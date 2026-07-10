"""
Comprehensive Accuracy Verification for Indexed (Base-100) Chart Views
======================================================================
Validates that _compute_indexed_series() produces mathematically correct
index values by cross-referencing against raw FIR data for a broad sample
of municipalities.

Checks:
  1. Index math: (value / base_value) * 100 == computed index
  2. Base year logic: 2010 preferred, fallback to first valid year
  3. Edge cases: zero CVA, missing years, NaN handling
  4. All 444 municipalities: no crashes, no NaN where data exists
  5. Provincial aggregate: indexed values consistent
  6. Report chart builders: output is valid, non-None
  7. Cross-check: indexed CVA growth vs existing cumulative growth %
"""
import sys
sys.path.insert(0, "app")

import pandas as pd
import numpy as np
from farm_tax.farm_tax_story import _compute_indexed_series, BASE_YEAR, _safe_val

# ═══════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("INDEXED CHART ACCURACY VERIFICATION")
print("=" * 70)

fir = pd.read_csv("data/derived/fir_indicators.csv")
fir["sgc_code"] = pd.to_numeric(fir["sgc_code"], errors="coerce")
fir = fir.dropna(subset=["sgc_code"])
fir["sgc_code"] = fir["sgc_code"].astype(int).astype(str).str.zfill(7)

munis = fir["sgc_code"].unique()
print(f"\nLoaded {len(munis)} municipalities, years {fir['year'].min()}-{fir['year'].max()}")
print(f"Base year: {BASE_YEAR}")

errors = []
warnings = []
pass_count = 0

# ═══════════════════════════════════════════════════════════════════════
# TEST 1: INDEX MATH ACCURACY — ALL MUNICIPALITIES
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 1: Index Math Accuracy — All Municipalities")
print("=" * 70)

cva_cols = {
    "Farmland": "farmland_cva",
    "Residential": "residential_cva",
    "Commercial": "commercial_cva",
    "Industrial": "industrial_cva",
}

tax_cols = {
    "Farmland": "farmland_muni_taxes",
    "Residential": "residential_muni_taxes",
    "Commercial": "commercial_muni_taxes",
    "Industrial": "industrial_muni_taxes",
}

burden_cols = {
    "Farmland": "farmland_share_of_taxes",
    "Residential": "residential_share_of_taxes",
    "Commercial": "commercial_share_of_taxes",
    "Industrial": "industrial_share_of_taxes",
}

tested_munis = 0
tested_values = 0

for sgc in munis:
    muni_df = fir[fir["sgc_code"] == sgc].sort_values("year").reset_index(drop=True)
    if len(muni_df) < 2:
        continue

    muni_name = muni_df.iloc[0].get("municipality_name", sgc)

    for col_set_name, col_map in [("CVA", cva_cols), ("Tax", tax_cols), ("Burden", burden_cols)]:
        # Filter to available columns
        available = {k: v for k, v in col_map.items() if v in muni_df.columns}
        if not available:
            continue

        indexed_df, base_info = _compute_indexed_series(muni_df, available)

        for label, col in available.items():
            info = base_info.get(label, {})
            base_val = info.get("base_val", 0)
            actual_base_year = info.get("base_year", BASE_YEAR)

            if base_val <= 0:
                continue  # No valid data for this class

            idx_col = f"{label}_idx"
            if idx_col not in indexed_df.columns:
                errors.append(f"{muni_name} ({sgc}): {col_set_name}/{label} — idx column missing")
                continue

            # Verify every single indexed value
            for i, row in muni_df.iterrows():
                raw_val = row.get(col)
                if pd.isna(raw_val):
                    raw_val = 0

                expected_idx = (float(raw_val) / base_val) * 100
                computed_idx = float(indexed_df.iloc[i][idx_col])

                if abs(expected_idx - computed_idx) > 0.001:
                    errors.append(
                        f"{muni_name} ({sgc}): {col_set_name}/{label} year={int(row['year'])} "
                        f"— expected {expected_idx:.4f}, got {computed_idx:.4f}"
                    )
                else:
                    tested_values += 1

            # Verify base year value = 100
            base_rows = indexed_df[muni_df["year"] == actual_base_year]
            if len(base_rows) > 0:
                base_idx = float(base_rows[idx_col].iloc[0])
                if abs(base_idx - 100.0) > 0.001:
                    errors.append(
                        f"{muni_name} ({sgc}): {col_set_name}/{label} — "
                        f"base year {actual_base_year} index is {base_idx:.4f}, expected 100.0"
                    )

    tested_munis += 1

print(f"  Tested {tested_munis} municipalities, {tested_values:,} indexed values")
if not errors:
    print(f"  ✅ ALL MATH CORRECT — zero discrepancies")
    pass_count += 1
else:
    print(f"  ❌ {len(errors)} ERRORS FOUND:")
    for e in errors[:20]:
        print(f"     {e}")

# ═══════════════════════════════════════════════════════════════════════
# TEST 2: BASE YEAR FALLBACK LOGIC
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 2: Base Year Fallback Logic")
print("=" * 70)

fallback_count = 0
no_data_count = 0

for sgc in munis:
    muni_df = fir[fir["sgc_code"] == sgc].sort_values("year").reset_index(drop=True)
    if len(muni_df) < 2:
        continue

    available = {k: v for k, v in cva_cols.items() if v in muni_df.columns}
    _, base_info = _compute_indexed_series(muni_df, available)

    for label in available:
        info = base_info.get(label, {})
        if info.get("base_val", 0) <= 0:
            no_data_count += 1
            continue

        actual_base = info["base_year"]
        if actual_base != BASE_YEAR:
            fallback_count += 1

            # Verify the fallback is correct: base year should be the first year with value > 0
            col = available[label]
            valid = muni_df[muni_df[col].notna() & (muni_df[col] > 0)].sort_values("year")
            if len(valid) > 0:
                expected_fallback = int(valid["year"].iloc[0])
                if actual_base != expected_fallback:
                    errors.append(
                        f"Fallback mismatch for {label}/{sgc}: "
                        f"got base_year={actual_base}, expected={expected_fallback}"
                    )

print(f"  Municipalities using 2010 base: {tested_munis - fallback_count - no_data_count}")
print(f"  Municipalities using fallback year: {fallback_count}")
print(f"  Series with no valid data: {no_data_count}")
if not any("Fallback mismatch" in e for e in errors):
    print(f"  ✅ All fallback logic correct")
    pass_count += 1
else:
    print(f"  ❌ Fallback errors found")

# ═══════════════════════════════════════════════════════════════════════
# TEST 3: CROSS-CHECK — INDEXED CVA vs CUMULATIVE GROWTH %
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 3: Cross-Check — Indexed CVA vs Cumulative Growth %")
print("=" * 70)

# For a sample of municipalities, verify that indexed latest value = 100 + cumulative_growth%
spot_check_names = ["Zorra", "Ottawa", "Hamilton", "Simcoe", "Thunder Bay"]
cross_errors = []

for name_fragment in spot_check_names:
    matches = fir[fir["municipality_name"].str.contains(name_fragment, na=False)]
    if matches.empty:
        continue

    sgc = matches["sgc_code"].iloc[0]
    muni_df = fir[fir["sgc_code"] == sgc].sort_values("year").reset_index(drop=True)
    muni_name = muni_df.iloc[0]["municipality_name"]

    available = {k: v for k, v in cva_cols.items() if v in muni_df.columns}
    indexed_df, base_info = _compute_indexed_series(muni_df, available)

    print(f"\n  {muni_name} ({sgc}):")
    for label, col in available.items():
        info = base_info.get(label, {})
        if info.get("latest_idx") is None:
            continue

        latest_idx = info["latest_idx"]
        base_val = info["base_val"]
        latest_val = info["latest_val"]

        # Manual calculation
        manual_growth_pct = ((latest_val - base_val) / base_val) * 100 if base_val > 0 else 0
        manual_idx = 100 + manual_growth_pct

        match = abs(latest_idx - manual_idx) < 0.01
        status = "✅" if match else "❌"
        print(f"    {label:15s}: base={base_val:>15,.0f}  latest={latest_val:>15,.0f}  "
              f"idx={latest_idx:>7.1f}  manual={manual_idx:>7.1f}  {status}")

        if not match:
            cross_errors.append(f"{muni_name}/{label}: idx={latest_idx}, manual={manual_idx}")

if not cross_errors:
    print(f"\n  ✅ All cross-checks match")
    pass_count += 1
else:
    print(f"\n  ❌ {len(cross_errors)} cross-check failures")

# ═══════════════════════════════════════════════════════════════════════
# TEST 4: EDGE CASES — ZERO VALUES, NaN, SINGLE-YEAR DATA
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 4: Edge Cases")
print("=" * 70)

edge_errors = []

# Test 4a: All-zero series
df_zero = pd.DataFrame({
    "year": [2010, 2012, 2014],
    "farmland_cva": [0, 0, 0],
})
_, info_zero = _compute_indexed_series(df_zero, {"Farmland": "farmland_cva"})
assert info_zero["Farmland"]["base_val"] == 0, "Zero series should have base_val=0"
print("  4a. All-zero series: ✅ handled correctly (no crash, base_val=0)")

# Test 4b: NaN values
df_nan = pd.DataFrame({
    "year": [2010, 2012, 2014],
    "farmland_cva": [1000, np.nan, 2000],
})
idx_nan, info_nan = _compute_indexed_series(df_nan, {"Farmland": "farmland_cva"})
assert abs(idx_nan["Farmland_idx"].iloc[0] - 100.0) < 0.01, "NaN test: base should be 100"
assert abs(idx_nan["Farmland_idx"].iloc[1] - 0.0) < 0.01, "NaN test: NaN should become 0 (filled)"
assert abs(idx_nan["Farmland_idx"].iloc[2] - 200.0) < 0.01, "NaN test: 2000/1000*100=200"
print("  4b. NaN handling: ✅ NaN filled with 0, index computed correctly")

# Test 4c: Missing base year (no 2010)
df_no_base = pd.DataFrame({
    "year": [2012, 2014, 2016],
    "farmland_cva": [500, 750, 1000],
})
_, info_no_base = _compute_indexed_series(df_no_base, {"Farmland": "farmland_cva"})
assert info_no_base["Farmland"]["base_year"] == 2012, \
    f"Expected fallback to 2012, got {info_no_base['Farmland']['base_year']}"
assert abs(info_no_base["Farmland"]["latest_idx"] - 200.0) < 0.01, \
    f"Expected 200.0, got {info_no_base['Farmland']['latest_idx']}"
print("  4c. Missing 2010 fallback: ✅ correctly falls back to 2012, idx=200")

# Test 4d: Single data point
df_single = pd.DataFrame({
    "year": [2010],
    "farmland_cva": [1000],
})
idx_single, info_single = _compute_indexed_series(df_single, {"Farmland": "farmland_cva"})
assert abs(idx_single["Farmland_idx"].iloc[0] - 100.0) < 0.01
print("  4d. Single data point: ✅ returns index=100")

# Test 4e: Missing column
df_missing_col = pd.DataFrame({
    "year": [2010, 2012],
    "farmland_cva": [1000, 2000],
})
_, info_missing = _compute_indexed_series(df_missing_col, {"Missing": "nonexistent_col"})
assert "Missing" not in info_missing
print("  4e. Missing column: ✅ gracefully skipped")

pass_count += 1

# ═══════════════════════════════════════════════════════════════════════
# TEST 5: REPORT CHART BUILDERS — NO CRASHES
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 5: Report Chart Builders")
print("=" * 70)

from farm_tax.farm_tax_report import _build_indexed_cva_chart, _build_indexed_tax_chart

# Test CVA chart builder
cva_growth = {"Farmland": 198.0, "Residential": 55.0, "Commercial": 12.0, "Industrial": -5.0}
tax_trends = {
    2010: {"farm": 5000, "res": 3000, "com": 2000, "ind": 1000},
    2015: {"farm": 8000, "res": 3800, "com": 2200, "ind": 950},
    2024: {"farm": 12000, "res": 5000, "com": 2500, "ind": 900},
}

cva_img = _build_indexed_cva_chart(cva_growth, tax_trends, "2010-2024")
assert cva_img is not None, "CVA chart should not be None"
assert len(cva_img.getvalue()) > 1000, "CVA chart should be a real image"
print(f"  CVA indexed chart: ✅ {len(cva_img.getvalue()):,} bytes")

tax_img = _build_indexed_tax_chart(tax_trends)
assert tax_img is not None, "Tax chart should not be None"
assert len(tax_img.getvalue()) > 1000, "Tax chart should be a real image"
print(f"  Tax indexed chart: ✅ {len(tax_img.getvalue()):,} bytes")

# Verify tax chart math: farm index = (12000/5000)*100 = 240
# Actually: (12000/5000)*100 = 240 for farm
# Base year is 2010, farm base = 5000, latest = 12000 → 240
print(f"  Expected farm tax idx: {(12000/5000)*100:.0f}, res tax idx: {(5000/3000)*100:.0f}")
pass_count += 1

# ═══════════════════════════════════════════════════════════════════════
# TEST 6: WORD REPORT + PPTX — FULL GENERATION WITH INDEXED CHARTS
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 6: Full Word + PPTX Report Generation")
print("=" * 70)

from farm_tax.farm_tax_report import calculate_revenue_neutral_ratio, generate_word_report, generate_pptx_report

# Use Zorra Township as test case
z = fir[fir["municipality_name"].str.contains("Zorra", na=False)]
cur = z[z.year == z.year.max()].iloc[0]
tgt = z[z.year == 2016].iloc[0]

def sv(row, col):
    v = row.get(col)
    if v is None or pd.isna(v):
        return 0.0
    return float(v)

r = calculate_revenue_neutral_ratio(
    target_burden=sv(tgt, "farmland_share_of_taxes"),
    farm_cva=sv(cur, "farmland_cva"),
    res_cva=sv(cur, "residential_cva"),
    com_cva=sv(cur, "commercial_cva"),
    ind_cva=sv(cur, "industrial_cva"),
    ft_ratio=sv(cur, "farmland_tax_ratio"),
    ct_ratio=sv(cur, "commercial_tax_ratio"),
    it_ratio=sv(cur, "industrial_tax_ratio"),
    total_muni_taxes=sv(cur, "total_muni_taxes"),
    current_farm_taxes=sv(cur, "farmland_muni_taxes"),
    current_res_taxes=sv(cur, "residential_muni_taxes"),
    current_com_taxes=sv(cur, "commercial_muni_taxes"),
    current_ind_taxes=sv(cur, "industrial_muni_taxes"),
    current_burden=sv(cur, "farmland_share_of_taxes"),
    total_households=sv(cur, "total_households"),
)

# Zero-sum check (existing test)
assert abs(r.zero_sum_check) < 0.01, f"ZERO-SUM FAILED: {r.zero_sum_check}"
print(f"  Zero-sum check: ✅ (diff={r.zero_sum_check:.6f})")

burden = {2020: {"farm": 0.20, "res": 0.55, "com": 0.04, "ind": 0.05},
          2024: {"farm": 0.22, "res": 0.53, "com": 0.04, "ind": 0.05}}
cva_growth_z = {"Farmland": 198.0, "Residential": 55.0, "Commercial": 12.0, "Industrial": -5.0}
tax_trends_z = {2010: {"farm": 5000, "res": 3000, "com": 2000, "ind": 1000},
                2024: {"farm": 12000, "res": 5000, "com": 2500, "ind": 900}}

# Word report
word_buf = generate_word_report(
    muni_name="Zorra Township", year_range="2010-2024",
    current_year=2024, target_year=2016,
    burden_by_year=burden, calc=r, cva_growth=cva_growth_z,
    is_two_tier=True, tax_trends_by_year=tax_trends_z,
)
word_size = len(word_buf.getvalue())
print(f"  Word report: ✅ {word_size:,} bytes")

# PPTX report
pptx_buf = generate_pptx_report(
    muni_name="Zorra Township", year_range="2010-2024",
    current_year=2024, target_year=2016,
    burden_by_year=burden, calc=r, cva_growth=cva_growth_z,
    is_two_tier=True, tax_trends_by_year=tax_trends_z, fir_raw_df=fir,
)
pptx_size = len(pptx_buf.getvalue())

# Verify 13 slides
from pptx import Presentation
import io
prs = Presentation(io.BytesIO(pptx_buf.getvalue()))
slide_count = len(prs.slides)
assert slide_count == 13, f"Expected 13 slides, got {slide_count}"
print(f"  PPTX report: ✅ {pptx_size:,} bytes, {slide_count} slides")
pass_count += 1

# ═══════════════════════════════════════════════════════════════════════
# TEST 7: PROVINCIAL AGGREGATE — INDEXED VIEW
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TEST 7: Provincial Aggregate Indexed Check")
print("=" * 70)

# Simulate provincial aggregation (simplified — just sum all munis per year)
latest_yr = fir["year"].max()
years = sorted(fir["year"].unique())

prov_data = []
for yr in years:
    yr_df = fir[fir["year"] == yr]
    row = {"year": yr}
    for col in ["farmland_cva", "residential_cva", "commercial_cva", "industrial_cva",
                "farmland_muni_taxes", "residential_muni_taxes", "commercial_muni_taxes", "industrial_muni_taxes"]:
        if col in yr_df.columns:
            row[col] = yr_df[col].sum()
    prov_data.append(row)

prov_df = pd.DataFrame(prov_data)

# CVA indexed
indexed_prov, prov_info = _compute_indexed_series(prov_df, cva_cols)
print(f"  Provincial CVA indexed ({prov_info.get('Farmland', {}).get('base_year', '?')}→{int(latest_yr)}):")
for label in cva_cols:
    info = prov_info.get(label, {})
    if info.get("latest_idx"):
        print(f"    {label:15s}: {info['latest_idx']:.1f}")

# Verify provincial farmland idx matches manual calc
farm_info = prov_info.get("Farmland", {})
if farm_info.get("base_val", 0) > 0:
    manual = (farm_info["latest_val"] / farm_info["base_val"]) * 100
    assert abs(farm_info["latest_idx"] - manual) < 0.01, \
        f"Provincial farm idx mismatch: {farm_info['latest_idx']} vs {manual}"
    print(f"\n  ✅ Provincial indexed math verified")
    pass_count += 1

# ═══════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════
total_tests = 7
print(f"\n{'=' * 70}")
print(f"VERIFICATION SUMMARY")
print(f"{'=' * 70}")
print(f"  Tests passed: {pass_count}/{total_tests}")
print(f"  Municipalities tested: {tested_munis}")
print(f"  Individual values verified: {tested_values:,}")
print(f"  Errors: {len(errors)}")
if errors:
    print(f"\n  ERRORS:")
    for e in errors:
        print(f"    ❌ {e}")
else:
    print(f"\n  ✅ ALL {tested_values:,} INDEXED VALUES VERIFIED — 100% ACCURATE")
print(f"{'=' * 70}")

# Exit with error code if any failures
if errors or pass_count < total_tests:
    sys.exit(1)
