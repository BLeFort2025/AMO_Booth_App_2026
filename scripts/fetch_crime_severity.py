"""
Crime Severity Index Fetcher
==============================
Fetches Crime Severity Index data from StatCan Table 35-10-0188-01
(Crime severity index and weighted clearance rates, police services in Ontario)

Maps police service areas to Census Subdivisions (CSDs) using geography matching.

Output: data/latest/wellbeing/crime_severity.csv
"""

import re
import time
import requests
import pandas as pd
from pathlib import Path

# --- Config ---
TABLE_ID = "35100188"  # Crime severity index, police services in Ontario
API_BASE = "https://www150.statcan.gc.ca/t1/tbl1/en/dtl!downloadTbl/en"
WDS_BASE = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action"

OUT_DIR = Path("data/latest/wellbeing")
OUT_FILE = OUT_DIR / "crime_severity.csv"
GEO_FILE = OUT_DIR / "dim_geography.csv"

# StatCan WDS API
GETDATA_URL = "https://www150.statcan.gc.ca/t1/tbl1/en/dtl!downloadTbl/en"


def fetch_from_statcan_api():
    """Fetch Table 35-10-0188 using the CSV bulk download endpoint."""
    print(f"Fetching StatCan Table {TABLE_ID} (Crime Severity Index)...")

    # Use the bulk CSV download endpoint
    url = f"https://www150.statcan.gc.ca/n1/tbl/csv/{TABLE_ID}-eng.zip"
    print(f"  Downloading from: {url}")

    r = requests.get(url, timeout=120)
    if r.status_code != 200:
        print(f"  [ERROR] HTTP {r.status_code}")
        return None

    # Extract CSV from ZIP
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_files = [n for n in z.namelist() if n.endswith(".csv") and "meta" not in n.lower()]
        if not csv_files:
            print("  [ERROR] No data CSV in ZIP")
            return None
        csv_name = csv_files[0]
        print(f"  Using CSV: {csv_name}")
        df = pd.read_csv(io.BytesIO(z.read(csv_name)))

    print(f"  Raw rows: {len(df):,}")
    print(f"  Columns: {list(df.columns)}")
    return df


def _extract_csd_name(geo_str):
    """Extract a clean community name from the police service geography string.
    Examples:
        'Belleville, Ontario, municipal' -> 'Belleville'
        'Bancroft (Bancroft), Ontario, Ontario Provincial Police, municipal' -> 'Bancroft'
        'City of Kawartha Lakes, Ontario, Ontario Provincial Police, rural' -> 'Kawartha Lakes'
    """
    if pd.isna(geo_str):
        return None
    # Take the first segment (before first comma)
    name = str(geo_str).split(",")[0].strip()
    # Remove parenthetical notes like "(Bancroft)" or "(Gravenhurst)"
    name = re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    # Remove "City of", "Town of", "Municipality of" prefixes
    name = re.sub(r"^(City of|Town of|Municipality of|Regional Municipality of|County of|District of)\s+",
                  "", name, flags=re.IGNORECASE).strip()
    return name


def process_crime_data(df):
    """Process raw StatCan Crime Severity data into per-community summary."""
    # Identify key columns
    geo_col = "GEO" if "GEO" in df.columns else df.columns[1]
    ref_period = "REF_DATE" if "REF_DATE" in df.columns else df.columns[0]
    stat_col = "Statistics" if "Statistics" in df.columns else None
    val_col = "VALUE" if "VALUE" in df.columns else "value"

    print(f"\n  GEO column: {geo_col}")
    print(f"  Date column: {ref_period}")

    # Show available statistics
    if stat_col and stat_col in df.columns:
        print(f"  Statistics values: {df[stat_col].unique()[:10]}")

    # Show available years
    years = sorted(df[ref_period].unique())
    print(f"  Years: {years[:5]}...{years[-5:] if len(years) > 5 else ''}")
    latest_year = max(years)
    print(f"  Using latest year: {latest_year}")

    # Filter to latest year
    recent = df[df[ref_period] == latest_year].copy()

    # Filter to key statistics
    key_stats = []
    if stat_col and stat_col in recent.columns:
        all_stats = recent[stat_col].unique()
        for target in ["Crime severity index", "Violent crime severity index",
                       "Non-violent crime severity index", "Weighted clearance rate"]:
            matches = [s for s in all_stats if target.lower() in str(s).lower()]
            if matches:
                key_stats.append(matches[0])
        print(f"  Key statistics found: {key_stats}")
        recent = recent[recent[stat_col].isin(key_stats)]

    print(f"  Filtered rows: {len(recent):,}")

    # Extract community name
    recent["community_name"] = recent[geo_col].apply(_extract_csd_name)

    # Pivot to wide format: one row per community, columns for each stat
    if stat_col and stat_col in recent.columns:
        pivot = recent.pivot_table(
            index=["community_name", geo_col],
            columns=stat_col,
            values=val_col,
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None
    else:
        pivot = recent[["community_name", geo_col, val_col]].copy()
        pivot = pivot.rename(columns={val_col: "Crime severity index"})

    # Clean column names
    col_map = {}
    for c in pivot.columns:
        if "crime severity index" in str(c).lower() and "violent" not in str(c).lower() and "non" not in str(c).lower():
            col_map[c] = "csi_overall"
        elif "violent crime severity" in str(c).lower() and "non" not in str(c).lower():
            col_map[c] = "csi_violent"
        elif "non-violent" in str(c).lower() or "non violent" in str(c).lower():
            col_map[c] = "csi_nonviolent"
        elif "clearance" in str(c).lower():
            col_map[c] = "clearance_rate"
    if col_map:
        pivot = pivot.rename(columns=col_map)

    pivot["ref_year"] = latest_year

    # Try to match to CSD SGC codes using community name
    if GEO_FILE.exists():
        geo = pd.read_csv(GEO_FILE)
        geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)

        # Clean CSD geo_names: strip CSD type suffixes and common prefixes
        def _clean_geo_name(name):
            if pd.isna(name):
                return ""
            n = str(name).strip()
            # Remove CSD type suffix like ", Township (TWP)" or ", City (CY)"
            n = re.sub(r",?\s*(Township|Town|City|Village|Municipality|Indian reserve|Indian settlement)\s*(\(.*?\))?\s*$",
                       "", n, flags=re.IGNORECASE).strip()
            # Remove "(IRI)", "(TWP)", etc. at end
            n = re.sub(r"\s*\([A-Z]{1,4}\)\s*$", "", n).strip()
            return n.lower()

        geo["clean_name"] = geo["geo_name"].apply(_clean_geo_name)
        pivot["name_lower"] = pivot["community_name"].str.lower().str.strip()

        # Build lookup: clean_name -> sgc_code (first match wins)
        geo_lookup = {}
        for _, row in geo.iterrows():
            cn = row["clean_name"]
            if cn and cn not in geo_lookup:
                geo_lookup[cn] = (row["sgc_code"], row["geo_name"], row.get("county", ""))

        # Match crime communities to CSDs
        matched_codes = []
        for _, row in pivot.iterrows():
            crime_name = row["name_lower"]
            if crime_name in geo_lookup:
                matched_codes.append(geo_lookup[crime_name])
            else:
                # Try partial match: check if crime name is contained in any CSD name
                found = None
                for geo_cn, geo_info in geo_lookup.items():
                    if crime_name in geo_cn or geo_cn in crime_name:
                        found = geo_info
                        break
                matched_codes.append(found)

        pivot["sgc_code"] = [m[0] if m else None for m in matched_codes]
        pivot["geo_name"] = [m[1] if m else None for m in matched_codes]
        pivot["county"] = [m[2] if m else None for m in matched_codes]

        matched = pivot["sgc_code"].notna().sum()
        print(f"\n  Matched {matched}/{len(pivot)} police services to CSDs")

        # Show some unmatched for debugging
        unmatched = pivot[pivot["sgc_code"].isna()]["community_name"].head(10).tolist()
        if unmatched:
            print(f"  Sample unmatched: {unmatched[:5]}")

        merged = pivot
    else:
        merged = pivot
        print("  [WARN] No dim_geography.csv found — cannot match to CSDs")

    return merged


def run():
    """Main: fetch, process, and save crime severity data."""
    df = fetch_from_statcan_api()
    if df is None:
        return

    result = process_crime_data(df)

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_FILE, index=False)
    print(f"\n  Saved {len(result)} police service records to {OUT_FILE}")

    # Summary stats
    if "csi_overall" in result.columns:
        print(f"  CSI range: {result['csi_overall'].min():.1f} to {result['csi_overall'].max():.1f}")
        print(f"  CSI median: {result['csi_overall'].median():.1f}")

    return result


if __name__ == "__main__":
    run()
