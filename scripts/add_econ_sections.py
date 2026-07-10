"""Add Economic Impact sections to the report."""
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
import os

REPORT_DIR = r'C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic Impact Studies\County Level\Perth and Wellington'

# Load the existing report
doc = Document(os.path.join(REPORT_DIR, 'Report_v2.docx'))

def set_cell_shading(cell, color):
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def add_styled_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(255, 255, 255)
        set_cell_shading(cell, "2E7D32")
    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = str(value)
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if col_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
                for run in paragraph.runs:
                    run.font.size = Pt(9)
            if row_idx % 2 == 0:
                set_cell_shading(cell, "E8F5E9")
    return table

# Find and replace the placeholder sections
# We need to find paragraph indices for "Economic Impact of Farming in Perth County"
# and replace "[To be completed]" text
for i, p in enumerate(doc.paragraphs):
    if p.text.strip() == '[To be completed]':
        # Find which section this belongs to
        # Look backward for the heading
        for j in range(i-1, -1, -1):
            if doc.paragraphs[j].style.name.startswith('Heading'):
                heading_text = doc.paragraphs[j].text.strip()
                break
        
        if heading_text == 'Economic Impact of Farming in Perth County':
            p.text = ''
            # We can't easily insert complex content (tables) between existing paragraphs
            # So we'll need to rebuild the document
            break

# Actually, the simplest approach is to rebuild the document adding the new sections
# Let me find all existing content and rebuild

print("Existing paragraphs:")
for i, p in enumerate(doc.paragraphs):
    if p.style.name.startswith('Heading'):
        print(f"  [{i}] {p.style.name}: {p.text}")

# The cleanest approach: read the existing v2, find the insertion points, build v3
# But since python-docx doesn't easily support inserting tables between paragraphs,
# let's use the write_report approach: read the script, add the new sections

print("\nWill rebuild with new content added.")
print("DONE")
