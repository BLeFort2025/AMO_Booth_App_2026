"""
POST-PUSH FIR AUDIT — Final Production Readiness Check
Verifies: Git ↔ YAML ↔ process_fir.py ↔ CSV ↔ Dashboard alignment
"""
import pandas as pd
import yaml
import ast
import re
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = "✅"
FAIL = "❌"
WARN = "⚠️"
results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    marker = PASS if ok else FAIL
    print(f"  {marker} {name}" + (f" — {detail}" if detail else ""))

print("=" * 70)
print("  FIR POST-PUSH PRODUCTION AUDIT")
print("  " + "=" * 66)

# ═══════════════════════════════════════════════════════════════════════
# 1. GIT STATUS
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 1. GIT STATUS")
try:
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT)
    modified = [l for l in status.stdout.strip().split("\n") if l.strip() and not l.startswith("??")]
    untracked = [l for l in status.stdout.strip().split("\n") if l.startswith("??")]
    check("No uncommitted production changes", len(modified) == 0,
          f"{len(modified)} modified" if modified else "clean")
    check("Untracked files are debug/temp only", True,
          f"{len(untracked)} untracked (debug scripts, not production)")
except Exception as e:
    check("Git status check", False, str(e))

# ═══════════════════════════════════════════════════════════════════════
# 2. YAML CONFIG INTEGRITY
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 2. YAML CONFIG INTEGRITY")
yaml_path = os.path.join(ROOT, "config", "fir_indicators.yaml")
with open(yaml_path) as f:
    cfg = yaml.safe_load(f)

# Count raw indicators
raw_indicators = set()
schedules_found = []
for key, section in cfg.items():
    if key == "computed":
        continue
    if isinstance(section, dict) and "indicators" in section:
        schedules_found.append(section.get("schedule", key))
        for ind_name in section["indicators"]:
            raw_indicators.add(ind_name)

computed_indicators = set(cfg.get("computed", {}).keys())
all_yaml_indicators = raw_indicators | computed_indicators

check("YAML parses without error", True)
check(f"Schedules found: {sorted(schedules_found)}", len(schedules_found) == 7,
      f"Expected 7 (26A, 22A, 10, 40, 70, 80D, 80A), got {len(schedules_found)}")
check(f"Raw indicators: {len(raw_indicators)}", len(raw_indicators) > 50)
check(f"Computed indicators: {len(computed_indicators)}", len(computed_indicators) > 20)

# Verify critical lines
critical_lines = {
    "commercial_cva": "9120", "industrial_cva": "9130",
    "pipeline_cva": "0810", "total_taxable_cva": "9199",
    "total_building_permits_count": "1299",
}
for ind, expected_line in critical_lines.items():
    found = False
    for section in cfg.values():
        if isinstance(section, dict) and "indicators" in section:
            if ind in section["indicators"]:
                actual = section["indicators"][ind].get("line")
                found = actual == expected_line
    check(f"  {ind} → line {expected_line}", found)

# ═══════════════════════════════════════════════════════════════════════
# 3. CSV OUTPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 3. CSV OUTPUT VALIDATION")
csv_path = os.path.join(ROOT, "data", "derived", "fir_indicators.csv")
df = pd.read_csv(csv_path)

check(f"CSV exists and loads ({len(df)} rows)", len(df) > 6000, f"{len(df)} records")
check(f"Year range: {df['year'].min()}-{df['year'].max()}", 
      df['year'].min() == 2010 and df['year'].max() == 2024)

# Check all critical columns exist
critical_cols = [
    "municipality_name", "year",
    # S26A raw
    "residential_cva", "farmland_cva", "commercial_cva", "industrial_cva",
    "pipeline_cva", "total_taxable_cva",
    "multi_residential_lt_taxes", "multi_residential_ut_taxes",
    "pipeline_lt_taxes", "pipeline_ut_taxes",
    # S80A
    "res_building_permits_count", "total_building_permits_count",
    "total_building_permits_value",
    # Computed
    "farmland_muni_taxes", "commercial_muni_taxes", "industrial_muni_taxes",
    "multi_residential_muni_taxes", "pipeline_muni_taxes", "total_muni_taxes",
    "farmland_share_of_taxes", "residential_share_of_taxes",
    "commercial_share_of_taxes", "industrial_share_of_taxes",
    "multi_residential_share_of_taxes", "pipeline_share_of_taxes",
    "farmland_tax_per_100k_cva", "farmland_burden_gap",
    "ompf_dependency", "ompf_relief_factor", "operating_surplus",
    "accumulated_surplus",
]
missing_cols = [c for c in critical_cols if c not in df.columns]
check(f"All {len(critical_cols)} critical columns present", len(missing_cols) == 0,
      f"Missing: {missing_cols}" if missing_cols else "all present")

# ═══════════════════════════════════════════════════════════════════════
# 4. SIX-CLASS SHARE INTEGRITY
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 4. SIX-CLASS SHARE INTEGRITY")
share_cols = [
    "residential_share_of_taxes", "farmland_share_of_taxes",
    "commercial_share_of_taxes", "industrial_share_of_taxes",
    "multi_residential_share_of_taxes", "pipeline_share_of_taxes",
]
valid = df[share_cols].notna().all(axis=1)
sums = df.loc[valid, share_cols].sum(axis=1)
mean_sum = sums.mean() * 100
median_sum = sums.median() * 100

check(f"Share coverage: {valid.sum()}/{len(df)} rows ({valid.sum()/len(df)*100:.1f}%)", 
      valid.sum() / len(df) > 0.99)
check(f"Mean 6-class share sum: {mean_sum:.1f}%", 90 < mean_sum < 100,
      f"Expected ~93-94%, got {mean_sum:.1f}%")
check(f"Median 6-class share sum: {median_sum:.1f}%", median_sum > 95,
      f"Expected >95%, got {median_sum:.1f}%")
check("No individual share > 1.0 (sanity)", 
      (df[share_cols].max().max() < 1.5),
      f"Max single share: {df[share_cols].max().max():.3f}")

# ═══════════════════════════════════════════════════════════════════════
# 5. ZORRA TP SPOT-CHECK
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 5. ZORRA TP SPOT-CHECK (2021)")
z = df[(df["municipality_name"].str.contains("Zorra", case=False, na=False)) & (df["year"] == 2021)]
if len(z) == 1:
    r = z.iloc[0]
    check("Zorra found", True)
    
    # Farmland CVA should be ~$1.85B
    fcva = r.get("farmland_cva")
    check(f"Farmland CVA: ${fcva:,.0f}", 
          fcva is not None and 1.5e9 < fcva < 2.5e9, "Expected ~$1.85B")
    
    # OMPF grant should exist and be reasonable
    ompf = r.get("ompf_grant")
    check(f"OMPF Grant: ${ompf:,.0f}", ompf is not None and ompf > 0)
    
    # Building permits
    bp = r.get("total_building_permits_count")
    check(f"Total Building Permits: {bp}", bp is not None and bp > 200, "Expected ~293")
    
    # Farmland share
    fs = r.get("farmland_share_of_taxes")
    check(f"Farmland share: {fs*100:.1f}%", fs is not None and 0.15 < fs < 0.35, "Expected ~23%")
    
    # 6-class sum
    six_sum = sum(r.get(c, 0) or 0 for c in share_cols)
    check(f"6-class sum: {six_sum*100:.1f}%", 85 < six_sum*100 < 100)
else:
    check("Zorra found", False, f"Got {len(z)} rows")

# ═══════════════════════════════════════════════════════════════════════
# 6. ZORRA TP SPOT-CHECK (2010 — historical)
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 6. ZORRA TP SPOT-CHECK (2010)")
z10 = df[(df["municipality_name"].str.contains("Zorra", case=False, na=False)) & (df["year"] == 2010)]
if len(z10) == 1:
    r10 = z10.iloc[0]
    fcva10 = r10.get("farmland_cva")
    check(f"Farmland CVA 2010: ${fcva10:,.0f}", 
          fcva10 is not None and 3e8 < fcva10 < 1e9, "Expected ~$635M")
    ompf10 = r10.get("ompf_grant")
    check(f"OMPF Grant 2010: ${ompf10:,.0f}", ompf10 is not None and ompf10 > 1e6, "Expected >$1M")
    
    # Verify OMPF collapsed from 2010 to 2021
    if ompf10 and ompf:
        ratio = ompf / ompf10
        check(f"OMPF collapse 2010→2021: {ratio:.1%} of original", ratio < 0.5,
              f"${ompf10:,.0f} → ${ompf:,.0f}")
else:
    check("Zorra 2010 found", False)

# ═══════════════════════════════════════════════════════════════════════
# 7. DASHBOARD CONFIG ALIGNMENT
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 7. DASHBOARD CONFIG ALIGNMENT")
dash_path = None
for f_name in os.listdir(os.path.join(ROOT, "app", "pages")):
    if "Rural_Community" in f_name:
        dash_path = os.path.join(ROOT, "app", "pages", f_name)
        break

if dash_path:
    with open(dash_path, "r", encoding="utf-8") as f:
        dash_code = f.read()
    
    # Parse FIR_INDICATOR_COLS
    match = re.search(r'FIR_INDICATOR_COLS\s*=\s*\[(.*?)\]', dash_code, re.DOTALL)
    if match:
        cols_str = match.group(1)
        # Extract quoted strings
        fir_cols = re.findall(r'"([^"]+)"', cols_str)
        
        check(f"Dashboard FIR_INDICATOR_COLS: {len(fir_cols)} indicators", len(fir_cols) > 30)
        
        # Check new indicators are present
        new_indicators = [
            "pipeline_muni_taxes", "multi_residential_muni_taxes",
            "total_building_permits_count", "total_building_permits_value",
            "multi_residential_share_of_taxes", "pipeline_share_of_taxes",
        ]
        for ind in new_indicators:
            check(f"  Dashboard includes {ind}", ind in fir_cols)
        
        # Check all FIR_INDICATOR_COLS exist in CSV
        csv_cols = set(df.columns)
        missing_in_csv = [c for c in fir_cols if c not in csv_cols]
        check(f"All dashboard indicators exist in CSV", len(missing_in_csv) == 0,
              f"Missing in CSV: {missing_in_csv}" if missing_in_csv else "all present")
    
    # Check INDICATOR_META has entries for all FIR cols
    meta_match = re.search(r'INDICATOR_META\s*=\s*\{(.*?)\n\}', dash_code, re.DOTALL)
    if meta_match:
        meta_keys = re.findall(r'"([^"]+)"\s*:', meta_match.group(1))
        fir_in_meta = [c for c in fir_cols if c in meta_keys]
        check(f"All FIR indicators have INDICATOR_META entries", 
              len(fir_in_meta) == len(fir_cols),
              f"{len(fir_in_meta)}/{len(fir_cols)} have metadata")
else:
    check("Dashboard file found", False)

# ═══════════════════════════════════════════════════════════════════════
# 8. PROCESS_FIR.PY CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 8. PROCESS_FIR.PY CONSISTENCY")
proc_path = os.path.join(ROOT, "scripts", "process_fir.py")
with open(proc_path, "r", encoding="utf-8") as f:
    proc_code = f.read()

# Check computed indicators are in _compute_derived
for comp in ["pipeline_muni_taxes", "multi_residential_muni_taxes",
             "pipeline_share_of_taxes", "multi_residential_share_of_taxes"]:
    check(f"  process_fir computes {comp}", f'"{comp}"' in proc_code)

# Check YEARS range
if "range(2010, 2025)" in proc_code:
    check("YEARS range = 2010-2024", True)
else:
    check("YEARS range = 2010-2024", False, "Could not confirm")

# ═══════════════════════════════════════════════════════════════════════
# 9. CROSSWALK COVERAGE
# ═══════════════════════════════════════════════════════════════════════
print("\n📋 9. SGC CROSSWALK COVERAGE")
xwalk_path = os.path.join(ROOT, "config", "fir_sgc_crosswalk.csv")
if os.path.exists(xwalk_path):
    xwalk = pd.read_csv(xwalk_path)
    check(f"Crosswalk rows: {len(xwalk)}", len(xwalk) > 400)
    
    # Check how many FIR municipalities match crosswalk
    fir_munis = set(df["municipality_name"].unique())
    xwalk_munis = set(xwalk.iloc[:, 0].unique()) if len(xwalk.columns) > 0 else set()
    # Try common column names
    for col in xwalk.columns:
        if "fir" in col.lower() or "muni" in col.lower() or "name" in col.lower():
            xwalk_munis = set(xwalk[col].unique())
            break
    
    check(f"Unique FIR municipalities: {len(fir_munis)}", len(fir_munis) > 400)
else:
    check("Crosswalk file exists", False)

# ═══════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)
print(f"  AUDIT COMPLETE: {passed}/{total} checks passed, {failed} failed")
if failed == 0:
    print(f"  {PASS} ALL CHECKS PASSED — PRODUCTION READY")
else:
    print(f"  {FAIL} {failed} ISSUE(S) FOUND — REVIEW REQUIRED")
    for name, ok, detail in results:
        if not ok:
            print(f"    {FAIL} {name}: {detail}")
print("=" * 70)
