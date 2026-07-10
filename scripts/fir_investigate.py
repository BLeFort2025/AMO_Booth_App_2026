"""Deep investigation of Zorra 2021 FIR data issues."""
import pandas as pd
import glob, zipfile
from python_calamine import CalamineWorkbook

# ── 1. Check CSV output for all Zorra years ──
df = pd.read_csv("data/derived/fir_indicators.csv")
zorra = df[df["municipality_name"].str.contains("Zorra", na=False)].sort_values("year")

print("=== Zorra Records Across Years ===")
print(f"Years: {sorted(zorra['year'].unique())}")
print()

check_cols = [
    "total_expenses", "farmland_tax_ratio", "farmland_cva", 
    "farmland_total_taxes", "farmland_muni_taxes",
    "residential_cva", "total_taxable_cva", "total_revenue",
    "own_purpose_tax_rev", "farmland_lt_rate", "farmland_ut_rate",
    "residential_lt_rate",
]

for _, r in zorra.iterrows():
    yr = int(r["year"])
    print(f"\n--- Zorra {yr} ---")
    for c in check_cols:
        v = r.get(c)
        if pd.isna(v):
            print(f"  {c:30s}: NULL")
        elif abs(v) > 100:
            print(f"  {c:30s}: {v:>18,.0f}")
        else:
            print(f"  {c:30s}: {v:>18.6f}")

# ── 2. Validate against raw Zorra 2021 xlsx ──
print("\n\n=== RAW ZORRA 2021 VALIDATION ===")
zips = glob.glob("data/FIR Data/2021/*Zorra*")
if not zips:
    print("No Zorra 2021 FIR zip found!")
else:
    z = zips[0]
    print(f"File: {z}")
    with zipfile.ZipFile(z) as zf:
        xlsx = [n for n in zf.namelist() if n.endswith(".xlsx")][0]
        with zf.open(xlsx) as xf:
            wb = CalamineWorkbook.from_filelike(xf)

            # S26A: Check farmland line 0110
            r26 = wb.get_sheet_by_name("26A").to_python()
            # Find col map
            cm26 = {}
            hr26 = -1
            for ri, row in enumerate(r26[:25]):
                nums = {}
                for ci, cell in enumerate(row):
                    if cell is not None:
                        try:
                            v = int(float(str(cell).strip()))
                            if 1 <= v <= 20: nums[v] = ci
                        except: pass
                if len(nums) >= 2:
                    cm26 = nums
                    hr26 = ri
                    break
            
            print(f"\nS26A col_map: {dict(sorted(cm26.items()))}")
            
            # Extract key lines
            lines_26 = {
                "0010": "Residential",
                "0050": "Multi-Res",
                "0110": "Farmland",
                "0210": "Commercial",
                "0510": "Industrial",
                "9199": "Total",
            }
            for line_code, desc in lines_26.items():
                for row in r26[hr26+1:]:
                    matched = False
                    for cell in row[:5]:
                        if cell is None: continue
                        val = str(cell).strip()
                        try:
                            if isinstance(cell, float): val = str(int(cell)).zfill(4)
                        except: pass
                        if val == line_code:
                            c3 = row[cm26.get(3)] if 3 in cm26 and cm26[3] < len(row) else None
                            c4 = row[cm26.get(4)] if 4 in cm26 and cm26[4] < len(row) else None
                            c5 = row[cm26.get(5)] if 5 in cm26 and cm26[5] < len(row) else None
                            c16 = row[cm26.get(16)] if 16 in cm26 and cm26[16] < len(row) else None
                            print(f"  {desc:12s} ({line_code}): c3(total_tax)={c3}, c4(lt_tax)={c4}, c5(ut_tax)={c5}, c16(cva)={c16}")
                            matched = True
                            break
                    if matched: break

            # S40: Check total expenses col 4 vs col 11
            r40 = wb.get_sheet_by_name("40").to_python()
            cm40 = {}
            hr40 = -1
            for ri, row in enumerate(r40[:25]):
                nums = {}
                for ci, cell in enumerate(row):
                    if cell is not None:
                        try:
                            v = int(float(str(cell).strip()))
                            if 1 <= v <= 20: nums[v] = ci
                        except: pass
                if len(nums) >= 3:
                    cm40 = nums
                    hr40 = ri
                    break
            
            print(f"\nS40 col_map: {dict(sorted(cm40.items()))}")
            
            for row in r40[hr40+1:]:
                for cell in row[:5]:
                    if cell is None: continue
                    val = str(cell).strip()
                    try:
                        if isinstance(cell, float): val = str(int(cell)).zfill(4)
                    except: pass
                    if val == "9910":
                        for col_id in [2, 4, 11]:
                            if col_id in cm40:
                                v = row[cm40[col_id]] if cm40[col_id] < len(row) else None
                                print(f"  S40 Line 9910 Col {col_id:2d} = {v}")
                        break

            # S22A: Check farmland tax ratio
            r22 = wb.get_sheet_by_name("22A").to_python()
            cm22 = {}
            hr22 = -1
            for ri, row in enumerate(r22[:20]):
                nums = {}
                for ci, cell in enumerate(row):
                    if cell is not None:
                        try:
                            v = int(float(str(cell).strip()))
                            if 1 <= v <= 20: nums[v] = ci
                        except: pass
                if len(nums) >= 3:
                    cm22 = nums
                    hr22 = ri
                    break
            
            print(f"\nS22A col_map: {dict(sorted(cm22.items()))}")
            
            for row in r22[hr22+1:]:
                for cell in row[:8]:
                    if cell is not None and str(cell).strip() in ["RT", "FT", "CT", "IT", "MT"]:
                        rtc = str(cell).strip()
                        c5 = row[cm22.get(5)] if 5 in cm22 and cm22[5] < len(row) else None
                        c8 = row[cm22.get(8)] if 8 in cm22 and cm22[8] < len(row) else None
                        c9 = row[cm22.get(9)] if 9 in cm22 and cm22[9] < len(row) else None
                        print(f"  RTC={rtc}: ratio(c5)={c5}, lt_rate(c8)={c8}, ut_rate(c9)={c9}")
                        break
