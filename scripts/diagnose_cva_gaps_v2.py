"""
Diagnostic Part 2: Find all municipalities where zero CVA in first year
causes N/A growth metrics, and identify the true scope of the problem.
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIR_CSV = ROOT / "data" / "derived" / "fir_indicators.csv"
df = pd.read_csv(FIR_CSV, low_memory=False)
df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)

print("=" * 100)
print("CVA GROWTH N/A ANALYSIS — Root Cause: Zero/Missing CVA in First Available Year")
print("=" * 100)

cva_cols = {
    "Farmland": "farmland_cva",
    "Residential": "residential_cva",
    "Commercial": "commercial_cva",
    "Industrial": "industrial_cva",
}

# For each municipality, check if first year has CVA=0 or null
affected_munis = []
for (fir_code, muni_name, tier), grp in df.groupby(["fir_code", "municipality_name", "tier"]):
    grp = grp.sort_values("year")
    first_year = grp["year"].min()
    last_year = grp["year"].max()
    first_row = grp[grp["year"] == first_year].iloc[0]
    
    issues = []
    for label, col in cva_cols.items():
        first_val = first_row.get(col)
        if first_val is None or pd.isna(first_val) or first_val == 0:
            # Check if later years have data
            later = grp[grp["year"] > first_year]
            later_has = later[col].notna() & (later[col] > 0)
            if later_has.any():
                # Find first year with actual data
                first_good_year = later[later_has]["year"].min()
                first_good_val = later[later[col].notna() & (later[col] > 0)][col].iloc[0]
                issues.append({
                    "label": label,
                    "col": col,
                    "first_year_val": first_val,
                    "first_good_year": first_good_year,
                    "first_good_val": first_good_val,
                })
    
    if issues:
        affected_munis.append({
            "fir_code": fir_code,
            "municipality_name": muni_name,
            "tier": tier,
            "first_year": int(first_year),
            "last_year": int(last_year),
            "n_years": len(grp),
            "issues": issues,
        })

print(f"\nTotal municipalities affected: {len(affected_munis)} / {df['fir_code'].nunique()}")
print(f"\nBy tier:")
tier_counts = {}
for m in affected_munis:
    tier_counts[m["tier"]] = tier_counts.get(m["tier"], 0) + 1
for tier, cnt in sorted(tier_counts.items()):
    print(f"  {tier}: {cnt}")

print(f"\n{'='*100}")
print("AFFECTED MUNICIPALITIES WITH ZERO CVA IN FIRST YEAR")
print(f"{'='*100}")
for m in sorted(affected_munis, key=lambda x: x["municipality_name"]):
    issue_strs = []
    for iss in m["issues"]:
        issue_strs.append(
            f"{iss['label']}(first_yr={iss['first_year_val']}, "
            f"first_good={int(iss['first_good_year'])}:{iss['first_good_val']:,.0f})"
        )
    print(f"  FIR {m['fir_code']:<5} | {m['municipality_name']:<35} | {m['tier']:<8} | "
          f"yr {m['first_year']}–{m['last_year']} | {'; '.join(issue_strs)}")

# Also check: how many total N/A growth metrics would be shown
print(f"\n{'='*100}")
print("IMPACT ON CVA GROWTH DISPLAY (# of N/A metrics per class)")
print(f"{'='*100}")
for label, col in cva_cols.items():
    # Count municipalities where growth calc would fail
    na_count = 0
    for (fir_code,), grp in df.groupby(["fir_code"]):
        grp = grp.sort_values("year")
        first_val = grp[col].iloc[0]
        last_val = grp[col].iloc[-1]
        if first_val is None or pd.isna(first_val) or first_val <= 0:
            na_count += 1
        elif last_val is None or pd.isna(last_val):
            na_count += 1
    print(f"  {label}: {na_count} municipalities would show N/A growth")

# Understanding: what's the real first year with data for these municipalities?
print(f"\n{'='*100}")
print("DATA QUALITY: CVA=0 rows (not null, but explicitly zero)")
print(f"{'='*100}")
for col in cva_cols.values():
    zero_count = ((df[col] == 0) & df[col].notna()).sum()
    null_count = df[col].isna().sum()
    print(f"  {col}: {zero_count} zeros, {null_count} nulls")

# Check if there's a pattern — are zeros always in particular years?
print(f"\n{'='*100}")
print("ZERO CVA BY YEAR (farmland_cva)")
print(f"{'='*100}")
for yr in sorted(df["year"].unique()):
    yr_df = df[df["year"] == yr]
    n_zero = ((yr_df["farmland_cva"] == 0) & yr_df["farmland_cva"].notna()).sum()
    n_null = yr_df["farmland_cva"].isna().sum()
    if n_zero > 0 or n_null > 0:
        print(f"  {int(yr)}: {n_zero} zeros, {n_null} nulls (out of {len(yr_df)})")

# Specific check: which municipalities have CVA=0 in 2010 (first year)?
print(f"\n{'='*100}")
print("MUNICIPALITIES WITH farmland_cva=0 IN 2010")
print(f"{'='*100}")
yr2010 = df[(df["year"] == 2010) & (df["farmland_cva"] == 0)]
for _, row in yr2010.iterrows():
    # Check if their 2011 has real data
    next_yr = df[(df["fir_code"] == row["fir_code"]) & (df["year"] == 2011)]
    next_cva = next_yr["farmland_cva"].values[0] if len(next_yr) > 0 else "N/A"
    print(f"  FIR {row['fir_code']:<5} | {row['municipality_name']:<35} | {row['tier']:<8} | "
          f"2010 CVA=0, 2011 CVA={next_cva}")
