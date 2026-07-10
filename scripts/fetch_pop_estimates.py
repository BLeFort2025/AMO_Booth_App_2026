"""
Fetch and process StatCan Table 17-10-0155-01:
  Population estimates, July 1, by census subdivision, 2021 boundaries.

Produces: data/derived/pop_estimates_annual.csv
  Columns: sgc_code, year, population

This provides annual intercensal population estimates for Ontario CSDs,
enabling gap-filling between Census years and forecast verification.
"""
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_statcan import fetch_table, ensure_year_column, persist_if_changed

TABLE_ID = "17-10-0155-01"
OUTPUT_PATH = PROJECT_ROOT / "data" / "derived" / "pop_estimates_annual.csv"


def run() -> pd.DataFrame:
    """Fetch, filter and save annual CSD population estimates for Ontario."""
    print(f"[pop_estimates] Fetching Table {TABLE_ID}...")

    # 1. Download raw CSV via existing StatCan helper
    df, content_hash = fetch_table(TABLE_ID)
    persist_if_changed(TABLE_ID, df, content_hash)

    # 2. Ensure we have a YEAR column
    df = ensure_year_column(df)

    # 3. Extract SGC code from DGUID
    #    DGUID format: "2021S0512XXXXXXX" → last 7 chars = SGC code
    #    Or from GEO column: "Township of Guelph/Eramosa (3523008)" — we prefer DGUID
    if "DGUID" in df.columns:
        df["sgc_code"] = df["DGUID"].astype(str).str[-7:]
    elif "GEO" in df.columns:
        # Fallback: extract 7-digit code from GEO name
        extracted = df["GEO"].astype(str).str.extract(r"\((\d{7})\)")
        df["sgc_code"] = extracted[0]
    else:
        print("[pop_estimates] ERROR: No DGUID or GEO column found.")
        return pd.DataFrame()

    # 4. Filter to Ontario CSDs only (SGC codes starting with "35")
    df = df[df["sgc_code"].str.startswith("35", na=False)].copy()

    if df.empty:
        print("[pop_estimates] WARNING: No Ontario records found after filtering.")
        return pd.DataFrame()

    # 5. Get population values
    #    StatCan tables use VALUE column for the numeric data
    value_col = None
    for candidate in ["VALUE", "Value", "value", "OBS_VALUE"]:
        if candidate in df.columns:
            value_col = candidate
            break

    if value_col is None:
        # Try to find a numeric column that looks like population
        print(f"[pop_estimates] Available columns: {list(df.columns)}")
        print("[pop_estimates] ERROR: No VALUE column found.")
        return pd.DataFrame()

    # 6. Build clean output: sgc_code, year, population
    result = df[["sgc_code", "YEAR", value_col]].copy()
    result.columns = ["sgc_code", "year", "population"]

    # Clean types
    result["year"] = pd.to_numeric(result["year"], errors="coerce").astype("Int64")
    result["population"] = pd.to_numeric(result["population"], errors="coerce")

    # Drop rows without valid data
    result = result.dropna(subset=["year", "population"])
    result["population"] = result["population"].astype(int)

    # Keep only post-Census years (2022+) — Census years are handled by fetch_census_profile
    result = result[result["year"] >= 2022].copy()

    # De-duplicate (should be one estimate per CSD per year)
    result = result.drop_duplicates(subset=["sgc_code", "year"])
    result = result.sort_values(["sgc_code", "year"]).reset_index(drop=True)

    # 7. Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    n_csds = result["sgc_code"].nunique()
    year_range = f"{result['year'].min()}-{result['year'].max()}"
    print(f"[pop_estimates] Saved {len(result)} rows for {n_csds} Ontario CSDs ({year_range})")
    print(f"[pop_estimates] Output: {OUTPUT_PATH}")

    return result


if __name__ == "__main__":
    run()
