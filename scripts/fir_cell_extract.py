"""Same extraction but writes results as UTF-8 text file directly."""
import zipfile, os, glob, io, openpyxl

BASE = os.path.join("data", "FIR Data")
TARGET_CODE = "0101"
YEARS = [2020, 2024]

TARGETS = [
    ("26A", "9199", 16, "Total Taxable Assessment CVA"),
    ("26A", "9199", 3, "Total Taxes"),
    ("26A", "0010", 16, "Residential/Farm Taxable CVA"),
    ("26A", "0010", 3, "Residential/Farm Total Taxes"),
    ("26A", "0010", 4, "Residential/Farm Municipal LT/ST Taxes"),
    ("26A", "0050", 16, "Farmlands Taxable CVA"),
    ("26A", "0050", 3, "Farmlands Total Taxes"),
    ("26A", "0050", 4, "Farmlands Municipal LT/ST Taxes"),
    ("26A", "1210", 16, "Commercial Taxable CVA"),
    ("26A", "1210", 3, "Commercial Total Taxes"),
    ("26A", "1610", 16, "Industrial Taxable CVA"),
    ("26A", "1610", 3, "Industrial Total Taxes"),
    ("26B", "0010", 4, "Residential Municipal Tax Rate LT"),
    ("26B", "0050", 4, "Farmlands Municipal Tax Rate LT"),
    ("26B", "1210", 4, "Commercial Municipal Tax Rate LT"),
    ("26B", "1610", 4, "Industrial Municipal Tax Rate LT"),
    ("10", "9910", 4, "Total Revenue"),
    ("10", "0299", 4, "Total Taxation Revenue"),
    ("10", "0699", 4, "Total Ontario Grants"),
    ("40", "9910", 4, "Total Expenses"),
    ("40", "0699", 4, "Transportation Expenses"),
    ("40", "0899", 4, "Environmental Expenses"),
    ("70", "9930", 4, "Total Financial Assets"),
    ("70", "9940", 4, "Total Liabilities"),
    ("70", "2099", 4, "Net Financial Assets/Debt"),
    ("80A", "8001", 2, "Permanent Population"),
    ("80A", "8026", 2, "Total Households"),
    ("80A", "8030", 2, "Total Road KM"),
    ("80A", "8050", 2, "Water Cubic Metres Treated"),
    ("80A", "8060", 2, "Wastewater Cubic Metres Treated"),
]


def find_cell(ws, line_code, col_num):
    col_map = {}
    header_row = None
    for row_idx in range(1, 21):
        row = []
        for c in ws.iter_rows(min_row=row_idx, max_row=row_idx, values_only=False):
            row = c
            break
        nums = set()
        for cell in row:
            if cell.value is not None:
                v = str(cell.value).strip()
                if v.isdigit() and 1 <= int(v) <= 20:
                    nums.add(v)
        if len(nums) >= 3:
            header_row = row_idx
            for cell in row:
                if cell.value is not None:
                    v = str(cell.value).strip()
                    if v.isdigit():
                        col_map[int(v)] = cell.column
            break
    
    if not col_map:
        return None, "no header"
    tcol = col_map.get(col_num)
    if not tcol:
        return None, f"col {col_num} missing"
    
    for row in ws.iter_rows(min_row=header_row+1, max_row=200, values_only=False):
        for cell in row[:5]:
            if cell.value is not None and str(cell.value).strip() == str(line_code):
                tc = row[tcol - 1] if tcol <= len(row) else None
                return (tc.value if tc else None), "ok"
    return None, f"line {line_code} not found"


out = open("scripts/fir_results.md", "w", encoding="utf-8")
out.write("# FIR Cell Extraction Results\n\n")

for year in YEARS:
    yr2 = str(year)[2:]
    matches = glob.glob(os.path.join(BASE, str(year), f"FI{yr2}{TARGET_CODE}*.zip"))
    if not matches:
        out.write(f"## {year}: NO FILE\n\n")
        continue
    
    out.write(f"## {year}: {os.path.basename(matches[0])}\n\n")
    out.write("| Schedule | Line | Col | Value | Description |\n")
    out.write("|----------|------|-----|-------|-------------|\n")
    
    with zipfile.ZipFile(matches[0]) as z:
        xlsx = [f for f in z.namelist() if f.endswith(".xlsx")][0]
        with z.open(xlsx) as xf:
            wb = openpyxl.load_workbook(io.BytesIO(xf.read()), read_only=True, data_only=True)
            for sheet, line, col, desc in TARGETS:
                if sheet in wb.sheetnames:
                    ws = wb[sheet]
                    val, status = find_cell(ws, line, col)
                    if val is not None and isinstance(val, (int, float)):
                        out.write(f"| {sheet} | {line} | {col} | {val:,.2f} | {desc} |\n")
                    elif val is not None:
                        out.write(f"| {sheet} | {line} | {col} | {val} | {desc} |\n")
                    else:
                        out.write(f"| {sheet} | {line} | {col} | MISSING ({status}) | {desc} |\n")
                else:
                    out.write(f"| {sheet} | {line} | {col} | SHEET NOT FOUND | {desc} |\n")
            wb.close()
    out.write("\n")

out.close()
print("Done - results in scripts/fir_results.md")
