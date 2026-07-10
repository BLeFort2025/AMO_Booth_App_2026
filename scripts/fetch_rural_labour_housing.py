"""
fetch_rural_labour_housing.py
==============================
Downloads and processes two Statistics Canada tables for the
Rural Labour Market Monitor section on Page 9:

  - 14-10-0203-01  Survey of Employment, Payrolls and Hours (SEPH)
                   Paid employment by NAICS industry, Ontario geo breakdown

  - 34-10-0143-01  CMHC Housing Starts in centres >= 10,000 population
                   Quarterly data: single-detached + multi-unit

Outputs (saved to data/derived/):
  - rural_labour_seph.parquet   — SEPH Ontario employment by industry, annual
  - rural_housing_starts.parquet — CMHC housing starts for Ontario, quarterly

Run manually:
  python scripts/fetch_rural_labour_housing.py

Or via the main pipeline:
  python scripts/run_pipeline.py
"""

import sys
from pathlib import Path
import pandas as pd

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_statcan import fetch_table
from scripts.http_utils import get_robust_session

DERIVED_DIR = PROJECT_ROOT / "data" / "derived"
DERIVED_DIR.mkdir(parents=True, exist_ok=True)

# ── NAICS industry labels we care about (SEPH NAICS codes → clean names) ──────
# These match OMAFRA report sectors; covers all 16 NAICS super-sectors
SEPH_INDUSTRY_MAP = {
    # Goods-producing
    "Agriculture":                                    "Agriculture",
    "Forestry, logging and support":                  "Forestry & Logging",
    "Mining, quarrying, and oil and gas extraction":  "Mining & Oil/Gas",
    "Utilities":                                      "Utilities",
    "Construction":                                   "Construction",
    "Manufacturing":                                  "Manufacturing",
    # Services-producing
    "Wholesale trade":                                "Wholesale Trade",
    "Retail trade":                                   "Retail Trade",
    "Transportation and warehousing":                 "Transportation",
    "Information and cultural industries":            "Information & Culture",
    "Finance and insurance":                          "Finance & Insurance",
    "Real estate and rental and leasing":             "Real Estate",
    "Professional, scientific and technical":         "Professional Services",
    "Business, building and other support":           "Business Support Services",
    "Educational services":                           "Education",
    "Health care and social assistance":              "Health Care",
    "Information, culture and recreation":            "Information & Recreation",
    "Accommodation and food services":                "Accommodation & Food",
    "Other services (except public administration)":  "Other Services",
    "Public administration":                          "Public Administration",
}

# Ontario geographic geo_uid filter
ONTARIO_GEO_PATTERNS = [
    "Ontario",
    "Northeastern Ontario",
    "Northwestern Ontario",
    "Ottawa",
    "Kingston-Pembroke",
    "Muskoka-Kawarthas",
    "Toronto",
    "Kitchener-Waterloo-Barrie",
    "Hamilton-Niagara Peninsula",
    "London",
    "Windsor-Sarnia",
    "Stratford-Bruce Peninsula",
]


def _process_seph(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process raw SEPH table (14-10-0203-01) into a clean annual time-series.
    Filters to Ontario geographies and selected NAICS industries.
    """
    print("  Processing SEPH data...")
    # Normalize column names (StatCan CSV headers vary slightly)
    df.columns = [c.strip() for c in df.columns]

    # Rename common StatCan column aliases
    col_aliases = {
        "REF_DATE": "ref_date",
        "GEO": "geo",
        "DGUID": "dguid",
        "North American Industry Classification System (NAICS)": "naics",
        "NAICS": "naics",
        "Type of employee": "employee_type",
        "VALUE": "value",
        "UOM": "unit",
        "STATUS": "status",
        "SCALAR_FACTOR": "scalar",
    }
    df = df.rename(columns={k: v for k, v in col_aliases.items() if k in df.columns})

    # Require minimum columns
    needed = {"ref_date", "geo", "value"}
    if not needed.issubset(df.columns):
        print(f"  [WARNING] SEPH: missing columns. Got: {list(df.columns)}")
        return pd.DataFrame()

    # Filter: Ontario geographies
    ontario_mask = df["geo"].str.contains(
        "Ontario", case=False, na=False
    )
    df = df[ontario_mask].copy()

    # Parse date → year (SEPH ref_date is typically "2024-01" monthly)
    df["year"] = pd.to_datetime(df["ref_date"], errors="coerce").dt.year
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)

    # Filter: Total employees (not just full-time/part-time)
    if "employee_type" in df.columns:
        df = df[df["employee_type"].str.contains("Total employees", case=False, na=False)]

    # Filter: known NAICS industries if column present
    if "naics" in df.columns:
        # Map verbose labels to short names
        df["industry"] = df["naics"].map(
            lambda x: next(
                (v for k, v in SEPH_INDUSTRY_MAP.items() if k.lower() in str(x).lower()),
                None
            )
        )
        df = df.dropna(subset=["industry"])
    else:
        df["industry"] = "All Industries"

    # Convert value to numeric
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    # Annual average by geo × industry
    result = (
        df.groupby(["year", "geo", "industry"])["value"]
        .mean()
        .reset_index()
        .rename(columns={"value": "employees_thousands"})
    )

    # Sort
    result = result.sort_values(["geo", "industry", "year"])
    print(f"  SEPH: {len(result):,} rows retained ({result['year'].min()}–{result['year'].max()})")
    return result


def _process_cmhc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process raw CMHC housing starts table (34-10-0143-01).
    Filters to Ontario, returns quarterly starts by type.
    """
    print("  Processing CMHC housing starts data...")
    df.columns = [c.strip() for c in df.columns]

    col_aliases = {
        "REF_DATE": "ref_date",
        "GEO": "geo",
        "Housing estimates": "estimate_type",
        "Type of dwelling unit": "dwelling_type",
        "VALUE": "value",
        "SCALAR_FACTOR": "scalar",
        "UOM": "unit",
    }
    df = df.rename(columns={k: v for k, v in col_aliases.items() if k in df.columns})

    needed = {"ref_date", "geo", "value"}
    if not needed.issubset(df.columns):
        print(f"  [WARNING] CMHC: missing columns. Got: {list(df.columns)}")
        return pd.DataFrame()

    # Filter to Ontario
    df = df[df["geo"].str.contains("Ontario", case=False, na=False)].copy()

    # Parse quarterly date
    df["ref_date_parsed"] = pd.to_datetime(df["ref_date"], errors="coerce")
    df = df.dropna(subset=["ref_date_parsed"])
    df["year"] = df["ref_date_parsed"].dt.year
    df["quarter"] = df["ref_date_parsed"].dt.quarter
    df["period"] = df["ref_date_parsed"].dt.to_period("Q").astype(str)

    # Filter: Housing starts (not completions or under construction)
    if "estimate_type" in df.columns:
        df = df[df["estimate_type"].str.contains("Starts", case=False, na=False)]

    # Keep relevant dwelling types
    DWELLING_TYPE_MAP = {
        "Single": "Single-Detached",
        "Semi-detached": "Semi-Detached",
        "Row": "Row/Townhouse",
        "Apartment": "Apartment/Multi",
        "All types": "All Types",
        "Total": "All Types",
    }
    if "dwelling_type" in df.columns:
        df["dwelling_type_clean"] = df["dwelling_type"].map(
            lambda x: next(
                (v for k, v in DWELLING_TYPE_MAP.items() if k.lower() in str(x).lower()),
                str(x)
            )
        )
    else:
        df["dwelling_type_clean"] = "All Types"

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    result = df[[
        "period", "year", "quarter", "geo", "dwelling_type_clean", "value"
    ]].rename(columns={"dwelling_type_clean": "dwelling_type", "value": "starts"})

    result = result.sort_values(["geo", "dwelling_type", "period"])
    print(f"  CMHC: {len(result):,} rows retained ({result['year'].min()}–{result['year'].max()})")
    return result


def run():
    """Main entry point — download and save both datasets."""
    print("\n--- Rural Labour & Housing Data Fetcher ---")

    # ── Table 1: SEPH (14-10-0203-01) ────────────────────────────────────────
    seph_out = DERIVED_DIR / "rural_labour_seph.parquet"
    print("\n[1/2] Fetching SEPH Table 14-10-0203-01...")
    session = get_robust_session()
    try:
        seph_df, _ = fetch_table("14-10-0203-01", session)
        seph_clean = _process_seph(seph_df)
        if not seph_clean.empty:
            seph_clean.to_parquet(seph_out, index=False)
            print(f"  [OK] Saved -> {seph_out}")
        else:
            print("  [WARNING] No SEPH data retained after processing.")
    except Exception as e:
        print(f"  [ERROR] SEPH fetch failed: {e}")

    # ── Table 2: CMHC Housing Starts (34-10-0143-01) ─────────────────────────
    cmhc_out = DERIVED_DIR / "rural_housing_starts.parquet"
    print("\n[2/2] Fetching CMHC Housing Starts Table 34-10-0143-01...")
    try:
        cmhc_df, _ = fetch_table("34-10-0143-01", session)
        cmhc_clean = _process_cmhc(cmhc_df)
        if not cmhc_clean.empty:
            cmhc_clean.to_parquet(cmhc_out, index=False)
            print(f"  [OK] Saved -> {cmhc_out}")
        else:
            print("  [WARNING] No CMHC data retained after processing.")
    except Exception as e:
        print(f"  [ERROR] CMHC fetch failed: {e}")

    print("\n--- Rural Labour & Housing Fetcher Complete ---")


if __name__ == "__main__":
    run()
