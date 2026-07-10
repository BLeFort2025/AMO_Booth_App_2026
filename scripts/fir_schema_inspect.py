"""Inspect FIR xlsx schema across years 2020-2024 to detect structural variations.
Opens one sample file per year (South Glengarry, code 0101) and reports:
- Sheet names and count
- For key sheets (Schedule 26, 10, 40, 80, 60, 74): headers, row count, sample data
"""
import zipfile
import os
import glob
import io
import json
import openpyxl

BASE = os.path.join("data", "FIR Data")
YEARS = [2020, 2021, 2022, 2023, 2024]
TARGET_CODE = "0101"  # South Glengarry - present in all 5 years

# Key schedules we need for the ETL
KEY_SHEETS_PATTERNS = [
    "SLC 26",   # Tax Rates / Assessment 
    "SLC 10",   # Revenue
    "SLC 40",   # Expenses
    "SLC 80",   # Statistics
    "SLC 60",   # Reserves
    "SLC 74",   # Debt
    "SLC 70",   # Balance Sheet
    "SLC 51",   # Capital Assets (TCA)
    "SLC 61",   # Development Charges (Obligatory)
    "SLC 62",   # Development Charges (Discretionary)
]

results = {}

for year in YEARS:
    yr2 = str(year)[2:]
    pattern = os.path.join(BASE, str(year), f"FI{yr2}{TARGET_CODE}*.zip")
    matches = glob.glob(pattern)
    if not matches:
        results[year] = {"error": f"No file for code {TARGET_CODE}"}
        continue
    
    fpath = matches[0]
    fname = os.path.basename(fpath)
    
    try:
        with zipfile.ZipFile(fpath) as z:
            xlsx_files = [f for f in z.namelist() if f.endswith(".xlsx")]
            if not xlsx_files:
                results[year] = {"error": "no xlsx in zip"}
                continue
            
            xlsx_name = xlsx_files[0]
            with z.open(xlsx_name) as xlsx_file:
                wb = openpyxl.load_workbook(io.BytesIO(xlsx_file.read()), read_only=True, data_only=True)
                
                year_info = {
                    "file": fname,
                    "xlsx": xlsx_name,
                    "sheet_count": len(wb.sheetnames),
                    "sheets": wb.sheetnames,
                    "key_sheets": {}
                }
                
                # Inspect key sheets
                for pattern_name in KEY_SHEETS_PATTERNS:
                    # Find matching sheet
                    matching = [s for s in wb.sheetnames if pattern_name.lower().replace(" ", "") in s.lower().replace(" ", "")]
                    if not matching:
                        # Try looser match
                        matching = [s for s in wb.sheetnames if pattern_name.split()[-1] in s]
                    
                    if matching:
                        sheet_name = matching[0]
                        ws = wb[sheet_name]
                        
                        # Read first 10 rows to understand structure
                        rows = []
                        row_count = 0
                        for i, row in enumerate(ws.iter_rows(values_only=True)):
                            row_count += 1
                            if i < 15:
                                # Convert row to strings for JSON serialization
                                rows.append([str(c) if c is not None else "" for c in row])
                        
                        year_info["key_sheets"][pattern_name] = {
                            "matched_name": sheet_name,
                            "row_count": row_count,
                            "sample_rows": rows
                        }
                    else:
                        year_info["key_sheets"][pattern_name] = {"matched_name": None}
                
                results[year] = year_info
                wb.close()
    except Exception as e:
        results[year] = {"error": str(e), "file": fname}

# Write results
with open("data/fir_schema_inspection.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Print summary
for year, info in results.items():
    if "error" in info:
        print(f"{year}: ERROR - {info['error']}")
    else:
        print(f"\n=== {year} ({info['sheet_count']} sheets) ===")
        print(f"  File: {info['file']}")
        for sp, details in info["key_sheets"].items():
            if details["matched_name"]:
                print(f"  {sp} -> '{details['matched_name']}' ({details['row_count']} rows)")
            else:
                print(f"  {sp} -> NOT FOUND")

print("\nFull results in data/fir_schema_inspection.json")
