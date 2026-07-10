"""Deep scan Schedule 80A for demographics/infrastructure rows."""
import zipfile, os, glob, io, openpyxl

BASE = os.path.join("data", "FIR Data")
YEAR = 2020
TARGET_CODE = "0101"

yr2 = str(YEAR)[2:]
matches = glob.glob(os.path.join(BASE, str(YEAR), f"FI{yr2}{TARGET_CODE}*.zip"))
fpath = matches[0]

out = open("scripts/fir_80a_full.md", "w", encoding="utf-8")
out.write(f"# Schedule 80A Full Dump\n\n```\n")

with zipfile.ZipFile(fpath) as z:
    xlsx = [f for f in z.namelist() if f.endswith(".xlsx")][0]
    with z.open(xlsx) as xf:
        wb = openpyxl.load_workbook(io.BytesIO(xf.read()), read_only=True, data_only=True)
        
        # Also check 80B, 80C, 80D
        for sname in ["80A", "80B", "80C", "80D"]:
            if sname not in wb.sheetnames:
                out.write(f"\n--- {sname}: NOT FOUND ---\n")
                continue
            out.write(f"\n--- {sname} ---\n")
            ws = wb[sname]
            for row_idx, row in enumerate(ws.iter_rows(values_only=False), 1):
                non_empty = []
                for cell in row:
                    if cell.value is not None and str(cell.value).strip():
                        v = str(cell.value).strip()
                        if len(v) > 80:
                            v = v[:80] + "..."
                        non_empty.append(f"[{cell.column}]{v}")
                if non_empty:
                    out.write(f"Row {row_idx:>3}: {' | '.join(non_empty)}\n")
        
        wb.close()

out.write("```\n")
out.close()
print("Done - scripts/fir_80a_full.md")
