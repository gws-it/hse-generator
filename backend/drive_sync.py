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

# Known file IDs from the GWS template Drive folder.
# These are used as a fallback when the API cannot list folder contents
# (e.g. "Anyone with link" sharing doesn't support API key listing).
KNOWN_TEMPLATES = {
    "Green Wall": [
        {"id": "1yVkYxep-779Z4RAaFmC82k-UciGzja5R", "name": "IWMF - GWS Green Wall MOS_rev.1.docx"},
        {"id": "1rSKmbxD2ngWo_4Hjs-RGGtzWAEZ_qKJm", "name": "IWMF_GWS_RA (1).docx"},
        {"id": "1Glf_LthyoyB_TgkvYkbhYsfkeqEvauHg", "name": "IWMF - SWP - Green wall (Rev_0).docx"},
    ],
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


def _sync_project_type(project_type: str, files: list[dict], db, creds, api_key: str) -> bool:
    """Download files for one project type and upsert into Template table."""
    from models import Template
    from parse_mos import parse_file

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

    if not mos_text and not ra_text and not swp_text:
        return False

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
    logger.info(f"Drive sync: {project_type} ✓")
    return True


# ── Maintenance-report photo search ────────────────────────────────────────
# The Photo-to-Drive bot organizes its Shared Drive as
# <date YYYY-MM-DD>/<"<code> - <name>">/<photo>. There's no efficient way to
# query "descendants of folder X" in the Drive API, so instead we search
# globally for folders matching that exact name (assumes the service account
# only has access to Drives relevant to this app, so a global name search
# won't collide with an unrelated folder that happens to share the name).

def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_project_folders(code: str, name: str, service=None) -> list[dict]:
    """Find every Drive folder named '<code> - <name>' (the bot's project-folder
    naming convention). Returns [{id, name, parents}]."""
    creds = _get_creds()
    if not creds:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set -- cannot search Drive")
    if service is None:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=creds)

    folder_name = _escape_query(f"{code} - {name}")
    q = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    result = service.files().list(
        q=q,
        fields="files(id,name,parents)",
        corpora="allDrives",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    return result.get("files", [])


def list_project_photos(code: str, name: str, date_from: str, date_to: str) -> list[dict]:
    """
    Return [{file_id, name, date}] for every image in this project's Drive
    folders whose parent date-folder (format YYYY-MM-DD) falls within
    [date_from, date_to] inclusive.
    """
    creds = _get_creds()
    if not creds:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set -- cannot search Drive")
    from googleapiclient.discovery import build
    service = build("drive", "v3", credentials=creds)

    photos = []
    for folder in find_project_folders(code, name, service):
        parents = folder.get("parents") or []
        if not parents:
            continue
        try:
            date_meta = service.files().get(
                fileId=parents[0], fields="name", supportsAllDrives=True
            ).execute()
        except Exception as e:
            logger.warning(f"Drive: could not resolve date folder for {folder['name']}: {e}")
            continue
        date_str = date_meta.get("name", "")
        if not date_str or not (date_from <= date_str <= date_to):
            continue

        q = f"'{folder['id']}' in parents and mimeType contains 'image/' and trashed=false"
        res = service.files().list(
            q=q, fields="files(id,name)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        for f in res.get("files", []):
            photos.append({"file_id": f["id"], "name": f["name"], "date": date_str})

    photos.sort(key=lambda p: (p["date"], p["name"]))
    return photos


def download_file(file_id: str) -> bytes:
    """Download an arbitrary Drive file (e.g. a maintenance photo) by ID, full resolution."""
    return _download(file_id, _get_creds(), _get_api_key())


PHOTO_DRIVE_ROOT_FOLDER_ID = os.getenv("PHOTO_DRIVE_ROOT_FOLDER_ID", "")


def browse_folder(folder_id: str = "") -> dict:
    """
    List the subfolders and images directly inside a Drive folder (defaults to
    the bot's Drive root if no folder_id given). Manual fallback for when a
    project's photos don't turn up in list_project_photos -- e.g. a typo in the
    WhatsApp caption sent it to the wrong folder, or _Unsorted.
    """
    creds = _get_creds()
    if not creds:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set -- cannot browse Drive")

    root = folder_id or PHOTO_DRIVE_ROOT_FOLDER_ID
    if not root:
        raise ValueError("PHOTO_DRIVE_ROOT_FOLDER_ID not configured -- cannot browse Drive")

    from googleapiclient.discovery import build
    service = build("drive", "v3", credentials=creds)

    res = service.files().list(
        q=f"'{root}' in parents and trashed=false",
        fields="files(id,name,mimeType)",
        orderBy="name desc",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get("files", [])

    folders = [{"id": f["id"], "name": f["name"]} for f in files
               if f["mimeType"] == "application/vnd.google-apps.folder"]
    images = [{"file_id": f["id"], "name": f["name"]} for f in files
              if f["mimeType"].startswith("image/")]
    return {"folders": folders, "images": images}


def browse_flat(date_from: str, date_to: str) -> list[dict]:
    """
    List every photo across every folder within [date_from, date_to] (inclusive,
    'YYYY-MM-DD'), grouped by (date, folder_name) -- a flat alternative to
    browse_folder() for when clicking through folders one at a time to find a
    project's misfiled photos is too slow. Fetches date folders' subfolders and
    each subfolder's images concurrently to keep this reasonably fast.
    """
    creds = _get_creds()
    if not creds:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set -- cannot browse Drive")
    root = PHOTO_DRIVE_ROOT_FOLDER_ID
    if not root:
        raise ValueError("PHOTO_DRIVE_ROOT_FOLDER_ID not configured -- cannot browse Drive")

    from googleapiclient.discovery import build
    from concurrent.futures import ThreadPoolExecutor

    def _service():
        # Built fresh per call/thread -- googleapiclient service objects (and the
        # httplib2 transport underneath) aren't safe to share across threads.
        return build("drive", "v3", credentials=creds)

    top = _service().files().list(
        q=f"'{root}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id,name)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    date_folders = [f for f in top.get("files", []) if date_from <= f["name"] <= date_to]

    def list_children(parent_id, mime_filter=None):
        svc = _service()
        q = f"'{parent_id}' in parents and trashed=false"
        if mime_filter == "folder":
            q += " and mimeType='application/vnd.google-apps.folder'"
        elif mime_filter == "image":
            q += " and mimeType contains 'image/'"
        res = svc.files().list(
            q=q, fields="files(id,name)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        return res.get("files", [])

    def process_date_folder(date_folder):
        groups = []
        subfolders = list_children(date_folder["id"], "folder")
        with ThreadPoolExecutor(max_workers=8) as pool:
            images_by_folder = list(pool.map(lambda sf: list_children(sf["id"], "image"), subfolders))
        for subfolder, images in zip(subfolders, images_by_folder):
            if not images:
                continue
            groups.append({
                "date": date_folder["name"],
                "folder_name": subfolder["name"],
                "photos": [{"file_id": f["id"], "name": f["name"]} for f in images],
            })
        return groups

    all_groups = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for groups in pool.map(process_date_folder, date_folders):
            all_groups.extend(groups)

    all_groups.sort(key=lambda g: (g["date"], g["folder_name"]))
    return all_groups


def get_thumbnail(file_id: str) -> bytes:
    """
    Fetch Drive's pre-generated small thumbnail for a file instead of the full-
    resolution original -- used for the photo picker grid, where dozens of
    photos may be shown at once and full downloads would be far too slow.
    Falls back to the full download if no thumbnail is available.
    """
    creds = _get_creds()
    if not creds:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not set -- cannot fetch thumbnail")
    from googleapiclient.discovery import build
    service = build("drive", "v3", credentials=creds)

    meta = service.files().get(
        fileId=file_id, fields="thumbnailLink", supportsAllDrives=True
    ).execute()
    thumbnail_link = meta.get("thumbnailLink")
    if thumbnail_link:
        resp = requests.get(thumbnail_link, timeout=15)
        if resp.ok:
            return resp.content

    return download_file(file_id)


def sync_templates(db) -> list[dict]:
    """
    Sync template files from Google Drive into the Template DB table.
    First tries to list folders via API; falls back to hardcoded known file IDs
    when the folder is shared as 'Anyone with link' (not listable via API key).
    """
    creds = _get_creds()
    api_key = _get_api_key()

    synced = []

    # Try dynamic listing via API first
    try:
        items = _list_folder(TEMPLATE_FOLDER_ID, creds, api_key)
        for folder in items:
            if folder.get("mimeType") != "application/vnd.google-apps.folder":
                continue
            project_type = TYPE_MAP.get(folder["name"].strip().lower())
            if not project_type:
                continue
            try:
                files = _list_folder(folder["id"], creds, api_key)
                if _sync_project_type(project_type, files, db, creds, api_key):
                    synced.append({"project_type": project_type, "folder": folder["name"]})
            except Exception as e:
                logger.warning(f"Drive sync: cannot process {folder['name']}: {e}")
    except Exception as e:
        logger.warning(f"Drive sync: API listing failed ({e}), using hardcoded file IDs.")

    # If API listing yielded nothing, fall back to hardcoded known file IDs
    if not synced:
        logger.info("Drive sync: falling back to hardcoded file IDs.")
        for project_type, files in KNOWN_TEMPLATES.items():
            if _sync_project_type(project_type, files, db, creds, api_key):
                synced.append({"project_type": project_type, "folder": project_type})

    return synced
