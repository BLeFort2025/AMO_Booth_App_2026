"""
process_capex.py
────────────────
Processes StatCan Table 34-10-0035-01 (Capital Expenditures) to produce
a verified CapEx baseline for each Industry Basket, **by geography**.

Output: data/derived/basket_capex.csv
Columns: geo, basket_key, total_capex_M, construction_share, machinery_share, data_year
"""

import pandas as pd
from pathlib import Path
import sys
import re

# Add project root to path if needed
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import config_loader

# Constants
TABLE_ID = "34-10-0035-01"
OUTPUT_FILE = Path("data/derived/basket_capex.csv")

# Basket Definitions
BASKETS = {
    "primary_agriculture": ["111", "112"],
    "food_beverage_manufacturing": ["311", "312", "3121"],
    "cfa_food_system": ["111", "112", "311", "312", "3121"]
}

# Atlantic provinces rollup (not a StatCan geography)
ATLANTIC_PROVINCES = [
    "New Brunswick", "Newfoundland and Labrador",
    "Nova Scotia", "Prince Edward Island"
]


def load_data():
    """Load the raw StatCan data."""
    raw_dir = config_loader.get_raw_data_dir()
    raw_path = raw_dir / f"{TABLE_ID}.csv"

    if not raw_path.exists():
        print(f"[WARNING] Raw data for table {TABLE_ID} not found at {raw_path}. Please run fetch_statcan first.")
        return None
    return pd.read_csv(raw_path, low_memory=False)


def _compute_basket(df_geo, type_col, basket_key, codes):
    """Compute CapEx totals for a single basket within a single geography."""
    subset = df_geo[df_geo["clean_code"].isin(codes)]
    if subset.empty:
        return None

    pivot = subset.groupby(type_col)["VALUE"].sum()
    construction = pivot.get("Capital, construction", 0)
    machinery = pivot.get("Capital, machinery and equipment", 0)
    total_capex = construction + machinery

    const_share = (construction / total_capex) if total_capex > 0 else 0.0
    mach_share = (machinery / total_capex) if total_capex > 0 else 0.0

    return {
        "total_capex_M": total_capex,
        "construction_share": const_share,
        "machinery_share": mach_share,
    }


def run():
    print(f"--- Processing CapEx Data (Table {TABLE_ID}) ---")
    df = load_data()
    if df is None:
        return

    # Standardize columns
    df.columns = df.columns.str.strip()

    # 1. Filter for Latest Reference Year
    latest_year = df["REF_DATE"].max()
    print(f"   Using Data Year: {latest_year}")
    df = df[df["REF_DATE"] == latest_year]

    # 2. Filter for Asset Types
    type_col = next((c for c in df.columns if "Capital and repair" in c), None)
    if not type_col:
        print("[ERROR] Could not find 'Capital and repair expenditures' column.")
        return

    target_types = ["Capital, construction", "Capital, machinery and equipment"]
    df = df[df[type_col].isin(target_types)]

    # 3. Extract NAICS Codes
    ind_col = next((c for c in df.columns if "NAICS" in c), None)

    def extract_code(val):
        match = re.search(r'\[(\d+)\]', str(val))
        return match.group(1) if match else None

    df = df.copy()
    df["clean_code"] = df[ind_col].apply(extract_code)

    # 4. Process per geography
    results = []
    geos = sorted(df["GEO"].unique())
    geo_count = 0

    for geo in geos:
        df_geo = df[df["GEO"] == geo]

        for basket_key, codes in BASKETS.items():
            basket = _compute_basket(df_geo, type_col, basket_key, codes)
            if basket:
                results.append({
                    "geo": geo,
                    "basket_key": basket_key,
                    "total_capex_M": basket["total_capex_M"],
                    "construction_share": basket["construction_share"],
                    "machinery_share": basket["machinery_share"],
                    "data_year": latest_year,
                })
                geo_count += 1

    # 5. Add "Atlantic provinces" rollup (sum of NB + NL + NS + PEI)
    atl_geos = [g for g in geos if g in ATLANTIC_PROVINCES]
    if atl_geos:
        df_atl = df[df["GEO"].isin(atl_geos)]
        for basket_key, codes in BASKETS.items():
            basket = _compute_basket(df_atl, type_col, basket_key, codes)
            if basket:
                results.append({
                    "geo": "Atlantic provinces",
                    "basket_key": basket_key,
                    "total_capex_M": basket["total_capex_M"],
                    "construction_share": basket["construction_share"],
                    "machinery_share": basket["machinery_share"],
                    "data_year": latest_year,
                })

    # Save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out_df = pd.DataFrame(results)
    out_df.to_csv(OUTPUT_FILE, index=False)

    # Summary
    pa = out_df[out_df["basket_key"] == "primary_agriculture"].sort_values("total_capex_M", ascending=False)
    print(f"\n   Primary Agriculture CapEx by Geography:")
    for _, row in pa.iterrows():
        print(f"     {row['geo']:<35} ${row['total_capex_M']:>10,.1f}M")
    print(f"\n   Saved {len(results)} records ({len(pa)} geos × {len(BASKETS)} baskets) to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()