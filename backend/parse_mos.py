import io
import re
import zipfile
import xml.etree.ElementTree as ET
import requests
import fitz  # PyMuPDF


def parse_file(content: bytes, filename: str) -> str:
    """Parse MOS from uploaded file bytes."""
    fname = filename.lower()
    if fname.endswith(".pdf"):
        return _parse_pdf(content)
    elif fname.endswith(".docx"):
        return _parse_docx(content)
    else:
        raise ValueError(f"Unsupported file type: {filename}")


def parse_google_doc(url: str, access_token: str = None) -> str:
    """Download and parse a Google Doc or Drive file."""
    file_id = _extract_drive_id(url)
    if not file_id:
        raise ValueError("Could not extract Google Drive file ID from URL")

    export_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    resp = requests.get(export_url, headers=headers, timeout=30)
    if resp.status_code == 401:
        raise ValueError("Google Drive file is private. Please share it or upload from PC.")
    if resp.status_code != 200:
        # Try as a regular Drive file export
        export_url2 = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        resp = requests.get(export_url2, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"Cannot download file from Google Drive (status {resp.status_code})")

    return _parse_docx(resp.content)


def _parse_pdf(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    lines = []
    for page in doc:
        lines.append(page.get_text())
    return "\n".join(lines)


def _parse_docx(content: bytes) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
    except Exception as e:
        raise ValueError(f"Cannot read DOCX file: {e}")

    root = tree.getroot()
    paragraphs = []
    for para in root.iter(ns + "p"):
        parts = []
        for r in para.iter(ns + "r"):
            for t in r.iter(ns + "t"):
                if t.text:
                    parts.append(t.text)
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_drive_id(url: str) -> str | None:
    patterns = [
        r"/document/d/([a-zA-Z0-9_-]+)",
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
