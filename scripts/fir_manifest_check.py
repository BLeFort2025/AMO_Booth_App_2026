"""Cross-reference missing FIR files with download_manifest.csv to diagnose root cause."""
import os
import re
import csv
import json

# Load the audit results
with open("data/fir_audit.json", "r", encoding="utf-8") as f:
    audit = json.load(f)

# Load the download manifest
manifest_entries = {}  # year -> set of codes found in manifest
with open("data/FIR Data/download_manifest.csv", "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    print(f"Manifest columns: {fieldnames}")
    
    for row in reader:
        url = row.get("url", "")
        filename = row.get("filename", "") or row.get("file_name", "")
        year_str = row.get("year", "")
        
        # Try to extract FIR code from filename
        m = re.search(r"FI(\d{2})(\d{4})", filename)
        if m:
            yr2 = m.group(1)
            code = m.group(2)
            year = 2000 + int(yr2)
            if year not in manifest_entries:
                manifest_entries[year] = set()
            manifest_entries[year].add(code)

# Check if missing files appear in manifest
print("\n=== Diagnosis: Are missing files in the manifest? ===")
for year_str, items in audit["missing"].items():
    year = int(year_str)
    if year not in manifest_entries:
        print(f"\n{year}: NO manifest entries at all for this year!")
        continue
    
    in_manifest = 0
    not_in_manifest = 0
    for item in items:
        code = item["code"]
        if code in manifest_entries.get(year, set()):
            in_manifest += 1
        else:
            not_in_manifest += 1
    
    print(f"\n{year}: {len(items)} missing files")
    print(f"  In manifest but not downloaded: {in_manifest}")
    print(f"  Not in manifest at all: {not_in_manifest}")
    
    # List a few not-in-manifest ones
    if not_in_manifest > 0:
        print(f"  Examples NOT in manifest:")
        count = 0
        for item in items:
            if item["code"] not in manifest_entries.get(year, set()):
                print(f"    {item['code']} {item['name']}")
                count += 1
                if count >= 5:
                    print(f"    ... and {not_in_manifest - 5} more")
                    break

# Also check: how many manifest entries per year?
print("\n=== Manifest entry counts per year ===")
for year in sorted(manifest_entries.keys()):
    if year >= 2020:
        print(f"  {year}: {len(manifest_entries[year])} entries")
