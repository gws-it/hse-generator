"""Build the Green Roof Maintenance Work Checklist DOCX (prefilled, for printing & hand-signing)."""
import io
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

from docx_helpers import cell_text, set_cell_bg

# Only one item set exists today (Green Roof) -- keyed by project_type so more
# can be added later without touching the builder itself.
CHECKLIST_ITEMS = {
    "Green Roof": [
        "Weeding",
        "Checking of irrigation system",
        "Checking of green roof system",
        "Removal of dead leaves & debris",
        "Replacement of plants, where necessary",
        "Checking of growlight system",
    ],
}
DEFAULT_ITEM_SET = "Green Roof"


def _add_letterhead(doc, logo_bytes):
    table = doc.add_table(rows=1, cols=2)
    table.autofit = True
    logo_cell, text_cell = table.rows[0].cells

    if logo_bytes:
        p = logo_cell.paragraphs[0]
        p.add_run().add_picture(io.BytesIO(logo_bytes), height=Cm(2.2))

    lines = [
        ("GWS Living Art PTE LTD", True, 14),
        ("Reg no: 201709254M", False, 8),
        ("Tel: +65 6468 6772 | Fax: +65 6877 9989", False, 8),
        ("102 Henderson Road, Singapore 159562", False, 8),
        ("Email: hello@gwsliving.com | www.gwslivingart.com", False, 8),
    ]
    p = text_cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, (text, bold, size) in enumerate(lines):
        target = p if i == 0 else text_cell.add_paragraph()
        target.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = target.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)

    doc.add_paragraph()


def build_checklist_docx(project: dict, maintenance_date: str, logo_bytes: bytes = None) -> bytes:
    doc = Document()
    for section in doc.sections:
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    _add_letterhead(doc, logo_bytes)

    title = doc.add_paragraph()
    run = title.add_run("Green Roof Maintenance Work Checklist")
    run.bold = True
    run.font.size = Pt(13)
    run.underline = True

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("Project Name: ").bold = True
    p.add_run(project.get("name", ""))

    p2 = doc.add_paragraph()
    p2.add_run("Maintenance Date: ").bold = True
    p2.add_run(maintenance_date)

    doc.add_paragraph()

    items = CHECKLIST_ITEMS.get(project.get("project_type") or DEFAULT_ITEM_SET, CHECKLIST_ITEMS[DEFAULT_ITEM_SET])

    table = doc.add_table(rows=1 + len(items), cols=4)
    table.style = "Table Grid"
    headers = ["S/N", "Work Description", "Please Tick", "Remarks"]
    widths = [Cm(1.5), Cm(9), Cm(3), Cm(4)]
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell_text(cell, h, bold=True, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
        set_cell_bg(cell, "D9E1F2")
        table.columns[i].width = widths[i]

    for idx, item in enumerate(items):
        row = table.rows[idx + 1]
        cell_text(row.cells[0], idx + 1, align=WD_ALIGN_PARAGRAPH.CENTER)
        cell_text(row.cells[1], item)
        cell_text(row.cells[2], "")  # left blank -- ticked by hand
        cell_text(row.cells[3], "")  # left blank -- filled by hand

    doc.add_paragraph()
    doc.add_paragraph()

    sig = doc.add_table(rows=1, cols=2)
    left_cell, right_cell = sig.rows[0].cells

    cell_text(left_cell, "GWS LIVING ART PTE LTD", bold=True)
    for text in ["", "", "Signature:  ____________________", "Date:  ____________________"]:
        p = left_cell.add_paragraph()
        p.add_run(text)

    cell_text(right_cell, "Acknowledged by:", bold=True)
    for text in [
        "Name:  " + (project.get("address") or ""),
        "Signature:  ____________________",
        "Designation:  ____________________",
        "Date:  ____________________",
    ]:
        p = right_cell.add_paragraph()
        p.add_run(text)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()
