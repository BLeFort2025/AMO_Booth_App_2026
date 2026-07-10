"""Dump raw cell structure for failing FIR schedules to debug extraction."""
import zipfile, os, glob, io, openpyxl

BASE = os.path.join("data", "FIR Data")
YEAR = 2020
TARGET_CODE = "0101"
FAILING_SHEETS = ["26B", "10", "70", "80A"]

yr2 = str(YEAR)[2:]
matches = glob.glob(os.path.join(BASE, str(YEAR), f"FI{yr2}{TARGET_CODE}*.zip"))
fpath = matches[0]

out = open("scripts/fir_debug_sheets.md", "w", encoding="utf-8")
out.write(f"# FIR Debug: Sheet Structure for {os.path.basename(fpath)}\n\n")

with zipfile.ZipFile(fpath) as z:
    xlsx = [f for f in z.namelist() if f.endswith(".xlsx")][0]
    with z.open(xlsx) as xf:
        wb = openpyxl.load_workbook(io.BytesIO(xf.read()), read_only=True, data_only=True)
        
        for sheet_name in FAILING_SHEETS:
            out.write(f"## Schedule {sheet_name}\n\n")
            if sheet_name not in wb.sheetnames:
                out.write("**NOT FOUND**\n\n")
                continue
            
            ws = wb[sheet_name]
            out.write("```\n")
            
            # Dump first 30 rows with non-empty cells
            for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=40, values_only=False), 1):
                non_empty = []
                for cell in row:
                    if cell.value is not None and str(cell.value).strip():
                        v = str(cell.value).strip()
                        if len(v) > 60:
                            v = v[:60] + "..."
                        non_empty.append(f"[{cell.column}]{v}")
                if non_empty:
                    out.write(f"Row {row_idx:>3}: {' | '.join(non_empty)}\n")
            
            out.write("```\n\n")
        
        wb.close()

out.close()
print("Done - scripts/fir_debug_sheets.md")
