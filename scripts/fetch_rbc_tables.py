"""
One-off script to fetch the 4 RBC Capital Gains StatCan tables,
filter them to agriculture-relevant NAICS industries, and save
trimmed CSVs to data/latest so the live app doesn't OOM.

These tables cover ALL industries (hundreds of NAICS codes) which
makes them too large to fetch/hold in memory on Streamlit Cloud.
We pre-filter to keep only agriculture (111-112), food manufacturing
(311), and a few reference industries for context.
"""
import io
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import requests
from scripts.http_utils import get_robust_session


DATA_LATEST = PROJECT_ROOT / "data" / "latest"
DATA_LATEST.mkdir(parents=True, exist_ok=True)

# Agriculture-relevant NAICS keywords to keep
AG_NAICS_PATTERNS = [
    "crop production",
    "animal production",
    "agriculture",
    "farming",
    "food manufacturing",
    "food and beverage",
    "111",
    "112",
    "311",
    "total",
    "all industries",
    "business sector",
    "aggregate",
]


def csv_zip_url(table_id: str) -> str:
    pid = table_id.replace("-", "")
    file_id = pid[:8]
    return f"https://www150.statcan.gc.ca/n1/tbl/csv/{file_id}-eng.zip"


# Setup robust session
session = get_robust_session()


def fetch_raw(table_id: str) -> pd.DataFrame:
    url = csv_zip_url(table_id)
    print(f"  Downloading {table_id} from {url}...")
    r = session.get(url, timeout=300, verify=False)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    preferred = [n for n in csv_names if "metadata" not in n.lower()]
    chosen = sorted(preferred)[0] if preferred else sorted(csv_names)[0]
    with z.open(chosen) as f:
        df = pd.read_csv(f, low_memory=False)
    print(f"  Raw rows: {len(df):,}")
    return df


def filter_ag_industries(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to agriculture-relevant rows based on NAICS industry columns."""
    # Find the industry/NAICS column
    industry_col = None
    for candidate in [
        "North American Industry Classification System (NAICS)",
        "NAICS",
        "Industry",
        "Sector",
    ]:
        if candidate in df.columns:
            industry_col = candidate
            break

    if industry_col is None:
        # Try fuzzy match
        for col in df.columns:
            if "naics" in col.lower() or "industry" in col.lower() or "sector" in col.lower():
                industry_col = col
                break

    if industry_col is None:
        print("  WARNING: No industry column found — keeping all rows")
        return df

    print(f"  Industry column: '{industry_col}'")
    print(f"  Unique industries: {df[industry_col].nunique()}")

    # Build mask: keep rows where industry matches any ag pattern
    mask = pd.Series(False, index=df.index)
    industry_lower = df[industry_col].astype(str).str.lower()
    for pattern in AG_NAICS_PATTERNS:
        mask = mask | industry_lower.str.contains(pattern.lower(), na=False)

    filtered = df[mask].copy()
    print(f"  Filtered rows: {len(filtered):,} (from {len(df):,})")
    print(f"  Kept industries: {sorted(filtered[industry_col].unique().tolist())}")
    return filtered


def process_table(table_id: str):
    print(f"\n{'='*60}")
    print(f"Processing {table_id}")
    print(f"{'='*60}")

    df = fetch_raw(table_id)
    filtered = filter_ag_industries(df)

    if table_id == "36-10-0096-01":
        # Filter years >= 1997
        if "REF_DATE" in filtered.columns:
            years = pd.to_numeric(filtered["REF_DATE"].astype(str).str[:4], errors="coerce")
            filtered = filtered[years >= 1997].copy()
        
        # Exclude territories to keep file size under 50MB
        if "GEO" in filtered.columns:
            keep_geos = [
                "Canada",
                "Newfoundland and Labrador",
                "Prince Edward Island",
                "Nova Scotia",
                "New Brunswick",
                "Quebec",
                "Ontario",
                "Manitoba",
                "Saskatchewan",
                "Alberta",
                "British Columbia"
            ]
            filtered = filtered[filtered["GEO"].isin(keep_geos)].copy()

    out_path = DATA_LATEST / f"{table_id}.csv"
    filtered.to_csv(out_path, index=False)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"  Saved to {out_path} ({size_mb:.1f} MB)")
    return filtered


if __name__ == "__main__":
    tables = [
        "36-10-0096-01",  # Capital formation by industry
        "36-10-0488-01",  # Gross output by industry
        "36-10-0434-03",  # GDP by industry
        "36-10-0217-01",  # Multifactor productivity
    ]

    for tid in tables:
        try:
            process_table(tid)
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone! All filtered CSVs saved to data/latest/")
