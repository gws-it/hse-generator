"""Shared docx -> pdf conversion via headless LibreOffice."""
import os
import subprocess
import tempfile


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
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
