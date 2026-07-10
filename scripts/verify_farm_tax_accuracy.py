"""
Farm Tax Calculator — Comprehensive Data Accuracy Verification
===============================================================
Scans 100% of municipalities for data quality and accuracy issues.

Checks:
  A1: CVA Growth calculation produces a value (no false N/A)
  A2: Revenue-neutral ratio math zero-sum verification
  A3: Tax share sums within tolerance (≤ 1.02)
  A4: No CVA=0 anomalies where taxes exist
  A5: Farmland tax ratio within [0, 0.25] bounds
  A6: Upper-tier data consistency
  A7: Year-over-year volatile jumps (>500% = flagged)
  A8: Provincial aggregate sanity checks
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

FIR_CSV = ROOT / "data" / "derived" / "fir_indicators.csv"

df = pd.read_csv(FIR_CSV, low_memory=False)
df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)

total_checks = 0
total_pass = 0
total_warn = 0
total_fail = 0
issues = []


def check(test_id, description, passed, detail="", severity="FAIL"):
    """Record a check result."""
    global total_checks, total_pass, total_warn, total_fail
    total_checks += 1
    if passed:
        total_pass += 1
    elif severity == "WARN":
        total_warn += 1
        issues.append((test_id, "WARN", description, detail))
    else:
        total_fail += 1
        issues.append((test_id, "FAIL", description, detail))


print("=" * 90)
print("FARM TAX CALCULATOR — COMPREHENSIVE DATA ACCURACY SCAN")
print("=" * 90)
print(f"Dataset: {len(df):,} rows, {df['fir_code'].nunique()} municipalities, "
      f"{int(df['year'].min())}–{int(df['year'].max())}")
print()

# ═══════════════════════════════════════════════════════════════════════════
# A1: CVA GROWTH — verify the fix works for all municipalities
# ═══════════════════════════════════════════════════════════════════════════
print("─" * 90)
print("A1: CVA GROWTH CALCULATION (post-fix verification)")
print("─" * 90)

cva_cols = {
    "Farmland": "farmland_cva",
    "Residential": "residential_cva",
    "Commercial": "commercial_cva",
    "Industrial": "industrial_cva",
}

# Replicate the FIXED growth logic
munis_with_farm = df[df["farmland_cva"].notna() & (df["farmland_cva"] > 0)]
valid_codes = set(munis_with_farm["sgc_code"].unique())

n_growable = 0
n_na_growth = 0
na_growth_munis = []

for sgc_code in valid_codes:
    muni_df = df[df["sgc_code"] == sgc_code].sort_values("year")
    if muni_df.empty:
        continue
    last_year = muni_df["year"].max()
    
    for label, col in cva_cols.items():
        if col not in muni_df.columns:
            continue
        valid_rows = muni_df[muni_df[col].notna() & (muni_df[col] > 0)]
        if valid_rows.empty:
            continue
        n_growable += 1
        base_val = float(valid_rows[col].iloc[0])
        last_rows = muni_df[muni_df["year"] == last_year]
        last_val = float(last_rows[col].iloc[0]) if len(last_rows) and pd.notna(last_rows[col].iloc[0]) else None
        if last_val is None or last_val <= 0 or base_val <= 0:
            n_na_growth += 1
            muni_name = muni_df["municipality_name"].iloc[0]
            na_growth_munis.append(f"{muni_name} ({label})")

check("A1.1", f"CVA growth computable for farm municipalities",
      n_na_growth == 0,
      f"{n_na_growth}/{n_growable} still show N/A: {', '.join(na_growth_munis[:5])}")
print(f"  A1.1: {n_growable} class-municipality pairs checked, {n_na_growth} N/A → "
      f"{'✅ PASS' if n_na_growth == 0 else '❌ FAIL'}")


# ═══════════════════════════════════════════════════════════════════════════
# A2: REVENUE-NEUTRAL RATIO ZERO-SUM VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A2: REVENUE-NEUTRAL RATIO MATH — ZERO-SUM VERIFICATION")
print("─" * 90)

from app.farm_tax.farm_tax_report import calculate_revenue_neutral_ratio

n_tested = 0
n_zero_sum_ok = 0
zero_sum_failures = []

# Test on latest year for each municipality with farm data
latest = df.sort_values("year").drop_duplicates("sgc_code", keep="last")
farm_munis = latest[
    latest["farmland_cva"].notna() & (latest["farmland_cva"] > 0) &
    latest["residential_cva"].notna() & (latest["residential_cva"] > 0) &
    latest["farmland_tax_ratio"].notna() & (latest["farmland_tax_ratio"] > 0) &
    latest["residential_muni_taxes"].notna() & (latest["residential_muni_taxes"] > 0) &
    latest["total_muni_taxes"].notna() & (latest["total_muni_taxes"] > 0) &
    latest["farmland_share_of_taxes"].notna() & (latest["farmland_share_of_taxes"] > 0)
]

for _, row in farm_munis.iterrows():
    # Use a target burden from an earlier year
    target_burden = max(0.01, row["farmland_share_of_taxes"] * 0.8)  # 80% of current
    
    calc = calculate_revenue_neutral_ratio(
        target_burden=target_burden,
        farm_cva=row.get("farmland_cva", 0),
        res_cva=row.get("residential_cva", 0),
        com_cva=row.get("commercial_cva", 0) if pd.notna(row.get("commercial_cva")) else 0,
        ind_cva=row.get("industrial_cva", 0) if pd.notna(row.get("industrial_cva")) else 0,
        ft_ratio=row.get("farmland_tax_ratio", 0),
        ct_ratio=row.get("commercial_tax_ratio", 0) if pd.notna(row.get("commercial_tax_ratio")) else 0,
        it_ratio=row.get("industrial_tax_ratio", 0) if pd.notna(row.get("industrial_tax_ratio")) else 0,
        total_muni_taxes=row.get("total_muni_taxes", 0),
        current_farm_taxes=row.get("farmland_muni_taxes", 0) if pd.notna(row.get("farmland_muni_taxes")) else 0,
        current_res_taxes=row.get("residential_muni_taxes", 0),
        current_com_taxes=row.get("commercial_muni_taxes", 0) if pd.notna(row.get("commercial_muni_taxes")) else 0,
        current_ind_taxes=row.get("industrial_muni_taxes", 0) if pd.notna(row.get("industrial_muni_taxes")) else 0,
        current_burden=row["farmland_share_of_taxes"],
        total_households=row.get("total_households", 0) if pd.notna(row.get("total_households")) else 0,
    )
    n_tested += 1
    if calc is not None:
        if abs(calc.zero_sum_check) < 0.01:  # within 1 cent
            n_zero_sum_ok += 1
        else:
            zero_sum_failures.append(
                f"{row['municipality_name']} (zero_sum=${calc.zero_sum_check:.2f})"
            )

check("A2.1", f"Revenue-neutral zero-sum verified for {n_tested} municipalities",
      len(zero_sum_failures) == 0,
      f"{len(zero_sum_failures)} failures: {', '.join(zero_sum_failures[:5])}")
print(f"  A2.1: {n_tested} municipalities tested, {n_zero_sum_ok} pass zero-sum → "
      f"{'✅ PASS' if len(zero_sum_failures) == 0 else '❌ FAIL'}")


# ═══════════════════════════════════════════════════════════════════════════
# A3: TAX SHARE SUMS ≤ 1.02
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A3: TAX SHARE SUM VALIDATION (should be ≤ 1.02)")
print("─" * 90)

invalid_sums = df[df["is_invalid_tax_sum"] == True]
n_invalid = len(invalid_sums)
check("A3.1", f"Tax share sums within tolerance",
      n_invalid == 0,
      f"{n_invalid} rows have tax_share_sum > 1.02",
      severity="WARN" if n_invalid < 50 else "FAIL")
print(f"  A3.1: {n_invalid} rows with invalid tax share sum → "
      f"{'✅ PASS' if n_invalid == 0 else '⚠️ WARN' if n_invalid < 50 else '❌ FAIL'}")
if n_invalid > 0:
    print(f"    Top offenders:")
    worst = invalid_sums.nlargest(5, "tax_share_sum")
    for _, row in worst.iterrows():
        print(f"      {row['municipality_name']} ({int(row['year'])}): "
              f"share_sum={row['tax_share_sum']:.4f}")


# ═══════════════════════════════════════════════════════════════════════════
# A4: CVA=0 WHERE TAXES EXIST (data quality)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A4: CVA vs TAX CONSISTENCY")
print("─" * 90)

has_farm_tax = df["farmland_muni_taxes"].notna() & (df["farmland_muni_taxes"] > 0)
zero_farm_cva = df["farmland_cva"].notna() & (df["farmland_cva"] == 0)
contradictions = df[has_farm_tax & zero_farm_cva]
check("A4.1", "No rows with farm taxes > 0 but CVA = 0",
      len(contradictions) == 0,
      f"{len(contradictions)} contradictions found",
      severity="WARN")
print(f"  A4.1: {len(contradictions)} rows with farm tax > 0 but CVA = 0 → "
      f"{'✅ PASS' if len(contradictions) == 0 else '⚠️ WARN'}")

# Same for residential
has_res_tax = df["residential_muni_taxes"].notna() & (df["residential_muni_taxes"] > 0)
no_res_cva = df["residential_cva"].isna()
res_contradictions = df[has_res_tax & no_res_cva]
check("A4.2", "No rows with residential taxes > 0 but CVA is null",
      len(res_contradictions) == 0,
      f"{len(res_contradictions)} contradictions")
print(f"  A4.2: {len(res_contradictions)} rows with res tax > 0 but CVA null → "
      f"{'✅ PASS' if len(res_contradictions) == 0 else '❌ FAIL'}")


# ═══════════════════════════════════════════════════════════════════════════
# A5: FARMLAND TAX RATIO BOUNDS [0, 0.25]
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A5: FARMLAND TAX RATIO BOUNDS")
print("─" * 90)

has_ratio = df["farmland_tax_ratio"].notna()
ratio_vals = df[has_ratio]["farmland_tax_ratio"]
above_max = (ratio_vals > 0.26).sum()  # small tolerance above 0.25
below_zero = (ratio_vals < 0).sum()
check("A5.1", "All farmland ratios within [0, 0.26]",
      above_max == 0 and below_zero == 0,
      f"{above_max} above 0.26, {below_zero} below 0",
      severity="WARN" if above_max < 10 else "FAIL")
print(f"  A5.1: {len(ratio_vals)} ratios checked, {above_max} above 0.26, "
      f"{below_zero} below 0 → "
      f"{'✅ PASS' if above_max == 0 and below_zero == 0 else '⚠️ WARN'}")
if above_max > 0:
    outliers = df[has_ratio & (df["farmland_tax_ratio"] > 0.26)]
    for _, row in outliers.head(5).iterrows():
        print(f"    ⚠️ {row['municipality_name']} ({int(row['year'])}): "
              f"ratio={row['farmland_tax_ratio']:.4f}")

# Distribution summary
print(f"  A5.2: Ratio distribution (latest year, farm municipalities only):")
latest_ratios = latest[has_ratio.reindex(latest.index, fill_value=False) if len(latest) != len(df) 
                       else latest["farmland_tax_ratio"].notna()]
latest_ratios_vals = latest[latest["farmland_tax_ratio"].notna()]["farmland_tax_ratio"]
if not latest_ratios_vals.empty:
    print(f"    Mean:   {latest_ratios_vals.mean():.4f}")
    print(f"    Median: {latest_ratios_vals.median():.4f}")
    print(f"    Min:    {latest_ratios_vals.min():.4f}")
    print(f"    Max:    {latest_ratios_vals.max():.4f}")
    print(f"    At 0.25 (max): {(latest_ratios_vals >= 0.2499).sum()}")
    print(f"    Below 0.20:    {(latest_ratios_vals < 0.20).sum()}")


# ═══════════════════════════════════════════════════════════════════════════
# A6: UPPER-TIER DATA CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A6: UPPER-TIER DATA CONSISTENCY")
print("─" * 90)

upper = df[df["tier"] == "upper"]
n_upper = upper["fir_code"].nunique()
upper_with_cva = upper[upper["farmland_cva"].notna() & (upper["farmland_cva"] > 0)]
n_upper_with_cva = upper_with_cva["fir_code"].nunique()
check("A6.1", f"All {n_upper} upper-tier municipalities have farmland CVA",
      n_upper_with_cva == n_upper,
      f"Only {n_upper_with_cva}/{n_upper} have CVA data")
print(f"  A6.1: {n_upper_with_cva}/{n_upper} upper-tier munis have farm CVA → "
      f"{'✅ PASS' if n_upper_with_cva == n_upper else '⚠️ WARN'}")

# Check that upper-tier rows don't have lower-tier taxes
upper_latest = upper.sort_values("year").drop_duplicates("fir_code", keep="last")
upper_with_lt = upper_latest[
    upper_latest["total_lt_taxes"].notna() & (upper_latest["total_lt_taxes"] > 0)
]
print(f"  A6.2: {len(upper_with_lt)}/{len(upper_latest)} upper-tier munis have LT taxes "
      f"(expected — they levy their own rate)")


# ═══════════════════════════════════════════════════════════════════════════
# A7: YEAR-OVER-YEAR VOLATILE JUMPS
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A7: YEAR-OVER-YEAR VOLATILE DATA JUMPS (>500% change)")
print("─" * 90)

volatile_count = 0
volatile_details = []
check_cols = ["farmland_cva", "residential_cva", "farmland_muni_taxes", "total_muni_taxes"]

for sgc_code in df["sgc_code"].unique():
    if pd.isna(sgc_code):
        continue
    muni = df[df["sgc_code"] == sgc_code].sort_values("year")
    if len(muni) < 2:
        continue
    muni_name = muni["municipality_name"].iloc[0]
    
    for col in check_cols:
        vals = muni[col].dropna()
        if len(vals) < 2:
            continue
        pct_change = vals.pct_change().abs()
        big_jumps = pct_change[pct_change > 5.0]  # >500%
        if not big_jumps.empty:
            for idx in big_jumps.index:
                yr = muni.loc[idx, "year"]
                old_val = vals.shift(1).loc[idx]
                new_val = vals.loc[idx]
                # Skip transitions from 0 (expected for 2010 data)
                if old_val == 0:
                    continue
                volatile_count += 1
                if len(volatile_details) < 20:
                    volatile_details.append(
                        f"  {muni_name} | {col} | {int(yr)}: "
                        f"${old_val:,.0f} → ${new_val:,.0f} "
                        f"({pct_change.loc[idx]*100:+.0f}%)"
                    )

check("A7.1", "Volatile YoY jumps",
      volatile_count == 0,
      f"{volatile_count} volatile changes found",
      severity="WARN")
print(f"  A7.1: {volatile_count} volatile jumps detected (excl. 0→N transitions) → "
      f"{'✅ PASS' if volatile_count == 0 else '⚠️ WARN'}")
for d in volatile_details[:10]:
    print(f"    {d}")


# ═══════════════════════════════════════════════════════════════════════════
# A8: PROVINCIAL AGGREGATE SANITY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 90)
print("A8: PROVINCIAL AGGREGATE SANITY CHECKS")
print("─" * 90)

# Simulate what the page does for provincial aggregation
non_upper = df[df["tier"] != "upper"]
latest_yr = int(non_upper["year"].max())
lt_latest = non_upper[non_upper["year"] == latest_yr]

prov_farm_cva = lt_latest["farmland_cva"].sum()
prov_res_cva = lt_latest["residential_cva"].sum()
prov_farm_tax = lt_latest["farmland_muni_taxes"].sum()
prov_total_tax = lt_latest["total_muni_taxes"].sum()

# Basic sanity: farm CVA should be a small % of residential
farm_to_res = prov_farm_cva / prov_res_cva if prov_res_cva > 0 else 0
check("A8.1", f"Farm CVA is reasonable fraction of residential ({farm_to_res:.1%})",
      0.01 < farm_to_res < 0.50,
      f"Farm/Res ratio = {farm_to_res:.4f}")

# Farm tax share should be small (typically 1-3%)
farm_tax_share = prov_farm_tax / prov_total_tax if prov_total_tax > 0 else 0
check("A8.2", f"Provincial farm tax share is reasonable ({farm_tax_share:.2%})",
      0.005 < farm_tax_share < 0.10,
      f"Farm tax share = {farm_tax_share:.4f}")

print(f"  A8.1: Provincial farm CVA / res CVA = {farm_to_res:.2%} → "
      f"{'✅ PASS' if 0.01 < farm_to_res < 0.50 else '❌ FAIL'}")
print(f"  A8.2: Provincial farm tax share = {farm_tax_share:.2%} → "
      f"{'✅ PASS' if 0.005 < farm_tax_share < 0.10 else '❌ FAIL'}")
print(f"  Stats ({latest_yr}):")
print(f"    Total farm CVA:   ${prov_farm_cva:>20,.0f}")
print(f"    Total res CVA:    ${prov_res_cva:>20,.0f}")
print(f"    Total farm taxes: ${prov_farm_tax:>20,.0f}")
print(f"    Total muni taxes: ${prov_total_tax:>20,.0f}")
print(f"    Municipalities:   {len(lt_latest):>20,}")


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("ACCURACY SCAN SUMMARY")
print("=" * 90)
print(f"  Total checks:  {total_checks}")
print(f"  ✅ Passed:     {total_pass}")
print(f"  ⚠️ Warnings:  {total_warn}")
print(f"  ❌ Failed:     {total_fail}")
print()

if issues:
    print("  Issues found:")
    for test_id, severity, desc, detail in issues:
        icon = "⚠️" if severity == "WARN" else "❌"
        print(f"    {icon} [{test_id}] {desc}")
        if detail:
            print(f"       {detail}")
else:
    print("  🎉 ALL CHECKS PASSED — 100% data accuracy verified!")

print()
overall = "PASS" if total_fail == 0 else "FAIL"
print(f"  Overall: {'🟢' if overall == 'PASS' else '🔴'} {overall}")
print("=" * 90)
