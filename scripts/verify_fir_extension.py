"""Gather Zorra sample data for expert prompt."""
import pandas as pd

df = pd.read_csv("data/derived/fir_indicators.csv")

for yr in [2010, 2021]:
    z = df[(df["municipality_name"] == "Zorra Tp") & (df["year"] == yr)]
    if len(z) == 0:
        print(f"Zorra {yr}: NOT FOUND")
        continue
    r = z.iloc[0]
    print(f"\n=== ZORRA {yr} ===")
    cols = [
        "total_revenue", "total_expenses", "ompf_grant",
        "total_taxes", "total_lt_taxes", "total_ut_taxes",
        "farmland_cva", "farmland_total_taxes", "farmland_lt_taxes", "farmland_ut_taxes",
        "farmland_tax_ratio", "farmland_lt_rate", "farmland_ut_rate",
        "residential_lt_rate", "residential_ut_rate",
        "residential_cva", "residential_total_taxes", "residential_lt_taxes", "residential_ut_taxes",
        "commercial_cva", "commercial_total_taxes", "commercial_lt_taxes", "commercial_ut_taxes",
        "industrial_cva", "industrial_total_taxes", "industrial_lt_taxes", "industrial_ut_taxes",
        "accumulated_surplus", "net_financial_assets",
        "ag_land_hectares",
        "res_building_permits_count", "res_building_permits_value",
        # Computed
        "farmland_muni_taxes", "residential_muni_taxes",
        "commercial_muni_taxes", "industrial_muni_taxes",
        "total_muni_taxes",
        "farmland_share_of_taxes", "residential_share_of_taxes",
        "commercial_share_of_taxes", "industrial_share_of_taxes",
        "farmland_share_of_cva", "farmland_burden_gap",
        "farmland_tax_per_100k_cva", "ompf_relief_factor",
        "farmland_tax_per_hectare", "operating_surplus",
        "total_road_km", "paved_road_km",
    ]
    for c in cols:
        v = r.get(c)
        if pd.isna(v):
            print(f"  {c}: —")
        elif isinstance(v, float) and abs(v) > 1000:
            print(f"  {c}: {v:,.0f}")
        elif isinstance(v, float) and abs(v) < 1:
            print(f"  {c}: {v:.6f}")
        else:
            print(f"  {c}: {v}")
