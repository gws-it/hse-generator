import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User, Project, MaintenanceReport
from auth import get_current_user
import drive_sync
from create_maintenance_checklist import build_checklist_docx
from create_maintenance_report import build_report_docx
from pdf_convert import convert_docx_to_pdf

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


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
    try:
        data = drive_sync.download_file(file_id)
    except Exception as e:
        raise HTTPException(502, f"Could not fetch photo: {e}")
    return StreamingResponse(io.BytesIO(data), media_type="image/jpeg")


# ── Generate ──────────────────────────────────────────────────────────────

@router.post("/generate")
def generate(body: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project_id = body.get("project_id")
    date_from = body.get("date_from", "")
    date_to = body.get("date_to", "")
    photos = body.get("photos", [])  # [{file_id, name, date}], as returned by the photos search endpoint
    if not project_id or not photos:
        raise HTTPException(400, "project_id and photos are required")
    if not all(p.get("file_id") for p in photos):
        raise HTTPException(400, "each photo requires a file_id")

    project = _get_project(project_id, db)

    report = MaintenanceReport(
        user_id=current_user.id,
        project_id=project.id,
        date_from=date_from,
        date_to=date_to,
        photos=photos,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"report_id": report.id}


# ── Download ──────────────────────────────────────────────────────────────

def _get_report(report_id: int, current_user: User, db: Session) -> MaintenanceReport:
    report = db.query(MaintenanceReport).filter(
        MaintenanceReport.id == report_id,
        MaintenanceReport.user_id == current_user.id,
    ).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return report


def _project_dict(project: Project) -> dict:
    return {"name": project.name, "address": project.address, "project_type": project.project_type}


@router.get("/download/{report_id}/{doc}/{fmt}")
def download(
    report_id: int, doc: str, fmt: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    if doc not in ("checklist", "report") or fmt not in ("docx", "pdf"):
        raise HTTPException(400, "Invalid doc or format")

    report = _get_report(report_id, current_user, db)
    project = report.project
    logo = drive_sync.get_logo_bytes()

    if doc == "checklist":
        maintenance_date = report.date_to or report.date_from or ""
        docx_bytes = build_checklist_docx(_project_dict(project), maintenance_date, logo)
    else:
        try:
            photos = [
                {"bytes": drive_sync.download_file(p["file_id"]), "date": p.get("date", "")}
                for p in report.photos
            ]
        except Exception as e:
            raise HTTPException(502, f"Could not fetch photos from Drive: {e}")
        docx_bytes = build_report_docx(_project_dict(project), photos, logo)

    if fmt == "pdf":
        file_bytes = convert_docx_to_pdf(docx_bytes)
        media_type = "application/pdf"
    else:
        file_bytes = docx_bytes
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    fname = f"{doc}_{project.name}.{fmt}".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
