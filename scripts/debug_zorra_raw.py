"""Focused: Extract Zorra 2011 farmland line 0110 raw values from S26A — write to file."""
import zipfile, io
from python_calamine import CalamineWorkbook

with zipfile.ZipFile("data/FIR Data/2011/FI113227 Zorra Tp.zip") as zf:
    xlsx_bytes = zf.read("FI113227 Zorra Tp.xlsx")

wb = CalamineWorkbook.from_object(io.BytesIO(xlsx_bytes))
rows = wb.get_sheet_by_name("26A").to_python()

lines = []

# Build col map from header area
lines.append("=== S26A Column Mapping ===")
for i in range(20):
    row = rows[i]
    non_empty = [(j, v) for j, v in enumerate(row[:22]) if v is not None and str(v).strip()]
    if non_empty:
        lines.append(f"  Row {i:2d}: {non_empty}")

# Find farmland lines
lines.append("\n=== Line 0110 (Farmland Taxable) ===")
for i, row in enumerate(rows):
    found = False
    for c in row[:3]:
        s = str(c).strip().replace(".0", "")
        if s == "0110" or s == "110":
            found = True
            break
    if found:
        lines.append(f"  Found at row {i}")
        for j in range(min(22, len(row))):
            lines.append(f"    Col[{j:2d}] = {repr(row[j])}")

lines.append("\n=== Line 1110 (Farmland PIL) ===")
for i, row in enumerate(rows):
    found = False
    for c in row[:3]:
        s = str(c).strip().replace(".0", "")
        if s == "1110":
            found = True
            break
    if found:
        lines.append(f"  Found at row {i}")
        for j in range(min(22, len(row))):
            lines.append(f"    Col[{j:2d}] = {repr(row[j])}")

lines.append("\n=== Line 9199 (Total Taxable) ===")
for i, row in enumerate(rows):
    found = False
    for c in row[:3]:
        s = str(c).strip().replace(".0", "")
        if s == "9199":
            found = True
            break
    if found:
        lines.append(f"  Found at row {i}")
        for j in range(min(22, len(row))):
            lines.append(f"    Col[{j:2d}] = {repr(row[j])}")

# Also look for S22A FT row
lines.append("\n=== S22A - Farmland (FT) row ===")
sheets_22 = [s for s in wb.sheet_names if "22" in s]
for sname in sheets_22:
    srows = wb.get_sheet_by_name(sname).to_python()
    lines.append(f"Sheet: {sname} ({len(srows)} rows)")
    for i in range(min(15, len(srows))):
        row = srows[i]
        non_empty = [(j, v) for j, v in enumerate(row[:15]) if v is not None and str(v).strip()]
        if non_empty:
            lines.append(f"  HdrRow {i:2d}: {non_empty}")
    for i, row in enumerate(srows):
        for c in row[:5]:
            if str(c).strip() == "FT":
                lines.append(f"\n  FT row at row {i}:")
                for j in range(min(15, len(row))):
                    lines.append(f"    Col[{j:2d}] = {repr(row[j])}")
                break

# Also check: what would $3,632,957 and $3,762,247 match?
lines.append("\n=== Searching for user's values ===")
target1 = 3632957
target2 = 3762247
for i, row in enumerate(rows):
    for j, v in enumerate(row):
        if isinstance(v, (int, float)):
            if abs(v - target1) < 100 or abs(v - target2) < 100:
                lines.append(f"  Found ~{v} at S26A row {i} col {j}")

for sname in sheets_22:
    srows = wb.get_sheet_by_name(sname).to_python()
    for i, row in enumerate(srows):
        for j, v in enumerate(row):
            if isinstance(v, (int, float)):
                if abs(v - target1) < 100 or abs(v - target2) < 100:
                    lines.append(f"  Found ~{v} at {sname} row {i} col {j}")

output = "\n".join(lines)
with open("scripts/zorra_raw_results.txt", "w") as f:
    f.write(output)
print(output)
