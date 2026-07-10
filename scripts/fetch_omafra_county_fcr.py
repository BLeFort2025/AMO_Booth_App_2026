"""
Fetch and process OMAFRA Ontario Farm Cash Receipts by County & Commodity.

Source: https://data.ontario.ca/dataset/ontario-farm-cash-receipts-by-county-and-crop
License: Open Government Licence – Ontario

Output: data/latest/omafra_county_fcr.csv
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("data/latest")
XLSX_FILE = DATA_DIR / "fcrcty_en.xlsx"
OUTPUT_FILE = DATA_DIR / "omafra_county_fcr.csv"

# Regional aggregation rows — these must be excluded to avoid double-counting.
# OMAFRA groups counties into 5 regions and includes subtotal rows.
REGION_ROWS = {
    "Southern Ontario Region",
    "Western Ontario Region",
    "Central Ontario Region",
    "Eastern Ontario Region",
    "Northern Ontario Region",
    "PROVINCE",
}

# Normalize OMAFRA county names to match the CEAG/Census style (lowercase, underscored)
COUNTY_NAME_MAP = {
    "Brant County": "brant",
    "Chatham-Kent Division": "chatham_kent",
    "Elgin County": "elgin",
    "Essex County": "essex",
    "Haldimand-Norfolk Regional Municipality": "haldimand_norfolk",
    "Hamilton Division": "hamilton",
    "Lambton County": "lambton",
    "Middlesex County": "middlesex",
    "Niagara Regional Municipality": "niagara",
    "Oxford County": "oxford",
    "Bruce County": "bruce",
    "Dufferin County": "dufferin",
    "Grey County": "grey",
    "Halton Regional Municipality": "halton",
    "Huron County": "huron",
    "Peel Regional Municipality": "peel",
    "Perth County": "perth",
    "Simcoe County": "simcoe",
    "Waterloo Regional Municipality": "waterloo",
    "Wellington County": "wellington",
    "Durham Regional Municipality": "durham",
    "Haliburton County": "haliburton",
    "Hastings County": "hastings",
    "Kawartha Lakes Division": "kawartha_lakes",
    "Muskoka District Municipality": "muskoka",
    "Northumberland County": "northumberland",
    "Parry Sound District": "parry_sound",
    "Peterborough County": "peterborough",
    "Prince Edward Division": "prince_edward",
    "York Regional Municipality": "york",
    "Frontenac County": "frontenac",
    "Lanark County": "lanark",
    "Leeds and Grenville United Counties": "leeds_and_grenville",
    "Lennox and Addington County": "lennox_and_addington",
    "Ottawa Division": "ottawa",
    "Prescott and Russell United Counties": "prescott_and_russell",
    "Renfrew County": "renfrew",
    "Stormont, Dundas and Glengarry Counties": "stormont",
    "Algoma": "algoma",
    "Cochrane": "cochrane",
    "Greater Sudbury / Grand Sudbury": "greater_sudbury",
    "Kenora": "kenora",
    "Manitoulin": "manitoulin",
    "Nipissing": "nipissing",
    "Rainy River": "rainy_river",
    "Sudbury": "sudbury",
    "Thunder Bay": "thunder_bay",
    "Timiskaming": "timiskaming",
}

# Display names for UI (Title Case, professional)
COUNTY_DISPLAY_NAMES = {
    "brant": "Brant County",
    "chatham_kent": "Chatham-Kent",
    "elgin": "Elgin County",
    "essex": "Essex County",
    "haldimand_norfolk": "Haldimand-Norfolk",
    "hamilton": "Hamilton",
    "lambton": "Lambton County",
    "middlesex": "Middlesex County",
    "niagara": "Niagara Region",
    "oxford": "Oxford County",
    "bruce": "Bruce County",
    "dufferin": "Dufferin County",
    "grey": "Grey County",
    "halton": "Halton Region",
    "huron": "Huron County",
    "peel": "Peel Region",
    "perth": "Perth County",
    "simcoe": "Simcoe County",
    "waterloo": "Waterloo Region",
    "wellington": "Wellington County",
    "durham": "Durham Region",
    "haliburton": "Haliburton County",
    "hastings": "Hastings County",
    "kawartha_lakes": "Kawartha Lakes",
    "muskoka": "Muskoka District",
    "northumberland": "Northumberland County",
    "parry_sound": "Parry Sound District",
    "peterborough": "Peterborough County",
    "prince_edward": "Prince Edward County",
    "york": "York Region",
    "frontenac": "Frontenac County",
    "lanark": "Lanark County",
    "leeds_and_grenville": "Leeds & Grenville",
    "lennox_and_addington": "Lennox & Addington",
    "ottawa": "Ottawa",
    "prescott_and_russell": "Prescott & Russell",
    "renfrew": "Renfrew County",
    "stormont": "Stormont, Dundas & Glengarry",
    "algoma": "Algoma District",
    "cochrane": "Cochrane District",
    "greater_sudbury": "Greater Sudbury",
    "kenora": "Kenora District",
    "manitoulin": "Manitoulin District",
    "nipissing": "Nipissing District",
    "rainy_river": "Rainy River District",
    "sudbury": "Sudbury District",
    "thunder_bay": "Thunder Bay District",
    "timiskaming": "Timiskaming District",
}

# OMAFRA regional grouping for each county
COUNTY_REGION = {
    # Southern Ontario
    "brant": "Southern Ontario",
    "chatham_kent": "Southern Ontario",
    "elgin": "Southern Ontario",
    "essex": "Southern Ontario",
    "haldimand_norfolk": "Southern Ontario",
    "hamilton": "Southern Ontario",
    "lambton": "Southern Ontario",
    "middlesex": "Southern Ontario",
    "niagara": "Southern Ontario",
    "oxford": "Southern Ontario",
    # Western Ontario
    "bruce": "Western Ontario",
    "dufferin": "Western Ontario",
    "grey": "Western Ontario",
    "halton": "Western Ontario",
    "huron": "Western Ontario",
    "peel": "Western Ontario",
    "perth": "Western Ontario",
    "simcoe": "Western Ontario",
    "waterloo": "Western Ontario",
    "wellington": "Western Ontario",
    # Central Ontario
    "durham": "Central Ontario",
    "haliburton": "Central Ontario",
    "hastings": "Central Ontario",
    "kawartha_lakes": "Central Ontario",
    "muskoka": "Central Ontario",
    "northumberland": "Central Ontario",
    "parry_sound": "Central Ontario",
    "peterborough": "Central Ontario",
    "prince_edward": "Central Ontario",
    "york": "Central Ontario",
    # Eastern Ontario
    "frontenac": "Eastern Ontario",
    "lanark": "Eastern Ontario",
    "leeds_and_grenville": "Eastern Ontario",
    "lennox_and_addington": "Eastern Ontario",
    "ottawa": "Eastern Ontario",
    "prescott_and_russell": "Eastern Ontario",
    "renfrew": "Eastern Ontario",
    "stormont": "Eastern Ontario",
    # Northern Ontario
    "algoma": "Northern Ontario",
    "cochrane": "Northern Ontario",
    "greater_sudbury": "Northern Ontario",
    "kenora": "Northern Ontario",
    "manitoulin": "Northern Ontario",
    "nipissing": "Northern Ontario",
    "rainy_river": "Northern Ontario",
    "sudbury": "Northern Ontario",
    "thunder_bay": "Northern Ontario",
    "timiskaming": "Northern Ontario",
}


def process_omafra_fcr():
    """Process the OMAFRA XLSX into a tidy CSV with county shares."""
    if not XLSX_FILE.exists():
        raise FileNotFoundError(f"OMAFRA XLSX not found: {XLSX_FILE}")

    xls = pd.ExcelFile(XLSX_FILE)
    all_frames = []

    for sheet in xls.sheet_names:
        # Extract year from sheet name (e.g., "FCR2024_EN" -> 2024)
        year = int(sheet.replace("FCR", "").replace("_EN", ""))

        df = pd.read_excel(xls, sheet_name=sheet, header=3)

        # Drop footnote/metadata rows
        df = df[df["County"].notna()].copy()
        df["County"] = df["County"].astype(str).str.strip()
        df = df[~df["County"].str.startswith("*")]
        df = df[~df["County"].str.startswith("Reference")]
        # Filter out date-like rows (e.g., "2022-07-08 00:00:00")
        df = df[~df["County"].str.match(r'^\d{4}-\d{2}-\d{2}')]
        df = df[~df["County"].str.match(r'^\w+\s+\d+\s+\d{4}')]

        # Separate province total and region subtotals
        province_row = df[df["County"] == "PROVINCE"]
        region_rows = df[df["County"].apply(
            lambda x: x.strip() in REGION_ROWS or x.strip().rstrip(" ") + " Region" in REGION_ROWS
        )]
        counties = df[~df["County"].isin(region_rows["County"].tolist())].copy()
        counties = counties[~counties["County"].str.endswith("Region")]
        counties = counties[~counties["County"].str.endswith("Region ")]

        # Get the provincial total from the "Total Farm Cash Receipts" column
        # If missing, sum across commodity columns
        total_col = "Total Farm Cash Receipts"
        if total_col not in df.columns:
            # Find the rightmost numeric column as total
            numeric_cols = [c for c in df.columns if c != "County"]
            total_col = numeric_cols[-1]

        prov_total = province_row[total_col].values[0] if not province_row.empty else 0

        # Melt county data from wide to long
        commodity_cols = [c for c in counties.columns if c not in ["County", total_col]]

        for _, row in counties.iterrows():
            raw_name = row["County"]
            county_slug = COUNTY_NAME_MAP.get(raw_name)
            if not county_slug:
                print(f"  WARNING: Unmapped county name '{raw_name}' in {sheet}")
                continue

            county_total = row[total_col] if pd.notna(row[total_col]) else 0
            share = county_total / prov_total if prov_total > 0 else 0

            # Add total row
            all_frames.append({
                "county": county_slug,
                "county_display": COUNTY_DISPLAY_NAMES.get(county_slug, raw_name),
                "region": COUNTY_REGION.get(county_slug, "Unknown"),
                "year": year,
                "commodity": "Total",
                "value_millions": county_total,
                "provincial_total_millions": prov_total,
                "share_of_province": round(share, 6),
            })

            # Add commodity-level rows
            for commodity in commodity_cols:
                val = row[commodity] if pd.notna(row[commodity]) else 0
                all_frames.append({
                    "county": county_slug,
                    "county_display": COUNTY_DISPLAY_NAMES.get(county_slug, raw_name),
                    "region": COUNTY_REGION.get(county_slug, "Unknown"),
                    "year": year,
                    "commodity": commodity,
                    "value_millions": val,
                    "provincial_total_millions": prov_total,
                    "share_of_province": round(val / prov_total, 6) if prov_total > 0 else 0,
                })

    result = pd.DataFrame(all_frames)

    # Sort for clean output
    result = result.sort_values(["year", "county", "commodity"]).reset_index(drop=True)

    # Validation: county totals should sum close to province total
    for yr in result["year"].unique():
        yr_totals = result[(result["year"] == yr) & (result["commodity"] == "Total")]
        county_sum = yr_totals["value_millions"].sum()
        prov = yr_totals["provincial_total_millions"].iloc[0]
        share_sum = yr_totals["share_of_province"].sum()
        gap_pct = abs(county_sum - prov) / prov * 100 if prov > 0 else 0
        status = "OK" if gap_pct < 5 else "WARN"
        print(f"  {yr}: Counties ${county_sum:,.1f}M / Province ${prov:,.1f}M "
              f"({share_sum:.2%} coverage) [{status}]")

    result.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(result):,} rows to {OUTPUT_FILE}")
    return result


if __name__ == "__main__":
    print("Processing OMAFRA Ontario Farm Cash Receipts by County...")
    process_omafra_fcr()
