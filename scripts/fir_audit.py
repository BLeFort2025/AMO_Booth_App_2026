"""Audit FIR data files across years - compact output."""
import os
import re
import json

BASE = os.path.join("data", "FIR Data")
YEARS = [2020, 2021, 2022, 2023, 2024]

year_codes = {}
all_names = {}

for year in YEARS:
    ydir = os.path.join(BASE, str(year))
    codes = {}
    for f in os.listdir(ydir):
        if f.endswith(".zip"):
            m = re.match(r"FI\d{2}(\d{4})\s+(.+?)\.zip", f)
            if m:
                codes[m.group(1)] = m.group(2)
                all_names[m.group(1)] = m.group(2)
    year_codes[year] = codes

all_codes = set()
for y in YEARS:
    all_codes.update(year_codes[y].keys())

# Build a compact JSON report
report = {
    "counts": {y: len(year_codes[y]) for y in YEARS},
    "total_unique": len(all_codes),
    "missing": {}
}

for year in YEARS:
    current = set(year_codes[year].keys())
    missing = sorted(all_codes - current)
    if missing:
        report["missing"][year] = [
            {"code": c, "name": all_names.get(c, "?"), 
             "present_in": [y for y in YEARS if c in year_codes[y]]}
            for c in missing
        ]

with open("data/fir_audit.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

# Print summary
print(json.dumps(report["counts"], indent=2))
print(f"Total unique: {report['total_unique']}")
for year, items in report["missing"].items():
    print(f"\nMissing from {year}: {len(items)}")
