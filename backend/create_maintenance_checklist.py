"""
Checklist section -- appended as a page within the merged Maintenance Report
(see create_maintenance_report.py). No longer a standalone document: the
letterhead/logo for this section is handled by the report's own per-page
header, so this module only adds content to an existing Document.
"""
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


def add_checklist_section(doc, project: dict, maintenance_date: str):
    """Appends the checklist title, table, and signature blocks to an existing Document."""
    title = doc.add_paragraph()
    run = title.add_run("Green Roof Maintenance Work Checklist")
    run.bold = True
    run.font.size = Pt(13)
    run.underline = True

    # Company contact details -- this page is printed and hand-signed on site,
    # so it's the one place in the document that needs to carry them (the
    # per-page header elsewhere only has the company name + reg no).
    contact = doc.add_paragraph()
    contact.alignment = WD_ALIGN_PARAGRAPH.LEFT
    contact_run = contact.add_run(
        "Tel: +65 6468 6772 | Fax: +65 6877 9989 | 102 Henderson Road, Singapore 159562 | "
        "hello@gwsliving.com | www.gwslivingart.com"
    )
    contact_run.font.size = Pt(8)

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
    # Proportions of the old portrait-page widths (1.5:9:3:4 of 17.5cm), scaled
    # to this document's actual section width -- this page is appended into
    # the report's landscape section, which is wider than the checklist was
    # originally designed for, so a fixed Cm() value would render too narrow.
    section = doc.sections[-1]
    content_width = section.page_width - section.left_margin - section.right_margin
    fractions = [1.5 / 17.5, 9 / 17.5, 3 / 17.5, 4 / 17.5]
    widths = [int(content_width * f) for f in fractions]
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
