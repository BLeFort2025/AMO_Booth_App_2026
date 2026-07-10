"""
Spot-check FIR extraction accuracy: open actual FIR Excel files for
known municipalities and compare extracted values against the raw source.

This verifies that fir_indicators.yaml coordinates (schedule, line, col)
are pulling the RIGHT data from the RIGHT cells.
"""

import io
import zipfile
from pathlib import Path

import pandas as pd

try:
    from python_calamine import CalamineWorkbook
except ImportError:
    print("ERROR: python_calamine not installed")
    exit(1)

ROOT = Path(__file__).resolve().parent.parent
FIR_DIR = ROOT / "data" / "FIR Data"
FIR_CSV = ROOT / "data" / "derived" / "fir_indicators.csv"

df = pd.read_csv(FIR_CSV, low_memory=False)

# Spot-check municipalities with well-known FIR data 
# Use 2024 data for the most current validation
SPOT_CHECKS = [
    # (FIR code, year, description)
    ("2300", 2024, "Wellington Co (upper-tier, major agricultural county)"),
    ("4300", 2024, "Simcoe Co (upper-tier, the one from the screenshot)"),
    ("3650", 2024, "Chatham-Kent M (single-tier, heavy agriculture)"),
    ("3200", 2024, "Oxford Co (upper-tier, dairy country)"),
    ("2300", 2020, "Wellington Co 2020 (CVA freeze year)"),
]

# Key fields to verify from Schedule 26A
VERIFY_FIELDS_26A = {
    "farmland_cva":          ("0110", 16, "Farmland CVA"),
    "residential_cva":       ("0010", 16, "Residential CVA"),
    "commercial_cva":        ("9120", 16, "Commercial CVA (subtotal)"),
    "industrial_cva":        ("9130", 16, "Industrial CVA (subtotal)"),
    "total_taxable_cva":     ("9199", 16, "Total Taxable CVA"),
    "farmland_lt_taxes":     ("0110", 4,  "Farmland LT Taxes"),
    "farmland_ut_taxes":     ("0110", 5,  "Farmland UT Taxes"),
    "residential_lt_taxes":  ("0010", 4,  "Residential LT Taxes"),
    "total_lt_taxes":        ("9199", 4,  "Total LT Taxes"),
    "total_ut_taxes":        ("9199", 5,  "Total UT Taxes"),
}

def find_fir_zip(fir_code, year):
    """Find the FIR zip file for a given code and year."""
    yr2 = str(year)[-2:]
    year_dir = FIR_DIR / str(year)
    if not year_dir.exists():
        return None
    for zp in year_dir.glob(f"FI{yr2}{fir_code.zfill(4)}*.zip"):
        return zp
    return None


def read_raw_26a(zip_path):
    """Read Schedule 26A from a FIR zip file."""
    with zipfile.ZipFile(zip_path) as z:
        xlsx_files = [f for f in z.namelist() if f.endswith((".xlsx", ".xls"))]
        if not xlsx_files:
            return None
        xlsx_bytes = z.read(xlsx_files[0])
    
    wb = CalamineWorkbook.from_object(io.BytesIO(xlsx_bytes))
    if "26A" not in wb.sheet_names:
        return None
    
    rows = wb.get_sheet_by_name("26A").to_python()
    return rows


def find_value_in_26a(rows, line_code, fir_col):
    """Extract a value from 26A using FIR column mapping."""
    # Build column map from header
    best_map = {}
    best_count = 0
    header_row = 0
    
    for row_idx, row in enumerate(rows[:25]):
        nums = {}
        for col_i, cell in enumerate(row):
            if cell is None or cell == "":
                continue
            num = None
            if isinstance(cell, (int, float)):
                if cell == int(cell) and 1 <= int(cell) <= 20:
                    num = int(cell)
            else:
                try:
                    f = float(str(cell).strip())
                    if f == int(f) and 1 <= int(f) <= 20:
                        num = int(f)
                except ValueError:
                    pass
            if num is not None:
                nums[num] = col_i
        if len(nums) > best_count:
            best_count = len(nums)
            best_map = nums
            header_row = row_idx
        if len(nums) >= 2:
            break
    
    target_idx = best_map.get(fir_col)
    if target_idx is None:
        return None, f"FIR col {fir_col} not in col_map {best_map}"
    
    # Normalize line code for matching
    for row in rows[header_row + 1:]:
        for cell in row[:5]:
            if cell is None or cell == "":
                continue
            matched = False
            if isinstance(cell, (int, float)):
                try:
                    if f"{int(cell):04d}" == line_code:
                        matched = True
                except (ValueError, OverflowError):
                    pass
            else:
                if str(cell).strip() == line_code:
                    matched = True
            
            if matched:
                if target_idx < len(row):
                    v = row[target_idx]
                    return v, "OK"
                return None, f"Row too short (len={len(row)}, need idx={target_idx})"
    
    return None, f"Line code {line_code} not found"


print("=" * 100)
print("FIR EXTRACTION ACCURACY SPOT-CHECK")
print("Comparing extracted CSV values against raw FIR Excel files")
print("=" * 100)

total_checks = 0
total_match = 0
total_mismatch = 0

for fir_code, year, desc in SPOT_CHECKS:
    print(f"\n{'─'*100}")
    print(f"  {desc}")
    print(f"  FIR {fir_code}, Year {year}")
    print(f"{'─'*100}")
    
    # Get CSV data
    csv_row = df[(df["fir_code"].astype(str).str.zfill(4) == fir_code.zfill(4)) & 
                 (df["year"] == year)]
    if csv_row.empty:
        print(f"  ⚠ No CSV data for FIR {fir_code} year {year}")
        continue
    csv_row = csv_row.iloc[0]
    
    # Get raw Excel data
    zip_path = find_fir_zip(fir_code, year)
    if zip_path is None:
        print(f"  ⚠ FIR zip not found for {fir_code} / {year}")
        continue
    
    rows_26a = read_raw_26a(zip_path)
    if rows_26a is None:
        print(f"  ⚠ Schedule 26A not found in {zip_path.name}")
        continue
    
    print(f"  {'Field':<25} {'CSV Value':>20} {'Raw Excel':>20}  {'Match?'}")
    print(f"  {'─'*25} {'─'*20} {'─'*20}  {'─'*10}")
    
    for field_name, (line, col, desc_short) in VERIFY_FIELDS_26A.items():
        csv_val = csv_row.get(field_name)
        raw_val, status = find_value_in_26a(rows_26a, line, col)
        
        # Normalize for comparison
        csv_num = float(csv_val) if pd.notna(csv_val) else None
        raw_num = float(raw_val) if raw_val is not None else None
        
        total_checks += 1
        
        if csv_num is not None and raw_num is not None:
            # Allow small floating point tolerance
            match = abs(csv_num - raw_num) < 1.0  # within $1
            if match:
                total_match += 1
                emoji = "✅"
            else:
                total_mismatch += 1
                emoji = "❌"
        elif csv_num is None and raw_num is None:
            total_match += 1
            emoji = "✅ (both null)"
        else:
            total_mismatch += 1
            emoji = "❌ (one null)"
        
        csv_str = f"${csv_num:,.0f}" if csv_num is not None else "NULL"
        raw_str = f"${raw_num:,.0f}" if raw_num is not None else f"NULL ({status})"
        
        print(f"  {desc_short:<25} {csv_str:>20} {raw_str:>20}  {emoji}")

    # Also verify computed fields
    csv_farm_muni = csv_row.get("farmland_muni_taxes")
    csv_farm_lt = csv_row.get("farmland_lt_taxes")
    csv_farm_ut = csv_row.get("farmland_ut_taxes")
    if pd.notna(csv_farm_muni) and pd.notna(csv_farm_lt) and pd.notna(csv_farm_ut):
        computed_sum = float(csv_farm_lt) + float(csv_farm_ut)
        match = abs(float(csv_farm_muni) - computed_sum) < 1.0
        total_checks += 1
        if match:
            total_match += 1
            print(f"  {'Farm muni=LT+UT':<25} {f'${computed_sum:,.0f}':>20} {f'${float(csv_farm_muni):,.0f}':>20}  ✅")
        else:
            total_mismatch += 1
            print(f"  {'Farm muni=LT+UT':<25} {f'${computed_sum:,.0f}':>20} {f'${float(csv_farm_muni):,.0f}':>20}  ❌ MISMATCH")

print(f"\n{'='*100}")
print(f"SPOT-CHECK SUMMARY")
print(f"{'='*100}")
print(f"  Total field checks: {total_checks}")
print(f"  ✅ Matched:         {total_match}")
print(f"  ❌ Mismatched:      {total_mismatch}")
print(f"  Accuracy:           {total_match/total_checks*100:.1f}%")
print(f"{'='*100}")
