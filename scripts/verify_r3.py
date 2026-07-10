"""Verify Expert R3 changes: 6-class share gap, pipeline data, total building permits."""
import pandas as pd
import numpy as np

df = pd.read_csv("data/derived/fir_indicators.csv")
print(f"Total records: {len(df)}")

# 1. Six-class share sum (RT + FT + CT + IT + MT + PT)
share_cols = [
    "residential_share_of_taxes", "farmland_share_of_taxes",
    "commercial_share_of_taxes", "industrial_share_of_taxes",
    "multi_residential_share_of_taxes", "pipeline_share_of_taxes",
]
for c in share_cols:
    nn = df[c].notna().sum()
    print(f"  {c}: {nn} non-null ({nn/len(df)*100:.1f}%)")

valid = df[share_cols].notna().all(axis=1)
print(f"\nRows with ALL 6 shares non-null: {valid.sum()} ({valid.sum()/len(df)*100:.1f}%)")

if valid.sum() > 0:
    sums = df.loc[valid, share_cols].sum(axis=1)
    print(f"  Mean 6-class share sum: {sums.mean()*100:.1f}%")
    print(f"  Median: {sums.median()*100:.1f}%")
    print(f"  Min: {sums.min()*100:.1f}%")
    print(f"  Max: {sums.max()*100:.1f}%")

    # By year
    print("\n  By year:")
    for yr in sorted(df.loc[valid, "year"].unique()):
        mask = valid & (df["year"] == yr)
        if mask.sum() > 0:
            yr_sums = df.loc[mask, share_cols].sum(axis=1)
            print(f"    {yr}: mean={yr_sums.mean()*100:.1f}%, n={mask.sum()}")

# 2. Pipeline-specific
print(f"\n--- Pipeline Data ---")
print(f"  pipeline_cva non-null: {df['pipeline_cva'].notna().sum()}")
print(f"  pipeline_muni_taxes non-null: {df['pipeline_muni_taxes'].notna().sum()}")
print(f"  pipeline_share_of_taxes non-null: {df['pipeline_share_of_taxes'].notna().sum()}")
pipe_ok = df["pipeline_share_of_taxes"].dropna()
if len(pipe_ok) > 0:
    print(f"  Mean pipeline share: {pipe_ok.mean()*100:.2f}%")

# 3. Total Building Permits
print(f"\n--- Total Building Permits ---")
print(f"  total_building_permits_count non-null: {df['total_building_permits_count'].notna().sum()} ({df['total_building_permits_count'].notna().mean()*100:.1f}%)")
print(f"  total_building_permits_value non-null: {df['total_building_permits_value'].notna().sum()} ({df['total_building_permits_value'].notna().mean()*100:.1f}%)")
print(f"  res_building_permits_count non-null: {df['res_building_permits_count'].notna().sum()} ({df['res_building_permits_count'].notna().mean()*100:.1f}%)")

# 4. Zorra Tp spot checks
print(f"\n--- Zorra Tp 2021 ---")
z = df[(df["municipality_name"].str.contains("Zorra", case=False, na=False)) & (df["year"] == 2021)]
if len(z) > 0:
    r = z.iloc[0]
    print(f"  pipeline_cva: {r.get('pipeline_cva', 'N/A')}")
    print(f"  pipeline_muni_taxes: {r.get('pipeline_muni_taxes', 'N/A')}")
    print(f"  pipeline_share: {r.get('pipeline_share_of_taxes', 'N/A')}")
    print(f"  multi_res_share: {r.get('multi_residential_share_of_taxes', 'N/A')}")
    six_sum = sum(r.get(c, 0) or 0 for c in share_cols)
    print(f"  6-class share sum: {six_sum*100:.1f}%")
    print(f"  total_building_permits_count: {r.get('total_building_permits_count', 'N/A')}")
    print(f"  total_building_permits_value: {r.get('total_building_permits_value', 'N/A')}")
