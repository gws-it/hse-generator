import io
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User, Project, MaintenanceReport
from auth import get_current_user
import drive_sync
from create_maintenance_report import build_report_docx
from pdf_convert import convert_docx_to_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

# In-memory job store for the async download flow (progress reporting on
# generation, which can take up to ~1 min for a report with many photos).
# Entries are evicted once served (get_job_file) and swept by age otherwise
# (a job whose result is never fetched -- e.g. the browser tab closes mid-poll
# -- would sit here forever holding its full file_bytes).
jobs: dict = {}
JOB_TTL_SECONDS = 3600


def _sweep_stale_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    for jid in [jid for jid, j in jobs.items() if j.get("created_at", 0) < cutoff]:
        jobs.pop(jid, None)


def _safe_filename(name: str) -> str:
    """ASCII-safe filename component. Project names are free-text and may
    contain characters (curly quotes, CJK, etc.) that break or crash HTTP
    header encoding (headers are Latin-1) if used as-is."""
    ascii_name = name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r'[\\/*?:"<>|]', "", ascii_name).strip()
    return ascii_name or "report"


# ── Projects ────────────────────────────────────────────────────────────────

@router.get("/projects")
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    projects = db.query(Project).order_by(Project.name).all()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "address": p.address,
         "client": p.client, "project_type": p.project_type}
        for p in projects
    ]


@router.post("/projects")
def add_project(body: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "code and name are required")

    if db.query(Project).filter(Project.code == code).first():
        raise HTTPException(400, f"Project code '{code}' already exists")

    project = Project(
        code=code,
        name=name,
        address=(body.get("address") or "").strip(),
        client=(body.get("client") or "").strip(),
        project_type=body.get("project_type") or "Green Roof",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "code": project.code, "name": project.name}


def _get_project(project_id: int, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


# ── Drive photo search ───────────────────────────────────────────────────────

@router.get("/projects/{project_id}/photos")
def project_photos(
    project_id: int, date_from: str, date_to: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, db)
    try:
        photos = drive_sync.list_project_photos(project.code, project.name, date_from, date_to)
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(502, f"Drive search failed: {e}")
    return photos


@router.get("/photo/{file_id}")
def photo_preview(file_id: str, current_user: User = Depends(get_current_user)):
    """Small thumbnail for the picker grid -- NOT the full-res image (see download())."""
    try:
        data = drive_sync.get_thumbnail(file_id)
    except Exception as e:
        raise HTTPException(502, f"Could not fetch photo: {e}")
    return StreamingResponse(io.BytesIO(data), media_type="image/jpeg")


@router.get("/drive/browse")
def browse_drive(folder_id: str = "", current_user: User = Depends(get_current_user)):
    """
    Manual folder browser -- fallback for when list_project_photos finds
    nothing (or misses some), e.g. a typo in the WhatsApp caption sent photos
    to the wrong folder. folder_id empty means the Drive root.
    """
    try:
        return drive_sync.browse_folder(folder_id)
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(502, f"Drive browse failed: {e}")


@router.get("/drive/browse-flat")
def browse_drive_flat(date_from: str, date_to: str, current_user: User = Depends(get_current_user)):
    """
    Flat alternative to /drive/browse -- lists every photo within the date
    range across all folders, grouped by (date, folder_name), so the user
    doesn't have to click through folders one at a time looking for misfiled
    photos. Can be slow for wide date ranges (walks every date folder in range).
    """
    try:
        return drive_sync.browse_flat(date_from, date_to)
    except ValueError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(502, f"Drive browse failed: {e}")


# ── Generate ──────────────────────────────────────────────────────────────

@router.post("/generate")
def generate(body: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project_id = body.get("project_id")
    date_from = body.get("date_from", "")
    date_to = body.get("date_to", "")
    address = (body.get("address") or "").strip()
    photos = body.get("photos", [])  # [{file_id, name, date}], as returned by the photos search endpoint
    if not project_id or not photos:
        raise HTTPException(400, "project_id and photos are required")
    if not all(p.get("file_id") for p in photos):
        raise HTTPException(400, "each photo requires a file_id")

    project = _get_project(project_id, db)

    # Keep Project.address in sync so it prefills correctly next time this project is used.
    if address and project.address != address:
        project.address = address

    report = MaintenanceReport(
        user_id=current_user.id,
        project_id=project.id,
        date_from=date_from,
        date_to=date_to,
        address=address,
        photos=photos,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"report_id": report.id}


# ── History ───────────────────────────────────────────────────────────────
# Shared across all users (not just whoever generated it) -- these are
# operational documents the whole team needs access to, unlike WHSE's
# per-user RA/SWP history.

@router.get("/history")
def history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reports = (
        db.query(MaintenanceReport)
        .order_by(MaintenanceReport.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": r.id,
            "project_name": r.project.name,
            "project_code": r.project.code,
            "date_from": r.date_from,
            "date_to": r.date_to,
            "photo_count": len(r.photos or []),
            "created_at": r.created_at.isoformat(),
            "generated_by": r.user.name or r.user.email,
        }
        for r in reports
    ]


# ── Download ──────────────────────────────────────────────────────────────

def _get_report(report_id: int, db: Session) -> MaintenanceReport:
    report = db.query(MaintenanceReport).filter(MaintenanceReport.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return report


def _project_dict(project: Project, report: MaintenanceReport) -> dict:
    return {
        "name": project.name,
        "address": report.address or project.address,
        "client": project.client,
        "project_type": project.project_type,
    }


def _build_document(report: MaintenanceReport, fmt: str, on_progress=None):
    """
    Builds the merged checklist + photo report document, returning
    (file_bytes, media_type, filename). on_progress(percent, step_label), if
    given, is called as work proceeds -- the photo-fetch step (the slow part,
    ~1 min for a report with many photos) is the only one where progress is
    meaningfully incremental.
    """
    def progress(pct, step):
        if on_progress:
            on_progress(pct, step)

    project = report.project
    logo = drive_sync.get_logo_bytes()
    project_dict = _project_dict(project, report)
    maintenance_date = report.date_to or report.date_from or ""

    total = len(report.photos) or 1
    photos_by_id = {}
    # Photos were already downloaded once during generate(); download()
    # re-fetches them fresh each time rather than storing large blobs in
    # Postgres. Fetching them concurrently (was sequential) is the main
    # fix for the ~1 min wait with no feedback. A photo that's since been
    # deleted/moved in Drive is skipped rather than failing the whole report --
    # historical reports shouldn't become permanently undownloadable over one
    # missing file.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(drive_sync.download_file, p["file_id"]): p["file_id"] for p in report.photos}
        done = 0
        for future in as_completed(futures):
            file_id = futures[future]
            try:
                photos_by_id[file_id] = future.result()
            except Exception as e:
                logger.warning(f"Maintenance report {report.id}: could not fetch photo {file_id}: {e}")
            done += 1
            progress(int(done / total * 70), f"Fetching photo {done} of {total}…")
    photos = [
        {"bytes": photos_by_id[p["file_id"]], "date": p.get("date", "")}
        for p in report.photos if p["file_id"] in photos_by_id
    ]
    progress(80, "Building report document…")
    docx_bytes = build_report_docx(project_dict, maintenance_date, photos, logo)

    if fmt == "pdf":
        progress(90, "Converting to PDF…")
        file_bytes = convert_docx_to_pdf(docx_bytes)
        media_type = "application/pdf"
    else:
        file_bytes = docx_bytes
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    progress(100, "Done")
    fname = f"report_{_safe_filename(project.name)}.{fmt}".replace(" ", "_")
    return file_bytes, media_type, fname


@router.get("/download/{report_id}/{fmt}")
def download(
    report_id: int, fmt: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Direct synchronous download -- kept for stable direct links. The
    frontend uses the async /download-start + /jobs flow below instead, for
    progress reporting."""
    if fmt not in ("docx", "pdf"):
        raise HTTPException(400, "Invalid format")

    report = _get_report(report_id, db)
    try:
        file_bytes, media_type, fname = _build_document(report, fmt)
    except Exception as e:
        raise HTTPException(502, f"Could not build document: {e}")

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/download-start/{report_id}/{fmt}")
def download_start(
    report_id: int, fmt: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Start document generation in the background, returning a job_id to poll
    for progress -- avoids the ~1 min blind wait of the direct download."""
    if fmt not in ("docx", "pdf"):
        raise HTTPException(400, "Invalid format")

    report = _get_report(report_id, db)  # validate it exists before backgrounding
    captured_report_id = report.id

    _sweep_stale_jobs()
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "progress": 0, "step": "Starting…", "error": None, "created_at": time.time()}

    def run():
        try:
            from database import SessionLocal
            db2 = SessionLocal()
            try:
                report2 = db2.query(MaintenanceReport).filter(MaintenanceReport.id == captured_report_id).first()
                file_bytes, media_type, fname = _build_document(
                    report2, fmt,
                    on_progress=lambda pct, step: jobs.__setitem__(
                        job_id, {**jobs[job_id], "progress": pct, "step": step}
                    ),
                )
                jobs[job_id] = {
                    "status": "done", "progress": 100, "step": "Done", "error": None,
                    "file_bytes": file_bytes, "media_type": media_type, "filename": fname,
                    "created_at": jobs[job_id].get("created_at", time.time()),
                }
            finally:
                db2.close()
        except Exception as e:
            jobs[job_id] = {
                "status": "error", "progress": 0, "step": "", "error": str(e),
                "created_at": jobs.get(job_id, {}).get("created_at", time.time()),
            }

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, current_user: User = Depends(get_current_user)):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {k: v for k, v in job.items() if k != "file_bytes"}


@router.get("/jobs/{job_id}/file")
def get_job_file(job_id: str, current_user: User = Depends(get_current_user)):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "File not ready")
    file_bytes, media_type, filename = job["file_bytes"], job["media_type"], job["filename"]
    jobs.pop(job_id, None)  # served -- drop the (potentially multi-MB) payload from memory
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
