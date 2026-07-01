"""Read templates and company logo from Google Drive."""
import io
import json
import os
import base64
import logging

import requests

logger = logging.getLogger(__name__)

TEMPLATE_FOLDER_ID = os.getenv("DRIVE_TEMPLATE_FOLDER_ID", "1ZUldUo93atjfQpflj96GormprgOONCX_")
LOGO_FILE_ID = os.getenv("DRIVE_LOGO_FILE_ID", "1-5akbsnWrz_8E8uziD1_GuNb0tN1DQTY")

TYPE_MAP = {
    "green wall": "Green Wall",
    "green roof": "Green Roof",
    "construction": "Construction",
    "landscape": "Landscape",
}

# In-memory logo cache
_logo_cache: bytes | None = None


def _get_creds():
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        return None
    try:
        from google.oauth2.service_account import Credentials
        try:
            info = json.loads(sa_json)
        except Exception:
            info = json.loads(base64.b64decode(sa_json))
        return Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
    except Exception as e:
        logger.warning(f"Drive: service account parse error: {e}")
        return None


def _get_api_key():
    return os.getenv("GOOGLE_API_KEY", "")


def _download(file_id: str, creds=None, api_key: str = "") -> bytes:
    """Download a Drive file. Tries authenticated → API key → public URL."""
    if creds:
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload
            service = build("drive", "v3", credentials=creds)
            req = service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue()
        except Exception:
            pass

    if api_key:
        resp = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"alt": "media", "key": api_key},
            timeout=60,
        )
        if resp.ok:
            return resp.content

    # Fall back to public download URL (works for "Anyone with the link" shares)
    resp = requests.get(
        f"https://drive.google.com/uc?export=download&id={file_id}",
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def _list_folder(folder_id: str, creds=None, api_key: str = "") -> list[dict]:
    """Return list of {id, name, mimeType} for items in a Drive folder."""
    q = f"'{folder_id}' in parents and trashed=false"

    if creds:
        try:
            from googleapiclient.discovery import build
            service = build("drive", "v3", credentials=creds)
            result = service.files().list(
                q=q, fields="files(id,name,mimeType)"
            ).execute()
            return result.get("files", [])
        except Exception:
            pass

    if api_key:
        resp = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            params={"q": q, "fields": "files(id,name,mimeType)", "key": api_key},
            timeout=30,
        )
        if resp.ok:
            return resp.json().get("files", [])

    return []


def get_logo_bytes() -> bytes | None:
    """Return the GWS logo as PNG bytes (cached in memory)."""
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    try:
        creds = _get_creds()
        api_key = _get_api_key()
        data = _download(LOGO_FILE_ID, creds, api_key)
        _logo_cache = data
        logger.info("Drive: logo downloaded and cached.")
        return data
    except Exception as e:
        logger.warning(f"Drive: logo download failed: {e}")
        return None


def upload_approved(project_type: str, project_name: str, ra_bytes: bytes, swp_bytes: bytes):
    """Upload approved RA and SWP DOCX files into the correct Drive subfolder."""
    creds = _get_creds()
    if not creds:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set — cannot upload to Drive")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    service = build("drive", "v3", credentials=creds)

    # Find or create the project-type subfolder
    folder_name = project_type
    q = (f"'{TEMPLATE_FOLDER_ID}' in parents and "
         f"mimeType='application/vnd.google-apps.folder' and "
         f"name='{folder_name}' and trashed=false")
    res = service.files().list(q=q, fields="files(id)").execute()
    folders = res.get("files", [])

    if folders:
        folder_id = folders[0]["id"]
    else:
        meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder",
                "parents": [TEMPLATE_FOLDER_ID]}
        folder_id = service.files().create(body=meta, fields="id").execute()["id"]

    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    safe_name = project_name.replace("/", "-").replace("\\", "-")[:80]

    for label, content in [("RA", ra_bytes), ("SWP", swp_bytes)]:
        filename = f"{label}_{safe_name}.docx"
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=docx_mime, resumable=False)
        service.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        logger.info(f"Drive: uploaded {filename} to {project_type}/")


def sync_templates(db) -> list[dict]:
    """
    Scan Drive template folder subfolders, download MOS/RA/SWP files, and
    upsert into the Template table. Returns list of synced project types.
    """
    from models import Template
    from parse_mos import parse_file

    creds = _get_creds()
    api_key = _get_api_key()

    if not creds and not api_key:
        logger.warning("Drive sync: no GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_API_KEY set.")
        return []

    try:
        items = _list_folder(TEMPLATE_FOLDER_ID, creds, api_key)
    except Exception as e:
        logger.error(f"Drive sync: cannot list template folder: {e}")
        return []

    synced = []
    for folder in items:
        if folder.get("mimeType") != "application/vnd.google-apps.folder":
            continue
        project_type = TYPE_MAP.get(folder["name"].strip().lower())
        if not project_type:
            continue

        try:
            files = _list_folder(folder["id"], creds, api_key)
        except Exception as e:
            logger.warning(f"Drive sync: cannot list {folder['name']}: {e}")
            continue

        mos_text = ra_text = swp_text = ""
        for f in files:
            name_lower = f["name"].lower()
            try:
                content = _download(f["id"], creds, api_key)
                try:
                    text = parse_file(content, f["name"])
                except Exception:
                    text = content.decode("utf-8", errors="ignore")

                if "mos" in name_lower or "method" in name_lower:
                    mos_text = text
                elif "ra" in name_lower or "risk" in name_lower:
                    ra_text = text
                elif "swp" in name_lower or "safe" in name_lower or "sop" in name_lower:
                    swp_text = text
            except Exception as e:
                logger.warning(f"Drive sync: cannot download {f['name']}: {e}")

        existing = db.query(Template).filter(
            Template.project_type == project_type,
            Template.label.contains("[Drive]"),
        ).first()

        if existing:
            if mos_text: existing.mos_text = mos_text
            if ra_text:  existing.ra_text = ra_text
            if swp_text: existing.swp_text = swp_text
        else:
            db.add(Template(
                user_id=None,
                project_type=project_type,
                label=f"{project_type} [Drive]",
                mos_text=mos_text,
                ra_text=ra_text,
                swp_text=swp_text,
            ))

        db.commit()
        synced.append({"project_type": project_type, "folder": folder["name"]})
        logger.info(f"Drive sync: {project_type} ✓")

    return synced
