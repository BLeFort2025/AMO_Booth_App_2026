"""
Diagnostic script: find all municipalities with missing CVA data in fir_indicators.csv.

Analyses:
 1. Municipalities with farmland_muni_taxes > 0 but farmland_cva is null
 2. Municipalities with residential_muni_taxes > 0 but residential_cva is null
 3. Upper-tier vs lower-tier breakdown of missing CVA
 4. Year-by-year coverage analysis
 5. Cross-check: do raw FIR files contain CVA data that the ETL missed?
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIR_CSV = ROOT / "data" / "derived" / "fir_indicators.csv"

df = pd.read_csv(FIR_CSV)
df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)

print("=" * 80)
print("FIR INDICATORS — CVA DATA GAP ANALYSIS")
print("=" * 80)

# 1. Basic stats
print(f"\nTotal rows: {len(df):,}")
print(f"Unique municipalities (fir_code): {df['fir_code'].nunique()}")
print(f"Year range: {int(df['year'].min())}–{int(df['year'].max())}")
print(f"Tier distribution:")
for tier, cnt in df["tier"].value_counts(dropna=False).items():
    print(f"  {tier}: {cnt:,}")

# 2. CVA null rates
cva_cols = [
    "farmland_cva", "residential_cva", "commercial_cva",
    "industrial_cva", "total_taxable_cva",
]
print(f"\n{'='*80}")
print("CVA NULL RATES (all rows)")
print(f"{'='*80}")
for col in cva_cols:
    n_null = df[col].isna().sum()
    pct = n_null / len(df) * 100
    print(f"  {col}: {n_null:,} null ({pct:.1f}%)")

# 3. Tax ratio and share null rates
ratio_cols = ["farmland_tax_ratio", "commercial_tax_ratio", "industrial_tax_ratio"]
print(f"\n{'='*80}")
print("TAX RATIO NULL RATES (all rows)")
print(f"{'='*80}")
for col in ratio_cols:
    if col in df.columns:
        n_null = df[col].isna().sum()
        pct = n_null / len(df) * 100
        print(f"  {col}: {n_null:,} null ({pct:.1f}%)")

# 4. Municipalities with taxes but no CVA
print(f"\n{'='*80}")
print("MUNICIPALITIES WITH TAXES BUT NO CVA (most likely data extraction issue)")
print(f"{'='*80}")

has_farm_tax = df["farmland_muni_taxes"].notna() & (df["farmland_muni_taxes"] > 0)
no_farm_cva = df["farmland_cva"].isna()
tax_no_cva = df[has_farm_tax & no_farm_cva]
print(f"\nRows with farmland_muni_taxes > 0 but farmland_cva is null: {len(tax_no_cva)}")

if not tax_no_cva.empty:
    # Breakdown by tier  
    print("\n  By tier:")
    for tier, cnt in tax_no_cva["tier"].value_counts(dropna=False).items():
        print(f"    {tier}: {cnt}")
    
    # Show affected municipalities
    affected = tax_no_cva.groupby(["fir_code", "municipality_name", "tier"]).agg(
        years=("year", list),
        n_years=("year", "count"),
        avg_farm_tax=("farmland_muni_taxes", "mean"),
    ).reset_index().sort_values("n_years", ascending=False)
    
    print(f"\n  Affected municipalities ({len(affected)} total):")
    for _, row in affected.head(50).iterrows():
        yrs = sorted(row["years"])
        yr_range = f"{int(min(yrs))}–{int(max(yrs))}" if len(yrs) > 1 else str(int(yrs[0]))
        print(f"    FIR {row['fir_code']} | {row['municipality_name']:<35} | {row['tier']:<8} | "
              f"{row['n_years']} yrs ({yr_range}) | avg farm tax=${row['avg_farm_tax']:,.0f}")

# 5. Same analysis for residential CVA
has_res_tax = df["residential_muni_taxes"].notna() & (df["residential_muni_taxes"] > 0)
no_res_cva = df["residential_cva"].isna()
res_tax_no_cva = df[has_res_tax & no_res_cva]
print(f"\nRows with residential_muni_taxes > 0 but residential_cva is null: {len(res_tax_no_cva)}")

# 6. Year-by-year CVA coverage for farmland
print(f"\n{'='*80}")
print("YEAR-BY-YEAR FARMLAND CVA COVERAGE")
print(f"{'='*80}")
for yr in sorted(df["year"].unique()):
    yr_df = df[df["year"] == yr]
    total = len(yr_df)
    has_cva = yr_df["farmland_cva"].notna().sum()
    has_tax = (yr_df["farmland_muni_taxes"].notna() & (yr_df["farmland_muni_taxes"] > 0)).sum()
    gap = has_tax - has_cva
    pct = has_cva / total * 100
    print(f"  {int(yr)}: {has_cva:>3}/{total:>3} have CVA ({pct:5.1f}%), "
          f"{has_tax:>3} have farm tax, gap={gap:>3}")

# 7. Check the FIR YAML config to see where CVA is sourced from
print(f"\n{'='*80}")
print("CVA EXTRACTION SOURCE (from fir_indicators.yaml)")
print(f"{'='*80}")
import yaml
cfg_path = ROOT / "config" / "fir_indicators.yaml"
if cfg_path.exists():
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for group_name, group_cfg in cfg.items():
        if group_name == "computed":
            continue
        for ind_name, ind_def in group_cfg.get("indicators", {}).items():
            if "cva" in ind_name.lower():
                print(f"  {ind_name}: schedule={group_cfg.get('schedule')}, "
                      f"line={ind_def.get('line','?')}, col={ind_def.get('col','?')}, "
                      f"match={group_cfg.get('match_type','?')}, "
                      f"col_type={group_cfg.get('col_type','?')}")
                if "rtc" in ind_def:
                    print(f"    → RTC={ind_def['rtc']}")

# 8. Upper-tier specific analysis (Simcoe is shown in the screenshot)
print(f"\n{'='*80}")
print("UPPER-TIER MUNICIPALITY CVA ANALYSIS")
print(f"{'='*80}")
upper = df[df["tier"] == "upper"]
print(f"Upper-tier rows: {len(upper)}")
for _, row in upper.drop_duplicates("fir_code").iterrows():
    muni_rows = df[df["fir_code"] == row["fir_code"]]
    has = muni_rows["farmland_cva"].notna().sum()
    total = len(muni_rows)
    latest = muni_rows.sort_values("year").iloc[-1]
    cva_val = latest.get("farmland_cva")
    tax_val = latest.get("farmland_muni_taxes")
    print(f"  FIR {row['fir_code']} | {row['municipality_name']:<35} | "
          f"CVA in {has}/{total} yrs | latest CVA={cva_val} | latest tax={tax_val}")

# 9. Sample raw data for Simcoe County to debug
print(f"\n{'='*80}")
print("SIMCOE COUNTY RAW DATA SAMPLE")
print(f"{'='*80}")
simcoe = df[df["municipality_name"].str.contains("Simcoe", case=False, na=False)]
if simcoe.empty:
    print("  No rows matching 'Simcoe' found")
else:
    for _, row in simcoe.sort_values("year").iterrows():
        print(f"  {int(row['year'])} | FIR {row['fir_code']} | {row['municipality_name']:<30} | "
              f"tier={row.get('tier','?'):<8} | "
              f"farm_cva={row.get('farmland_cva','NULL')!s:<12} | "
              f"res_cva={row.get('residential_cva','NULL')!s:<15} | "
              f"farm_tax={row.get('farmland_muni_taxes','NULL')!s:<12}")
