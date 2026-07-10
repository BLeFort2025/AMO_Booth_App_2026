"""
ETL pipeline for OFA member survey data.

Parses raw survey exports into clean, normalized CSVs:
  - confidence_panel.csv   — 3-year panel of Farm Business Confidence (2023-2025)
  - insurance_2025.csv     — Farm Insurance survey responses
  - county_map.csv         — survey county → dim_geography county mapping

Usage:
    python scripts/etl_surveys.py
"""
from pathlib import Path
import pandas as pd
import numpy as np
import re

SURVEY_DIR = Path(__file__).resolve().parents[1] / "data" / "surveys"

# ────────────────────────────────────────────────────────
#  County normalization: OFA survey names → dim_geography
# ────────────────────────────────────────────────────────
COUNTY_MAP = {
    # Direct matches (already correct)
    "Algoma": "Algoma",
    "Brant": "Brant",
    "Bruce": "Bruce",
    "Cochrane": "Cochrane",
    "Dufferin": "Dufferin",
    "Durham": "Durham",
    "Elgin": "Elgin",
    "Essex": "Essex",
    "Frontenac": "Frontenac",
    "Grey": "Grey",
    "Halton": "Halton",
    "Hastings": "Hastings",
    "Huron": "Huron",
    "Kenora": "Kenora",
    "Lambton": "Lambton",
    "Lanark": "Lanark",
    "Middlesex": "Middlesex",
    "Muskoka": "Muskoka",
    "Northumberland": "Northumberland",
    "Ottawa": "Ottawa",
    "Oxford": "Oxford",
    "Peel": "Peel",
    "Perth": "Perth",
    "Peterborough": "Peterborough",
    "Simcoe": "Simcoe",
    "Waterloo": "Waterloo",
    "Wellington": "Wellington",
    "York": "York",
    "Prince Edward": "Prince Edward",
    "Rainy River": "Rainy River",
    "Renfrew": "Renfrew",
    "Thunder Bay": "Thunder Bay",
    # Renamed / split counties
    "Haldimand": "Haldimand-Norfolk",
    "Norfolk": "Haldimand-Norfolk",
    "Hamilton-Wentworth": "Hamilton",
    "Hamilton": "Hamilton",
    "Kent": "Chatham-Kent",
    "Chatham-Kent": "Chatham-Kent",
    "Niagara (North and South)": "Niagara",
    "Niagara": "Niagara",
    "Temiskaming": "Timiskaming",
    "Timiskaming": "Timiskaming",
    "Kawartha Lakes": "Kawartha Lakes",
    "Kawartha Lakes – Haliburton": "Kawartha Lakes",
    "Haliburton": "Haliburton",
    # SDG split
    "Dundas": "Stormont, Dundas and Glengarry",
    "Glengarry": "Stormont, Dundas and Glengarry",
    "Stormont": "Stormont, Dundas and Glengarry",
    "Stormont, Dundas and Glengarry": "Stormont, Dundas and Glengarry",
    # LG split
    "Leeds": "Leeds and Grenville",
    "Grenville": "Leeds and Grenville",
    "Leeds and Grenville": "Leeds and Grenville",
    # PR split
    "Prescott": "Prescott and Russell",
    "Russell": "Prescott and Russell",
    "Prescott and Russell": "Prescott and Russell",
    # LA
    "Lennox & Addington": "Lennox and Addington",
    "Lennox and Addington": "Lennox and Addington",
    # Composite northern OFA counties
    "East Nipissing – Parry Sound": "Nipissing",
    "East Nipissing - Parry Sound": "Nipissing",
    "West Nipissing – Sudbury East": "Nipissing",
    "West Nipissing - Sudbury East": "Nipissing",
    "Manitoulin-North Shore – Sudbury West": "Manitoulin",
    "Manitoulin-North Shore - Sudbury West": "Manitoulin",
    "Manitoulin": "Manitoulin",
    "Kenora – Dryden": "Kenora",
    "Kenora - Dryden": "Kenora",
    "Arnprior": "Renfrew",
    "Parry Sound": "Parry Sound",
    "Nipissing": "Nipissing",
    "Sudbury": "Sudbury",
    "Greater Sudbury": "Greater Sudbury / Grand Sudbury",
    "Toronto": "Toronto",
}


def normalize_county(raw: str) -> str:
    """Map a raw survey county name to the dim_geography standard."""
    if pd.isna(raw) or str(raw).strip() == "":
        return np.nan
    cleaned = str(raw).strip()
    return COUNTY_MAP.get(cleaned, cleaned)


# ────────────────────────────────────────────────────────
#  Multi-select column flattener
#  Survey exports spread multi-select into Unnamed columns
# ────────────────────────────────────────────────────────
def flatten_multiselect(df: pd.DataFrame, anchor_col: str) -> pd.Series:
    """
    Given a named anchor column followed by Unnamed: N columns that hold
    the multi-select spill, collapse them into a single semicolon-delimited
    string per row.
    """
    idx = df.columns.get_loc(anchor_col)
    # Collect consecutive Unnamed columns after the anchor
    spill_cols = [anchor_col]
    for j in range(idx + 1, len(df.columns)):
        if str(df.columns[j]).startswith("Unnamed:"):
            spill_cols.append(df.columns[j])
        else:
            break
    parts = df[spill_cols].apply(
        lambda row: ";".join(str(v) for v in row if pd.notna(v) and str(v).strip()), axis=1
    )
    return parts


# ────────────────────────────────────────────────────────
#  Confidence survey parser
# ────────────────────────────────────────────────────────
CONFIDENCE_QUESTION_MAP = {
    "county": "Please select your County or Region",
    "gross_income": None,  # matched by substring
    "farm_structure": "How is your farm business structured?",
    "age": None,  # matched by substring
    "confidence_outlook": None,  # matched by substring "confident"
    "growth_expectation": None,  # matched by substring "growth" or "change"
    "machinery_investment": None,  # matched by substring "machinery"
    "energy_investment": None,  # matched by substring "energy efficiency"
    "tax_impact": None,  # matched by substring "type of tax"
}


def _find_col(df: pd.DataFrame, *substrings) -> str | None:
    """Find a column whose name contains ALL given substrings (case-insensitive)."""
    for c in df.columns:
        cl = str(c).lower()
        if all(s.lower() in cl for s in substrings):
            return c
    return None


def parse_confidence_survey(path: Path, year: int) -> pd.DataFrame:
    """Parse a single confidence survey file into a clean DataFrame."""
    if path.suffix == ".xlsx":
        raw = pd.read_excel(path)
    else:
        try:
            raw = pd.read_csv(path, encoding="utf-8")
        except UnicodeDecodeError:
            raw = pd.read_csv(path, encoding="latin1")

    # Drop the header-description row (row 0 often has "Response" as value)
    if str(raw.iloc[0, 0]).strip() in ("Response", "response"):
        raw = raw.iloc[1:].reset_index(drop=True)

    records = []
    county_col = _find_col(raw, "county") or _find_col(raw, "region")
    income_col = _find_col(raw, "gross farm income") or _find_col(raw, "farm sales")
    age_col = _find_col(raw, "your age") or _find_col(raw, "indicate your age")
    structure_col = _find_col(raw, "farm business structured")
    confidence_col = _find_col(raw, "confident", "outlook")
    growth_col = _find_col(raw, "growth") or _find_col(raw, "change")
    machinery_col = _find_col(raw, "machinery")
    energy_col = _find_col(raw, "energy efficiency")
    tax_col = _find_col(raw, "type of tax")

    # Find commodity columns (multi-select starting with the commodity question)
    commodity_col = _find_col(raw, "commodit") or _find_col(raw, "produce")

    # Find challenge columns
    challenge_col = _find_col(raw, "challenge")

    # Find policy priority columns
    policy_col = _find_col(raw, "policy priorit")

    for i, row in raw.iterrows():
        rec = {"year": year}
        rec["county_raw"] = row[county_col] if county_col else np.nan
        rec["county"] = normalize_county(rec["county_raw"])
        rec["gross_income"] = row[income_col] if income_col else np.nan
        rec["age"] = row[age_col] if age_col else np.nan
        rec["farm_structure"] = row[structure_col] if structure_col else np.nan
        rec["confidence_outlook"] = row[confidence_col] if confidence_col else np.nan
        rec["growth_expectation"] = row[growth_col] if growth_col else np.nan
        rec["machinery_investment"] = row[machinery_col] if machinery_col else np.nan
        rec["energy_investment"] = row[energy_col] if energy_col else np.nan
        rec["tax_impact"] = row[tax_col] if tax_col else np.nan

        # Flatten multi-selects
        if commodity_col:
            rec["commodities"] = flatten_multiselect(raw, commodity_col).iloc[
                i - raw.index[0]
            ] if (i - raw.index[0]) < len(raw) else ""
        if challenge_col:
            rec["challenges"] = flatten_multiselect(raw, challenge_col).iloc[
                i - raw.index[0]
            ] if (i - raw.index[0]) < len(raw) else ""
        if policy_col:
            rec["policy_priorities"] = flatten_multiselect(raw, policy_col).iloc[
                i - raw.index[0]
            ] if (i - raw.index[0]) < len(raw) else ""

        records.append(rec)

    df = pd.DataFrame(records)
    # Clean up
    df = df[df["county"].notna() & (df["county"] != "")]
    return df


# ────────────────────────────────────────────────────────
#  Insurance survey parser
# ────────────────────────────────────────────────────────
def parse_insurance_survey(path: Path) -> pd.DataFrame:
    """Parse the Farm Insurance Survey 2025."""
    raw = pd.read_csv(path)
    if str(raw.iloc[0, 0]).strip() in ("Response", "response"):
        raw = raw.iloc[1:].reset_index(drop=True)

    county_col = _find_col(raw, "county") or _find_col(raw, "region")
    income_col = _find_col(raw, "gross farm income")
    age_col = _find_col(raw, "your age") or _find_col(raw, "indicate your age")
    drao_col = _find_col(raw, "DRAO") or _find_col(raw, "disaster recovery")
    agritourism_col = _find_col(raw, "agritourism") or _find_col(raw, "diversified")

    # Insurance types (multi-select)
    insurance_col = _find_col(raw, "private insurance policies")

    records = []
    for i, row in raw.iterrows():
        rec = {}
        rec["county_raw"] = row[county_col] if county_col else np.nan
        rec["county"] = normalize_county(rec["county_raw"])
        rec["gross_income"] = row[income_col] if income_col else np.nan
        rec["age"] = row[age_col] if age_col else np.nan
        rec["drao_received"] = row[drao_col] if drao_col else np.nan
        rec["has_agritourism"] = row[agritourism_col] if agritourism_col else np.nan

        if insurance_col:
            rec["insurance_types"] = flatten_multiselect(raw, insurance_col).iloc[
                i - raw.index[0]
            ] if (i - raw.index[0]) < len(raw) else ""

        records.append(rec)

    df = pd.DataFrame(records)
    df = df[df["county"].notna() & (df["county"] != "")]
    return df


# ────────────────────────────────────────────────────────
#  Main
# ────────────────────────────────────────────────────────
def main():
    print("=== OFA Survey ETL ===\n")

    # 1. Parse confidence surveys
    conf_frames = []
    for fname, year in [
        ("confidence_2023.xlsx", 2023),
        ("confidence_2024.csv", 2024),
        ("confidence_2025.csv", 2025),
    ]:
        fp = SURVEY_DIR / fname
        if fp.exists():
            print(f"  Parsing {fname}...")
            df = parse_confidence_survey(fp, year)
            print(f"    {len(df)} respondents, {df['county'].nunique()} counties")
            conf_frames.append(df)
        else:
            print(f"  SKIP: {fname} not found")

    if conf_frames:
        panel = pd.concat(conf_frames, ignore_index=True)
        out = SURVEY_DIR / "confidence_panel.csv"
        panel.to_csv(out, index=False)
        print(f"\n  Saved {out.name}: {len(panel)} rows, {panel['year'].nunique()} years")

    # 2. Parse insurance survey
    ins_path = SURVEY_DIR / "farm_insurance_2025.csv"
    if ins_path.exists():
        print(f"\n  Parsing farm_insurance_2025.csv...")
        ins_df = parse_insurance_survey(ins_path)
        out = SURVEY_DIR / "insurance_2025.csv"
        ins_df.to_csv(out, index=False)
        print(f"  Saved {out.name}: {len(ins_df)} rows")

    # 3. Save county map for reference
    cmap = pd.DataFrame(
        [(k, v) for k, v in sorted(COUNTY_MAP.items())],
        columns=["survey_county", "geo_county"],
    )
    cmap.to_csv(SURVEY_DIR / "county_map.csv", index=False)
    print(f"\n  Saved county_map.csv: {len(cmap)} mappings")

    print("\nDone.")


if __name__ == "__main__":
    main()
