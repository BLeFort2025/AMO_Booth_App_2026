"""Fetch global fertilizer benchmark prices from the World Bank Pink Sheet.

Source: World Bank Commodity Price Data ("Pink Sheet")
  - Monthly nominal USD prices, 1960 to present
  - License: Creative Commons Attribution 4.0 (CC-BY 4.0)
  - URL: https://www.worldbank.org/en/research/commodity-markets

Commodities extracted:
  - Urea (Eastern Europe, bulk, f.o.b.)
  - DAP (Di-ammonium Phosphate, US Gulf, f.o.b.)
  - TSP (Triple Super Phosphate, North Africa, f.o.b.)
  - Potash / KCl (Muriate of Potash, standard grade, f.o.b. Vancouver)
  - Phosphate Rock (Morocco, 70% BPL, contract, f.a.s. Casablanca)

Output: data/latest/fertilizer_benchmarks.csv
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path("data/latest")
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_DIR / "fertilizer_benchmarks.csv"

# World Bank CMO Monthly Prices Excel (Pink Sheet)
PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "5d903e848db1d1b83e0ec8f744e55570-0350012021/"
    "related/CMO-Historical-Data-Monthly.xlsx"
)

# Column mapping: Pink Sheet column name → our clean name
# Note: some Pink Sheet column names have trailing spaces or ** markers
FERTILIZER_COLUMNS = {
    "Urea":            "urea_usd",
    "Urea ":           "urea_usd",          # trailing space variant
    "DAP":             "dap_usd",
    "TSP":             "tsp_usd",
    "Potassium chloride **": "potash_usd",
    "Potassium chloride":    "potash_usd",   # without ** variant
    "Phosphate rock":  "phosphate_rock_usd",
}

# Human-friendly labels for display
FERTILIZER_LABELS = {
    "urea_usd":            "Urea (USD/t)",
    "dap_usd":             "DAP (USD/t)",
    "tsp_usd":             "TSP (USD/t)",
    "potash_usd":          "Potash / KCl (USD/t)",
    "phosphate_rock_usd":  "Phosphate Rock (USD/t)",
}


def _parse_pink_sheet_date(val: str) -> pd.Timestamp | None:
    """Parse Pink Sheet date format '2024M01' → Timestamp."""
    try:
        match = re.match(r"(\d{4})M(\d{2})", str(val))
        if match:
            return pd.Timestamp(int(match.group(1)), int(match.group(2)), 1)
    except Exception:
        pass
    return None


def fetch_fertilizer_benchmarks() -> pd.DataFrame | None:
    """Download the World Bank Pink Sheet and extract fertilizer prices.

    Returns a cleaned DataFrame or None if download fails.
    """
    print("📡 Fetching World Bank Pink Sheet (fertilizer benchmarks)...")

    try:
        resp = requests.get(PINK_SHEET_URL, timeout=120)
        resp.raise_for_status()
        print(f"   ✅ Downloaded ({len(resp.content):,} bytes)")
    except Exception as e:
        print(f"   ❌ Download failed: {e}")
        return None

    try:
        df = pd.read_excel(
            io.BytesIO(resp.content),
            sheet_name="Monthly Prices",
            header=4,
            engine="openpyxl",
        )
    except Exception as e:
        print(f"   ❌ Excel parse failed: {e}")
        return None

    # Identify columns
    date_col = df.columns[0]  # first column is the date (typically "Unnamed: 0")

    found_cols = {}
    for raw_col in df.columns:
        raw_str = str(raw_col).strip()
        for pattern, clean_name in FERTILIZER_COLUMNS.items():
            if raw_str == pattern.strip():
                found_cols[raw_col] = clean_name
                break

    if not found_cols:
        print("   ❌ Could not find any fertilizer columns in the Pink Sheet!")
        print(f"   Available columns: {list(df.columns[:20])}")
        return None

    print(f"   Found {len(found_cols)} fertilizer columns: {list(found_cols.values())}")

    # Extract and clean
    keep_cols = [date_col] + list(found_cols.keys())
    result = df[keep_cols].copy()
    result = result.rename(columns={date_col: "date_raw", **found_cols})

    # Parse dates
    result["date"] = result["date_raw"].apply(_parse_pink_sheet_date)
    result = result.dropna(subset=["date"])

    # Convert price columns to numeric
    for col in found_cols.values():
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    # Drop rows where ALL price columns are NaN
    price_cols = [c for c in found_cols.values() if c in result.columns]
    result = result.dropna(subset=price_cols, how="all")

    # Clean up: keep only date + price columns, sorted
    result = result[["date"] + price_cols].sort_values("date").reset_index(drop=True)

    # Save
    result.to_csv(OUTPUT_FILE, index=False)
    date_range = f"{result['date'].min().strftime('%Y-%m')} to {result['date'].max().strftime('%Y-%m')}"
    print(f"💾 Saved {len(result)} rows to {OUTPUT_FILE} ({date_range})")

    return result


if __name__ == "__main__":
    df = fetch_fertilizer_benchmarks()
    if df is not None:
        print("\nLatest 6 months:")
        print(df.tail(6).to_string(index=False))
