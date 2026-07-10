"""Debug 26A column map building with calamine."""
import io, zipfile
from python_calamine import CalamineWorkbook

z = zipfile.ZipFile(r"data\FIR Data\2020\FI200101 South Glengarry Tp.zip")
xb = z.read([f for f in z.namelist() if f.endswith(".xlsx")][0])
wb = CalamineWorkbook.from_object(io.BytesIO(xb))
rows = wb.get_sheet_by_name("26A").to_python()

with open("scripts/debug_26a_cols.txt", "w", encoding="utf-8") as f:
    for i in range(15):
        # Show type info too
        row_info = []
        for j, cell in enumerate(rows[i][:20]):
            if cell is not None and cell != '':
                row_info.append(f"[{j}]{repr(cell)}({type(cell).__name__})")
        f.write(f"Row {i}: {row_info}\n")

print("Done - see scripts/debug_26a_cols.txt")
