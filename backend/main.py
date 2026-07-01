import os
import io
import json
import subprocess
import tempfile
import threading
import uuid
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
from models import User, Generation, Template
from auth import verify_google_token, create_jwt, get_current_user, get_or_create_user
from parse_mos import parse_file, parse_google_doc
from generate import extract_project_details, generate_ra_swp, _generate_ra, _generate_swp
from create_ra import build_ra_docx
from create_swp import build_swp_docx
import drive_sync

app = FastAPI(title="HSE Report Generator", version="1.0.0")

# In-memory job store: {job_id: {status, result, error}}
jobs: dict = {}

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
        return

    # Pre-load logo cache
    try:
        drive_sync.get_logo_bytes()
    except Exception as e:
        print(f"[WARNING] Logo preload failed: {e}")

    # Auto-sync Drive templates (runs in background so startup is fast)
    def _bg_sync():
        try:
            from database import SessionLocal
            db = SessionLocal()
            synced = drive_sync.sync_templates(db)
            db.close()
            if synced:
                print(f"[Drive] Synced templates: {[s['project_type'] for s in synced]}")
            else:
                print("[Drive] No templates synced (check GOOGLE_API_KEY or GOOGLE_SERVICE_ACCOUNT_JSON)")
        except Exception as e:
            print(f"[Drive] Background sync failed: {e}")

    threading.Thread(target=_bg_sync, daemon=True).start()


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
    """Start RA generation in background. Returns job_id immediately."""
    mos_text = body.get("mos_text", "")
    project_details = body.get("project_details", {})
    if not mos_text:
        raise HTTPException(400, "mos_text is required")

    project_type = project_details.get("project_type", "")

    # Load uploaded templates for this project type
    tmpls = db.query(Template).filter(Template.project_type == project_type).order_by(Template.created_at.desc()).limit(2).all()
    template_examples = [{"project_type": t.project_type, "label": t.label,
                          "mos_text": t.mos_text, "ra_text": t.ra_text, "swp_text": t.swp_text}
                         for t in tmpls]

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "step": "ra", "result": None, "error": None}

    def run():
        try:
            ra = _generate_ra(mos_text, project_details, template_examples)

            # Save to DB
            from database import SessionLocal
            db2 = SessionLocal()
            try:
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
                db2.add(gen)
                db2.commit()
                db2.refresh(gen)
                jobs[job_id] = {"status": "done", "step": "ra", "result": {"generation_id": gen.id, "ra": ra}, "error": None}
            finally:
                db2.close()
        except Exception as e:
            import traceback
            print(f"[ERROR] RA job {job_id}: {traceback.format_exc()}")
            jobs[job_id] = {"status": "error", "step": "ra", "result": None, "error": str(e)}

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "status": "processing"}


@app.post("/api/generate/swp/{generation_id}")
def generate_swp_step(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Start SWP generation in background. Returns job_id immediately."""
    gen = _get_gen(generation_id, current_user, db)
    project_details = _project_details_from_gen(gen)
    ra_activities = gen.ra_swp_json.get("ra", {}).get("activities", [])
    mos_text = gen.mos_text

    # Load Drive/uploaded templates for this project type
    tmpls = db.query(Template).filter(Template.project_type == gen.project_type).order_by(Template.created_at.desc()).limit(2).all()
    template_examples = [{"project_type": t.project_type, "label": t.label,
                          "mos_text": t.mos_text, "ra_text": t.ra_text, "swp_text": t.swp_text}
                         for t in tmpls]

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "step": "swp", "result": None, "error": None}

    def run():
        try:
            swp = _generate_swp(mos_text, project_details, ra_activities, template_examples)
            from database import SessionLocal
            db2 = SessionLocal()
            try:
                g = db2.query(Generation).filter(Generation.id == generation_id).first()
                g.ra_swp_json = {**g.ra_swp_json, "swp": swp}
                g.updated_at = datetime.utcnow()
                db2.commit()
                jobs[job_id] = {"status": "done", "step": "swp", "result": {"generation_id": generation_id, "swp": swp}, "error": None}
            finally:
                db2.close()
        except Exception as e:
            import traceback
            print(f"[ERROR] SWP job {job_id}: {traceback.format_exc()}")
            jobs[job_id] = {"status": "error", "step": "swp", "result": None, "error": str(e)}

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "status": "processing"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Poll job status."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


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
    """Start feedback regeneration as a background job. Returns job_id immediately."""
    generation_id = body.get("generation_id")
    feedback = body.get("feedback", "").strip()
    if not feedback:
        raise HTTPException(400, "feedback text is required")

    gen = db.query(Generation).filter(Generation.id == generation_id, Generation.user_id == current_user.id).first()
    if not gen:
        raise HTTPException(404, "Generation not found")

    project_details = _project_details_from_gen(gen)
    mos_text = gen.mos_text
    prev_output = gen.ra_swp_json

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "step": "feedback", "result": None, "error": None}

    def run():
        try:
            new_ra_swp = generate_ra_swp(mos_text, project_details, feedback=feedback, previous_output=prev_output)
            from database import SessionLocal
            db2 = SessionLocal()
            try:
                g = db2.query(Generation).filter(Generation.id == generation_id).first()
                history = g.feedback_history or []
                history.append({"feedback": feedback, "timestamp": datetime.utcnow().isoformat()})
                g.feedback_history = history
                g.ra_swp_json = new_ra_swp
                g.updated_at = datetime.utcnow()
                db2.commit()
                jobs[job_id] = {"status": "done", "step": "feedback",
                                "result": {"generation_id": generation_id, "ra_swp": new_ra_swp}, "error": None}
            finally:
                db2.close()
        except Exception as e:
            import traceback
            print(f"[ERROR] Feedback job {job_id}: {traceback.format_exc()}")
            jobs[job_id] = {"status": "error", "step": "feedback", "result": None, "error": str(e)}

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "status": "processing"}


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
    logo = drive_sync.get_logo_bytes()
    docx_bytes = build_ra_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("ra", {}), logo)
    fname = f"RA_{gen.project_name or 'report'}.docx".replace(" ", "_")
    _auto_save_template(gen, db)
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/download/{generation_id}/swp/docx")
def download_swp_docx(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    logo = drive_sync.get_logo_bytes()
    docx_bytes = build_swp_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("swp", {}), logo)
    fname = f"SWP_{gen.project_name or 'report'}.docx".replace(" ", "_")
    _auto_save_template(gen, db)
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/download/{generation_id}/ra/pdf")
def download_ra_pdf(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    logo = drive_sync.get_logo_bytes()
    docx_bytes = build_ra_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("ra", {}), logo)
    pdf_bytes = _convert_to_pdf(docx_bytes)
    fname = f"RA_{gen.project_name or 'report'}.pdf".replace(" ", "_")
    _auto_save_template(gen, db)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/download/{generation_id}/swp/pdf")
def download_swp_pdf(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    gen = _get_gen(generation_id, current_user, db)
    logo = drive_sync.get_logo_bytes()
    docx_bytes = build_swp_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("swp", {}), logo)
    pdf_bytes = _convert_to_pdf(docx_bytes)
    fname = f"SWP_{gen.project_name or 'report'}.pdf".replace(" ", "_")
    _auto_save_template(gen, db)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _auto_save_template(gen: Generation, db: Session):
    """When user downloads, auto-save this generation as a template for AI learning."""
    if not gen.ra_swp_json:
        return
    # Don't save if RA has no activities — empty template would mislead future generations
    if not gen.ra_swp_json.get("ra", {}).get("activities"):
        return
    try:
        existing = db.query(Template).filter(
            Template.project_type == gen.project_type,
            Template.label == f"[Auto] {gen.project_name}",
        ).first()
        if existing:
            return  # already saved

        ra_text = json.dumps(gen.ra_swp_json.get("ra", {}), indent=2)
        swp_text = json.dumps(gen.ra_swp_json.get("swp", {}), indent=2)
        db.add(Template(
            user_id=gen.user_id,
            project_type=gen.project_type,
            label=f"[Auto] {gen.project_name}",
            mos_text=gen.mos_text[:5000] if gen.mos_text else "",
            ra_text=ra_text[:8000],
            swp_text=swp_text[:8000],
        ))
        db.commit()
    except Exception as e:
        print(f"[WARNING] Auto-save template failed: {e}")


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


# ── Drive Sync ────────────────────────────────────────────────────────────

@app.post("/api/drive-sync")
def trigger_drive_sync(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Manually trigger a re-sync of templates from Google Drive."""
    try:
        synced = drive_sync.sync_templates(db)
        drive_sync._logo_cache = None  # refresh logo too
        drive_sync.get_logo_bytes()
        return {"synced": synced, "count": len(synced)}
    except Exception as e:
        raise HTTPException(500, f"Drive sync failed: {e}")


# ── Templates ─────────────────────────────────────────────────────────────

@app.post("/api/templates")
async def upload_template(
    project_type: str = Form(...),
    label: str = Form(...),
    mos_file: Optional[UploadFile] = File(None),
    ra_file: Optional[UploadFile] = File(None),
    swp_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    async def read_file(f):
        if not f:
            return ""
        content = await f.read()
        try:
            return parse_file(content, f.filename)
        except Exception:
            return content.decode("utf-8", errors="ignore")

    mos_text = await read_file(mos_file)
    ra_text = await read_file(ra_file)
    swp_text = await read_file(swp_file)

    tmpl = Template(
        user_id=current_user.id,
        project_type=project_type,
        label=label,
        mos_text=mos_text,
        ra_text=ra_text,
        swp_text=swp_text,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return {"id": tmpl.id, "label": tmpl.label, "project_type": tmpl.project_type}


@app.get("/api/templates")
def list_templates(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    templates = db.query(Template).order_by(Template.created_at.desc()).all()
    return [{"id": t.id, "project_type": t.project_type, "label": t.label,
             "has_mos": bool(t.mos_text), "has_ra": bool(t.ra_text), "has_swp": bool(t.swp_text),
             "created_at": t.created_at.isoformat()} for t in templates]


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tmpl = db.query(Template).filter(Template.id == template_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    db.delete(tmpl)
    db.commit()
    return {"ok": True}


# ── Approve (save accepted generation as template) ────────────────────────

@app.post("/api/generations/{generation_id}/approve")
def approve_generation(generation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """User approves the generated report — saves to template DB and optionally to Drive."""
    gen = _get_gen(generation_id, current_user, db)
    if not gen.ra_swp_json:
        raise HTTPException(400, "No generated content to approve")

    # Save to template DB
    existing = db.query(Template).filter(
        Template.project_type == gen.project_type,
        Template.label == f"[Approved] {gen.project_name}",
    ).first()

    if not existing:
        db.add(Template(
            user_id=gen.user_id,
            project_type=gen.project_type,
            label=f"[Approved] {gen.project_name}",
            mos_text=(gen.mos_text or "")[:5000],
            ra_text=json.dumps(gen.ra_swp_json.get("ra", {}), indent=2)[:8000],
            swp_text=json.dumps(gen.ra_swp_json.get("swp", {}), indent=2)[:8000],
        ))
        db.commit()

    # Try to upload DOCX files to Google Drive (requires service account)
    drive_uploaded = False
    try:
        logo = drive_sync.get_logo_bytes()
        ra_bytes  = build_ra_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("ra",  {}), logo)
        swp_bytes = build_swp_docx(_project_details_from_gen(gen), gen.ra_swp_json.get("swp", {}), logo)
        drive_sync.upload_approved(gen.project_type, gen.project_name, ra_bytes, swp_bytes)
        drive_uploaded = True
    except Exception as e:
        print(f"[Drive upload skipped] {e}")

    return {"ok": True, "drive_uploaded": drive_uploaded}


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
