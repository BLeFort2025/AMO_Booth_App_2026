"""
MOF Population Projections Processor
======================================
Parses the Ontario Ministry of Finance 49 Census Division Population Projections
(downloaded from Ontario Data Catalogue) into a clean CSV for use by the
Scenario Planner.

Input:  data/raw/mof_cd_projections.xlsx
Output: data/latest/wellbeing/mof_projections.csv
"""

import pandas as pd
from pathlib import Path

RAW_FILE = Path("data/raw/mof_cd_projections.xlsx")
OUT_DIR = Path("data/latest/wellbeing")
OUT_FILE = OUT_DIR / "mof_projections.csv"

# Map MOF region names → our dim_geography county names
# MOF uses uppercase; we normalise via title-case
MOF_NAME_OVERRIDES = {
    "HALDIMAND-NORFOLK": "Haldimand-Norfolk",
    "KAWARTHA LAKES": "Kawartha Lakes",
    "LENNOX AND ADDINGTON": "Lennox and Addington",
    "LEEDS AND GRENVILLE": "Leeds and Grenville",
    "STORMONT, DUNDAS AND GLENGARRY": "Stormont, Dundas and Glengarry",
    "PRESCOTT AND RUSSELL": "Prescott and Russell",
    "MANITOULIN-SUDBURY": "Manitoulin-Sudbury",
    "COCHRANE": "Cochrane",
    "TIMISKAMING": "Timiskaming",
    "NIPISSING": "Nipissing",
    "PARRY SOUND": "Parry Sound",
    "THUNDER BAY": "Thunder Bay",
    "RAINY RIVER": "Rainy River",
    "KENORA": "Kenora",
    "GREATER SUDBURY": "Greater Sudbury",
}


def _normalise_name(mof_name: str) -> str:
    """Convert MOF uppercase region name to title-case county name."""
    name = mof_name.strip()
    if name in MOF_NAME_OVERRIDES:
        return MOF_NAME_OVERRIDES[name]
    return name.title()


def run():
    """Parse MOF XLSX → clean CSV with broad age bands and 5-year cohorts."""
    print("Processing MOF Population Projections...")

    if not RAW_FILE.exists():
        print(f"  [ERROR] {RAW_FILE} not found.")
        print("  Download from: https://data.ontario.ca/dataset/population-projections")
        return None

    # Read the XLSX — header is at row 5 (0-indexed row 4)
    df = pd.read_excel(RAW_FILE, sheet_name=0, header=4)
    print(f"  Raw rows: {len(df):,}")

    # Drop empty rows
    df = df.dropna(subset=["YEAR (JULY 1)"])

    # Rename columns
    col_map = {
        "YEAR (JULY 1)": "year",
        "REGION CODE": "cd_code",
        "REGION NAME": "cd_name",
        "GENDER": "gender",
        "TOTAL": "total",
        "0 to 14": "age_0_14",
        "15 to 64": "age_15_64",
        "65 Plus": "age_65_plus",
    }

    # Also capture 5-year cohorts if present
    five_yr = {
        "0 to 4": "age_0_4",
        "5 to 9": "age_5_9",
        "10 to 14": "age_10_14",
        "15 to 19": "age_15_19",
        "20 to 24": "age_20_24",
        "25 to 29": "age_25_29",
        "30 to 34": "age_30_34",
        "35 to 39": "age_35_39",
        "40 to 44": "age_40_44",
        "45 to 49": "age_45_49",
        "50 to 54": "age_50_54",
        "55 to 59": "age_55_59",
        "60 to 64": "age_60_64",
        "65 to 69": "age_65_69",
        "70 to 74": "age_70_74",
        "75 to 79": "age_75_79",
        "80 to 84": "age_80_84",
        "85 to 89": "age_85_89",
        "90 Plus": "age_90_plus",
    }

    # Merge all column mappings, keeping only columns that exist
    all_maps = {**col_map, **five_yr}
    existing = {k: v for k, v in all_maps.items() if k in df.columns}
    df = df[list(existing.keys())].rename(columns=existing)

    # Convert types
    df["year"] = df["year"].astype(int)
    df["cd_code"] = df["cd_code"].astype(int)

    # Normalise county name to match dim_geography
    df["county"] = df["cd_name"].apply(_normalise_name)

    # Filter to "TOTAL BOTH GENDERS" for the primary projection
    # Keep gender-split data too for age pyramids
    df_total = df[df["gender"] == "TOTAL BOTH GENDERS"].copy()
    df_total = df_total.drop(columns=["gender", "cd_name"])

    # Convert numeric columns
    num_cols = [c for c in df_total.columns if c.startswith("age_") or c == "total"]
    for c in num_cols:
        df_total[c] = pd.to_numeric(df_total[c], errors="coerce")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_total.to_csv(OUT_FILE, index=False)
    print(f"  Saved {len(df_total)} rows to {OUT_FILE}")
    print(f"  CDs: {df_total['county'].nunique()}")
    print(f"  Years: {df_total['year'].min()} – {df_total['year'].max()}")

    # Also save gender-split data for age pyramids
    gender_file = OUT_DIR / "mof_projections_by_gender.csv"
    df_gender = df[df["gender"] != "TOTAL BOTH GENDERS"].copy()
    df_gender["county"] = df_gender["cd_name"].apply(_normalise_name)
    df_gender = df_gender.drop(columns=["cd_name"])
    for c in num_cols:
        if c in df_gender.columns:
            df_gender[c] = pd.to_numeric(df_gender[c], errors="coerce")
    df_gender.to_csv(gender_file, index=False)
    print(f"  Gender split: {len(df_gender)} rows → {gender_file.name}")

    return df_total


if __name__ == "__main__":
    run()
