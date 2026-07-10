"""Change output filename to v3."""
with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace("Report_v2.docx", "Report_v3.docx")
with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Changed to Report_v3.docx")
