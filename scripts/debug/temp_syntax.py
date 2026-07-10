import ast
from pathlib import Path

pages_dir = Path(r"c:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter\app\pages")
matches = list(pages_dir.glob("8_*Simulator*"))
if matches:
    f = matches[0]
    print(f"Found: {f.name}")
    code = f.read_text(encoding="utf-8")
    ast.parse(code)
    print("Syntax OK")
    print(f"Total lines: {len(code.splitlines())}")
else:
    print("File not found")
