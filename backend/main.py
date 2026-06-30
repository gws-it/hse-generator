import os
import io
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from database import get_db, init_db
from models import User, Generation
from auth import verify_google_token, create_jwt, get_current_user, get_or_create_user
from parse_mos import parse_file, parse_google_doc
from generate import extract_project_details, generate_ra_swp, _generate_ra, _generate_swp
from create_ra import build_ra_docx
from create_swp import build_swp_docx

app = FastAPI(title="HSE Report Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/config")
def get_config():
    return {"google_client_id": os.getenv("GOOGLE_CLIENT_ID", "")}


@app.on_event("startup")
def on_startup():
    try:
        init_db()
    except Exception as e:
        print(f"[WARNING] Database init failed: {e}")
        print("[WARNING] App will start but DB features won't work until DATABASE_URL is correct.")


# ── Auth ──────────────────────────────────────────────────────────────────

@app.post("/api/auth/google")
def google_auth(body: dict, db: Session = Depends(get_db)):
    """Exchange Google ID token for app JWT."""
    google_token = body.get("credential")
    if not google_token:
        raise HTTPException(400, "No credential provided")

    try:
        google_data = verify_google_token(google_token)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Token verification error: {e}")

    try:
        user = get_or_create_user(db, google_data)
    except Exception as e:
        raise HTTPException(500, f"Database error: {e}")

    try:
        token = create_jwt(user.id)
    except Exception as e:
        raise HTTPException(500, f"JWT error: {e}")

    return {"token": token, "user": {"id": user.id, "name": user.name, "email": user.email, "picture": user.picture}}


@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email, "picture": current_user.picture}


# ── MOS Upload & Extract ───────────────────────────────────────────────────

@app.post("/api/upload-mos")
async def upload_mos(
    file: Optional[UploadFile] = File(None),
    google_drive_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Upload MOS file or provide Google Drive URL. Returns extracted text."""
    if file:
        content = await file.read()
        try:
            mos_text = parse_file(content, file.filename)
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif google_drive_url:
        try:
            mos_text = parse_google_doc(google_drive_url)
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        raise HTTPException(400, "Provide a file or Google Drive URL")

    if not mos_text.strip():
        raise HTTPException(400, "Could not extract text from the document. Please check the file.")

    return {"mos_text": mos_text[:15000], "char_count": len(mos_text)}


@app.post("/api/extract-details")
def extract_details(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Extract and prefill project details from MOS text using AI."""
    mos_text = body.get("mos_text", "")
    if not mos_text:
        raise HTTPException(400, "mos_text is required")
    try:
        details = extract_project_details(mos_text)
    except Exception as e:
        raise HTTPException(500, f"AI extraction failed: {e}")
    return details


# ── Generate ──────────────────────────────────────────────────────────────

@app.post("/api/generate/ra")
def generate_ra_step(body: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Step 1: Generate RA only. Creates a Generation record and returns generation_id."""
    mos_text = body.get("mos_text", "")
    project_details = body.get("project_details", {})
    if not mos_text:
        raise HTTPException(400, "mos_text is required")

    project_type = project_details.get("project_type", "")
    examples = (
        db.query(Generation)
        .filter(Generation.project_type == project_type, Generation.ra_swp_json.isnot(None))
        .order_by(Generation.updated_at.desc())
        .limit(2)
        .all()
    )
    few_shot = [{"project_type": ex.project_type, **ex.ra_swp_json} for ex in examples if ex.ra_swp_json]

    try:
        ra = _generate_ra(mos_text, project_details, few_shot)
    except Exception as e:
        raise HTTPException(500, f"RA generation failed: {e}")

    gen = Generation(
        user_id=current_user.id,
        project_name=project_details.get("project_name"),
        project_type=project_type,
        location=project_details.get("location"),
        ra_leader=project_details.get("ra_leader"),
        approved_by=project_details.get("approved_by"),
        ra_members=project_details.get("ra_members", []),
        reference_no=project_details.get("reference_no"),
        company=project_details.get("company"),
        client=project_details.get("client"),
        assessment_date=project_details.get("assessment_date", datetime.today().strftime("%d %b %Y")),
        mos_text=mos_text,
        ra_swp_json={"project_type": project_type, "ra": ra, "swp": {}},
        feedback_history=[],
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)
    return {"generation_id": gen.id, "ra": ra}


@app.post("/api/generate/swp/{generation_id}")
def generate_swp_step(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Step 2: Generate SWP using the saved RA from step 1."""
    gen = _get_gen(generation_id, current_user, db)
    project_details = _project_details_from_gen(gen)
    ra_activities = gen.ra_swp_json.get("ra", {}).get("activities", [])

    try:
        swp = _generate_swp(gen.mos_text, project_details, ra_activities)
    except Exception as e:
        raise HTTPException(500, f"SWP generation failed: {e}")

    gen.ra_swp_json = {**gen.ra_swp_json, "swp": swp}
    gen.updated_at = datetime.utcnow()
    db.commit()
    return {"generation_id": gen.id, "swp": swp}


@app.post("/api/generate")
def generate(body: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Legacy single-call generate (used by feedback flow)."""
    mos_text = body.get("mos_text", "")
    project_details = body.get("project_details", {})
    if not mos_text:
        raise HTTPException(400, "mos_text is required")

    project_type = project_details.get("project_type", "")
    examples = (
        db.query(Generation)
        .filter(Generation.project_type == project_type, Generation.ra_swp_json.isnot(None))
        .order_by(Generation.updated_at.desc())
        .limit(2)
        .all()
    )
    few_shot = [{"project_type": ex.project_type, **ex.ra_swp_json} for ex in examples if ex.ra_swp_json]

    try:
        ra_swp = generate_ra_swp(mos_text, project_details, few_shot_examples=few_shot)
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")

    # Save to DB
    gen = Generation(
        user_id=current_user.id,
        project_name=project_details.get("project_name"),
        project_type=project_details.get("project_type"),
        location=project_details.get("location"),
        ra_leader=project_details.get("ra_leader"),
        approved_by=project_details.get("approved_by"),
        ra_members=project_details.get("ra_members", []),
        reference_no=project_details.get("reference_no"),
        company=project_details.get("company"),
        client=project_details.get("client"),
        assessment_date=project_details.get("assessment_date", datetime.today().strftime("%d %b %Y")),
        mos_text=mos_text,
        ra_swp_json=ra_swp,
        feedback_history=[],
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)

    return {"generation_id": gen.id, "ra_swp": ra_swp}


@app.post("/api/feedback")
def apply_feedback(body: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Apply user feedback to regenerate RA/SWP."""
    generation_id = body.get("generation_id")
    feedback = body.get("feedback", "").strip()

    if not feedback:
        raise HTTPException(400, "feedback text is required")

    gen = db.query(Generation).filter(Generation.id == generation_id, Generation.user_id == current_user.id).first()
    if not gen:
        raise HTTPException(404, "Generation not found")

    project_details = {
        "project_name": gen.project_name,
        "project_type": gen.project_type,
        "location": gen.location,
        "ra_leader": gen.ra_leader,
        "approved_by": gen.approved_by,
        "ra_members": gen.ra_members,
        "reference_no": gen.reference_no,
        "company": gen.company,
        "client": gen.client,
        "assessment_date": gen.assessment_date,
    }

    try:
        new_ra_swp = generate_ra_swp(
            gen.mos_text,
            project_details,
            feedback=feedback,
            previous_output=gen.ra_swp_json,
        )
    except Exception as e:
        raise HTTPException(500, f"Regeneration failed: {e}")

    # Append to feedback history and update
    history = gen.feedback_history or []
    history.append({"feedback": feedback, "timestamp": datetime.utcnow().isoformat()})
    gen.feedback_history = history
    gen.ra_swp_json = new_ra_swp
    gen.updated_at = datetime.utcnow()
    db.commit()

    return {"generation_id": gen.id, "ra_swp": new_ra_swp}


# ── Download ──────────────────────────────────────────────────────────────

def _get_gen(generation_id: int, current_user: User, db: Session) -> Generation:
    gen = db.query(Generation).filter(
        Generation.id == generation_id,
        Generation.user_id == current_user.id,
    ).first()
    if not gen:
        raise HTTPException(404, "Generation not found")
    return gen


def _project_details_from_gen(gen: Generation) -> dict:
    return {
        "project_name": gen.project_name,
        "project_type": gen.project_type,
        "location": gen.location,
        "ra_leader": gen.ra_leader,
        "approved_by": gen.approved_by,
        "ra_members": gen.ra_members,
        "reference_no": gen.reference_no,
        "company": gen.company,
        "client": gen.client,
        "assessment_date": gen.assessment_date,
    }


@app.get("/api/download/{generation_id}/ra/docx")
def download_ra_docx(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    docx_bytes = build_ra_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("ra", {}))
    fname = f"RA_{gen.project_name or 'report'}.docx".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/download/{generation_id}/swp/docx")
def download_swp_docx(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    docx_bytes = build_swp_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("swp", {}))
    fname = f"SWP_{gen.project_name or 'report'}.docx".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/download/{generation_id}/ra/pdf")
def download_ra_pdf(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    docx_bytes = build_ra_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("ra", {}))
    pdf_bytes = _convert_to_pdf(docx_bytes)
    fname = f"RA_{gen.project_name or 'report'}.pdf".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/download/{generation_id}/swp/pdf")
def download_swp_pdf(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    docx_bytes = build_swp_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("swp", {}))
    pdf_bytes = _convert_to_pdf(docx_bytes)
    fname = f"SWP_{gen.project_name or 'report'}.pdf".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _convert_to_pdf(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, "doc.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, docx_path],
            check=True, capture_output=True, timeout=60,
        )
        pdf_path = os.path.join(tmpdir, "doc.pdf")
        with open(pdf_path, "rb") as f:
            return f.read()


# ── History ───────────────────────────────────────────────────────────────

@app.get("/api/history")
def history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gens = (
        db.query(Generation)
        .filter(Generation.user_id == current_user.id)
        .order_by(Generation.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": g.id,
            "project_name": g.project_name,
            "project_type": g.project_type,
            "location": g.location,
            "created_at": g.created_at.isoformat(),
            "feedback_count": len(g.feedback_history or []),
        }
        for g in gens
    ]


@app.get("/api/history/{generation_id}")
def history_detail(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    return {
        "id": gen.id,
        "project_details": _project_details_from_gen(gen),
        "ra_swp": gen.ra_swp_json,
        "feedback_history": gen.feedback_history,
        "created_at": gen.created_at.isoformat(),
    }


# ── Serve React frontend ───────────────────────────────────────────────────

static_dir = Path(__file__).parent / "static"

@app.get("/")
def root():
    index = static_dir / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>HSE Generator API is running. Frontend not built yet.</h2>")

if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

@app.get("/{full_path:path}")
def spa(full_path: str):
    index = static_dir / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Frontend not found")
