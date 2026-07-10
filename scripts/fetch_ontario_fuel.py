"""Fetch Ontario weekly retail fuel prices from the Ontario Data Catalogue.

Source: Ontario Ministry of Energy — Fuels Price Survey
URL: https://data.ontario.ca/dataset/fuels-price-survey

The survey publishes weekly retail prices for gasoline, diesel, propane,
and CNG across 10 Ontario markets.  Data is typically updated every Monday.

Output: data/latest/ontario_fuel_weekly.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path("data/latest")
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_DIR / "ontario_fuel_weekly.csv"

# Ontario Data Catalogue resource URL for the Fuels Price Survey
# This is the XLSX download link for the retail fuel price survey.
# NOTE: This URL may change if Ontario updates the dataset resource.
# If it breaks, check: https://data.ontario.ca/dataset/fuels-price-survey
FUEL_SURVEY_URL = (
    "https://data.ontario.ca/dataset/f4aa2e25-e129-4e5d-b7e5-6a3f369b91c5/"
    "resource/91cc8ac6-3174-44a6-80f0-4f5ec8c2682f/download/"
    "fuels-price-survey-current-year.xlsx"
)

# Fallback: try the CSV version of the Ontario fuel data
FUEL_SURVEY_CSV_URL = (
    "https://data.ontario.ca/dataset/f4aa2e25-e129-4e5d-b7e5-6a3f369b91c5/"
    "resource/91cc8ac6-3174-44a6-80f0-4f5ec8c2682f/download/"
    "fuels-price-survey-current-year.csv"
)


def fetch_ontario_fuel() -> pd.DataFrame | None:
    """Download and parse the Ontario fuel price survey.

    Returns a cleaned DataFrame or None if all attempts fail.
    """
    print("📡 Fetching Ontario weekly fuel prices...")

    df = _try_xlsx_download()
    if df is None:
        df = _try_csv_download()

    if df is None:
        print("❌ Could not download Ontario fuel data from any source.")
        return None

    # Standardise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Save
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"💾 Ontario fuel data saved to {OUTPUT_FILE} ({len(df)} rows)")
    return df


def _try_xlsx_download() -> pd.DataFrame | None:
    """Attempt to download and parse the XLSX format."""
    try:
        print(f"   Trying XLSX: {FUEL_SURVEY_URL[:80]}...")
        resp = requests.get(FUEL_SURVEY_URL, timeout=60)
        resp.raise_for_status()
        df = pd.read_excel(
            resp.content,
            engine="openpyxl",
        )
        print(f"   ✅ XLSX downloaded ({len(df)} rows)")
        return df
    except Exception as e:
        print(f"   ⚠️ XLSX failed: {e}")
        return None


def _try_csv_download() -> pd.DataFrame | None:
    """Attempt to download the CSV format as fallback."""
    try:
        print(f"   Trying CSV fallback: {FUEL_SURVEY_CSV_URL[:80]}...")
        resp = requests.get(FUEL_SURVEY_CSV_URL, timeout=60)
        resp.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
        print(f"   ✅ CSV downloaded ({len(df)} rows)")
        return df
    except Exception as e:
        print(f"   ⚠️ CSV failed: {e}")
        return None


if __name__ == "__main__":
    fetch_ontario_fuel()
