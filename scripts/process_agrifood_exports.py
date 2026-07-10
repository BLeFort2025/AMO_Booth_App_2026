"""
Download and process StatCan Table 12-10-0175-01 (CIMT) for agri-food exports.

This script:
1. Downloads the full CSV ZIP from Statistics Canada
2. Reads it in chunks to filter to agri-food HS sections only
3. Aggregates monthly data to annual
4. Saves a compact Parquet file for dashboard consumption

Usage:
    python scripts/process_agrifood_exports.py
    python scripts/process_agrifood_exports.py --verify   # verify existing output
"""
import argparse
import io
import ssl
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests
import urllib3

# Suppress InsecureRequestWarning when using verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "latest"

# ---------------------------------------------------------------------------
# Table 12-10-0175-01 — Province/partner breakdown (existing)
# ---------------------------------------------------------------------------
TABLE_ID = "12-10-0175-01"
STATCAN_PID = "12100175"
DOWNLOAD_URL = f"https://www150.statcan.gc.ca/n1/tbl/csv/{STATCAN_PID}-eng.zip"
LOCAL_ZIP = DATA_DIR / f"{STATCAN_PID}-eng.zip"
OUTPUT_PARQUET = DATA_DIR / "agrifood_exports.parquet"
OUTPUT_CSV = DATA_DIR / "agrifood_exports.csv"

# ---------------------------------------------------------------------------
# Table 12-10-0163-01 — Detailed commodity breakdown (NEW)
# ---------------------------------------------------------------------------
DETAILED_TABLE_ID = "12-10-0163-01"
DETAILED_PID = "12100163"
DETAILED_DOWNLOAD_URL = f"https://www150.statcan.gc.ca/n1/tbl/csv/{DETAILED_PID}-eng.zip"
DETAILED_LOCAL_ZIP = DATA_DIR / f"{DETAILED_PID}-eng.zip"
DETAILED_OUTPUT_PARQUET = DATA_DIR / "agrifood_exports_detailed.parquet"
DETAILED_OUTPUT_CSV = DATA_DIR / "agrifood_exports_detailed.csv"

# NAPCS codes to capture from 12-10-0163 for agri-food
# Section C11 — Farm, fishing and intermediate food products
# Section C22 → C221 — Food, beverage and tobacco products
AGRIFOOD_NAPCS_CODES = {
    # C11 — Farm, fishing and intermediate food products
    "111": "Live animals",
    "112": "Wheat",
    "113": "Canola (including rapeseed)",
    "114": "Fresh fruit, nuts, vegetables, pulse crops",
    "115": "Other crop products",
    "116": "Other animal products",
    "121": "Fish, crustaceans, shellfish",
    "181": "Animal feed",
    "182": "Intermediate food products",
    # C221 — Food, beverage and tobacco products
    "171": "Prepared and packaged seafood products",
    "172": "Meat products",
    "173": "Dairy products",
    "183": "Packaged food (cereals, bakery, snacks, confectionery, frozen meals)",
    "191": "Coffee and tea",
    "192": "Fruit and vegetable juices",
    "193": "Carbonated/non-carbonated drinks, bottled water",
    "211": "Alcoholic beverages",
    "212": "Tobacco products",
}

# HS Sections relevant to agri-food & seafood (for table 12-10-0175-01)
# Section I:   Live animals; animal products (HS Ch. 01-05)
# Section II:  Vegetable products (HS Ch. 06-14)
# Section III: Animal or vegetable fats and oils (HS Ch. 15)
# Section IV:  Prepared foodstuffs; beverages, spirits, tobacco (HS Ch. 16-24)
# We also include fish/seafood which falls under Section I
AGRIFOOD_HS_KEYWORDS = [
    "Section I",
    "Section II",
    "Section III",
    "Section IV",
    "Live animals",
    "Animal products",
    "Vegetable products",
    "Animal or vegetable fats",
    "Prepared foodstuffs",
    "Beverages",
    "Fish",
    "Meat",
    "Dairy",
    "Cereals",
    "Oil seeds",
    "Tobacco",
]

def _make_session() -> requests.Session:
    """Create a session with retries and relaxed SSL for StatCan."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_table() -> Path:
    """Download the ZIP file from StatCan if not already present."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if LOCAL_ZIP.exists():
        size_mb = LOCAL_ZIP.stat().st_size / (1024 * 1024)
        print(f"✅ ZIP already exists: {LOCAL_ZIP} ({size_mb:.0f} MB)")
        return LOCAL_ZIP

    print(f"📥 Downloading Table {TABLE_ID} from Statistics Canada...")
    print(f"   URL: {DOWNLOAD_URL}")
    print("   This is a large file and may take several minutes...")

    session = _make_session()
    try:
        r = session.get(DOWNLOAD_URL, timeout=900, stream=True, verify=False)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Download failed: {e}")
        # Clean up partial download
        if LOCAL_ZIP.exists():
            LOCAL_ZIP.unlink()
        sys.exit(1)

    # Stream to disk to avoid memory issues
    total = int(r.headers.get("content-length", 0))
    downloaded = 0
    try:
        with open(LOCAL_ZIP, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192 * 16):
                f.write(chunk)
                downloaded += len(chunk)
                if total and downloaded % (1024 * 1024 * 10) < 8192 * 16:
                    pct = (downloaded / total) * 100
                    print(f"   Progress: {pct:.1f}% ({downloaded / 1e6:.0f} MB / {total / 1e6:.0f} MB)")
    except Exception as e:
        print(f"\n❌ Download interrupted: {e}")
        if LOCAL_ZIP.exists():
            LOCAL_ZIP.unlink()
        sys.exit(1)
    print()

    size_mb = LOCAL_ZIP.stat().st_size / (1024 * 1024)
    print(f"✅ Downloaded: {LOCAL_ZIP} ({size_mb:.0f} MB)")
    return LOCAL_ZIP


def is_agrifood_hs(value: str) -> bool:
    """Check if an HS section/commodity string is agri-food related."""
    if pd.isna(value):
        return False
    val_lower = str(value).lower()
    # Match HS sections I-IV specifically
    for kw in AGRIFOOD_HS_KEYWORDS:
        if kw.lower() in val_lower:
            return True
    return False


def process_table(zip_path: Path) -> pd.DataFrame:
    """Read the ZIP in chunks, filter to agri-food, and aggregate."""
    print(f"\n🔄 Processing {zip_path}...")

    csv_name = f"{STATCAN_PID}.csv"
    chunk_size = 200_000
    chunks = []
    total_rows = 0
    kept_rows = 0

    with zipfile.ZipFile(zip_path) as z:
        # List contents
        names = z.namelist()
        print(f"   ZIP contents: {names}")

        # Find the data CSV (not metadata)
        data_csv = None
        for name in names:
            if name.lower().endswith(".csv") and "metadata" not in name.lower():
                data_csv = name
                break
        if data_csv is None:
            data_csv = csv_name

        print(f"   Reading: {data_csv}")

        with z.open(data_csv) as f:
            iterator = pd.read_csv(f, chunksize=chunk_size, low_memory=False)

            for i, chunk in enumerate(iterator):
                total_rows += len(chunk)

                if i % 20 == 0:
                    print(f"   Chunk {i}... ({total_rows:,.0f} rows scanned, {kept_rows:,.0f} kept)")

                # Identify the commodity column
                commodity_col = None
                for candidate in [
                    "North American Product Classification System (NAPCS)",
                    "Harmonized System (HS)",
                    "Commodity",
                ]:
                    if candidate in chunk.columns:
                        commodity_col = candidate
                        break

                if commodity_col is None:
                    # Try fuzzy match
                    for col in chunk.columns:
                        if any(kw in col.lower() for kw in ["commodity", "hs", "napcs", "product classification"]):
                            commodity_col = col
                            break

                if commodity_col is None:
                    if i == 0:
                        print(f"   ⚠️ Available columns: {list(chunk.columns)}")
                        print("   Keeping all rows (no commodity filter applied)")
                    chunks.append(chunk)
                    kept_rows += len(chunk)
                    continue

                # Filter to agri-food HS sections
                mask = chunk[commodity_col].apply(is_agrifood_hs)
                filtered = chunk[mask].copy()

                if not filtered.empty:
                    chunks.append(filtered)
                    kept_rows += len(filtered)

    if not chunks:
        print("❌ No agri-food rows found!")
        sys.exit(1)

    print(f"\n   ✅ Scan complete: {total_rows:,.0f} total rows → {kept_rows:,.0f} agri-food rows")

    df = pd.concat(chunks, ignore_index=True)

    # Clean up and standardize columns
    print("   Standardizing columns...")

    # Ensure VALUE is numeric
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    # Extract year from REF_DATE
    if "REF_DATE" in df.columns:
        df["YEAR"] = pd.to_datetime(df["REF_DATE"].astype(str).str[:7] + "-01", errors="coerce").dt.year

    # Identify key columns for the output
    trade_col = None
    for c in df.columns:
        if c.lower() == "trade":
            trade_col = c
            break

    geo_col = "GEO" if "GEO" in df.columns else None
    partner_col = None
    for c in df.columns:
        if "trading partner" in c.lower() or "partner" in c.lower():
            partner_col = c
            break

    # Print diagnostics
    print(f"\n   --- DIAGNOSTICS ---")
    print(f"   Columns: {list(df.columns)}")
    if trade_col:
        print(f"   Trade types: {df[trade_col].unique()}")
    if geo_col:
        print(f"   Geographies (first 10): {df[geo_col].unique()[:10]}")
    if partner_col:
        print(f"   Partners (first 10): {df[partner_col].unique()[:10]}")
    if commodity_col and commodity_col in df.columns:
        print(f"   Commodities (first 15): {df[commodity_col].unique()[:15]}")
    if "YEAR" in df.columns:
        print(f"   Years: {sorted(df['YEAR'].dropna().unique().astype(int))}")

    return df


def aggregate_annual(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate monthly data to annual totals."""
    print("\n📊 Aggregating to annual totals...")

    # Identify key grouping columns
    group_cols = ["YEAR"]

    if "GEO" in df.columns:
        group_cols.append("GEO")

    # Find trade column
    trade_col = None
    for c in df.columns:
        if c.lower() == "trade":
            trade_col = c
            group_cols.append(c)
            break

    # Find commodity column (NAPCS in table 12-10-0175-01)
    commodity_col = None
    for c in df.columns:
        if any(kw in c.lower() for kw in ["napcs", "product classification", "commodity", "harmonized", "hs"]):
            commodity_col = c
            group_cols.append(c)
            break

    # Find partner column
    partner_col = None
    for c in df.columns:
        if "trading partner" in c.lower() or "partner" in c.lower():
            partner_col = c
            group_cols.append(c)
            break

    # Only keep rows with valid VALUE and YEAR
    df = df.dropna(subset=["VALUE", "YEAR"])
    df["YEAR"] = df["YEAR"].astype(int)

    # Aggregate
    agg = df.groupby(group_cols, as_index=False)["VALUE"].sum()

    print(f"   Annual rows: {len(agg):,}")
    return agg


def save_output(df: pd.DataFrame) -> None:
    """Save the processed data as Parquet and CSV."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Save Parquet (primary)
    df.to_parquet(OUTPUT_PARQUET, index=False)
    parquet_mb = OUTPUT_PARQUET.stat().st_size / (1024 * 1024)
    print(f"   ✅ Parquet: {OUTPUT_PARQUET} ({parquet_mb:.1f} MB)")

    # Save CSV (fallback for smart_read)
    df.to_csv(OUTPUT_CSV, index=False)
    csv_mb = OUTPUT_CSV.stat().st_size / (1024 * 1024)
    print(f"   ✅ CSV: {OUTPUT_CSV} ({csv_mb:.1f} MB)")


def verify_output() -> bool:
    """Verify the processed output file."""
    print("\n🔍 Verifying output...")

    if not OUTPUT_PARQUET.exists():
        print(f"❌ Output not found: {OUTPUT_PARQUET}")
        return False

    df = pd.read_parquet(OUTPUT_PARQUET)

    checks = []

    # Check rows
    n_rows = len(df)
    checks.append(("Has data", n_rows > 0))
    print(f"   Rows: {n_rows:,}")

    # Check columns
    for col in ["YEAR", "VALUE"]:
        present = col in df.columns
        checks.append((f"Column '{col}' present", present))

    # Check year range
    if "YEAR" in df.columns:
        years = sorted(df["YEAR"].unique())
        checks.append(("Multiple years", len(years) > 1))
        print(f"   Years: {years[0]}–{years[-1]} ({len(years)} years)")

    # Check values
    if "VALUE" in df.columns:
        total = df["VALUE"].sum()
        checks.append(("Non-zero total value", total > 0))
        print(f"   Total value: {total:,.0f}")

    # Check trade types
    trade_col = None
    for c in df.columns:
        if c.lower() == "trade":
            trade_col = c
            break
    if trade_col:
        trades = df[trade_col].unique()
        has_exports = any("export" in str(t).lower() for t in trades)
        checks.append(("Has export data", has_exports))
        print(f"   Trade types: {trades}")

    # Check geographies
    if "GEO" in df.columns:
        geos = df["GEO"].unique()
        print(f"   Geographies: {len(geos)} ({geos[:5]}...)")

    # Summary
    print(f"\n   --- VERIFICATION RESULTS ---")
    all_pass = True
    for label, passed in checks:
        status = "✅" if passed else "❌"
        print(f"   {status} {label}")
        if not passed:
            all_pass = False

    return all_pass


# =============================================================================
# DETAILED COMMODITY TABLE (12-10-0163-01) — NEW
# =============================================================================

def download_detailed_table() -> Path:
    """Download the ZIP file for table 12-10-0163-01 if not already present."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DETAILED_LOCAL_ZIP.exists():
        size_mb = DETAILED_LOCAL_ZIP.stat().st_size / (1024 * 1024)
        print(f"✅ Detailed ZIP already exists: {DETAILED_LOCAL_ZIP} ({size_mb:.0f} MB)")
        return DETAILED_LOCAL_ZIP

    print(f"📥 Downloading Table {DETAILED_TABLE_ID} from Statistics Canada...")
    print(f"   URL: {DETAILED_DOWNLOAD_URL}")
    print("   This is a large file and may take several minutes...")

    session = _make_session()
    try:
        r = session.get(DETAILED_DOWNLOAD_URL, timeout=900, stream=True, verify=False)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Download failed: {e}")
        if DETAILED_LOCAL_ZIP.exists():
            DETAILED_LOCAL_ZIP.unlink()
        sys.exit(1)

    total = int(r.headers.get("content-length", 0))
    downloaded = 0
    try:
        with open(DETAILED_LOCAL_ZIP, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192 * 16):
                f.write(chunk)
                downloaded += len(chunk)
                if total and downloaded % (1024 * 1024 * 10) < 8192 * 16:
                    pct = (downloaded / total) * 100
                    print(f"   Progress: {pct:.1f}% ({downloaded / 1e6:.0f} MB / {total / 1e6:.0f} MB)")
    except Exception as e:
        print(f"\n❌ Download interrupted: {e}")
        if DETAILED_LOCAL_ZIP.exists():
            DETAILED_LOCAL_ZIP.unlink()
        sys.exit(1)
    print()

    size_mb = DETAILED_LOCAL_ZIP.stat().st_size / (1024 * 1024)
    print(f"✅ Downloaded: {DETAILED_LOCAL_ZIP} ({size_mb:.0f} MB)")
    return DETAILED_LOCAL_ZIP


def _is_agrifood_napcs(value: str) -> bool:
    """Check if a NAPCS string starts with one of our target 3-digit codes."""
    if pd.isna(value):
        return False
    val = str(value).strip()
    # NAPCS values typically look like "111 - Live animals" or "[111]"
    for code in AGRIFOOD_NAPCS_CODES:
        # Match at start: "171 " or "[171]" or "171-"
        if val.startswith(code) or f"[{code}]" in val:
            return True
    return False


def _extract_napcs_code(value: str) -> str:
    """Extract the 3-digit NAPCS code from a label like '171 - Prepared seafood'."""
    if pd.isna(value):
        return ""
    val = str(value).strip()
    for code in AGRIFOOD_NAPCS_CODES:
        if val.startswith(code) or f"[{code}]" in val:
            return code
    return val[:3]  # fallback


def process_detailed_table(zip_path: Path) -> pd.DataFrame:
    """Read table 12-10-0163-01 ZIP, filter to agri-food NAPCS codes."""
    print(f"\n🔄 Processing detailed commodity table: {zip_path}...")

    chunk_size = 200_000
    chunks = []
    total_rows = 0
    kept_rows = 0

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        print(f"   ZIP contents: {names}")

        data_csv = None
        for name in names:
            if name.lower().endswith(".csv") and "metadata" not in name.lower():
                data_csv = name
                break
        if data_csv is None:
            data_csv = f"{DETAILED_PID}.csv"

        print(f"   Reading: {data_csv}")

        with z.open(data_csv) as f:
            iterator = pd.read_csv(f, chunksize=chunk_size, low_memory=False)

            for i, chunk in enumerate(iterator):
                total_rows += len(chunk)

                if i % 20 == 0:
                    print(f"   Chunk {i}... ({total_rows:,.0f} rows scanned, {kept_rows:,.0f} kept)")

                # Identify the commodity column
                commodity_col = None
                for candidate in [
                    "North American Product Classification System (NAPCS)",
                    "Commodity",
                    "NAPCS",
                ]:
                    if candidate in chunk.columns:
                        commodity_col = candidate
                        break

                if commodity_col is None:
                    for col in chunk.columns:
                        if any(kw in col.lower() for kw in ["napcs", "product classification", "commodity"]):
                            commodity_col = col
                            break

                if commodity_col is None:
                    if i == 0:
                        print(f"   ⚠️ Available columns: {list(chunk.columns)}")
                        print("   Keeping all rows (no commodity filter applied)")
                    chunks.append(chunk)
                    kept_rows += len(chunk)
                    continue

                # Filter: Customs basis only (skip Balance of payments)
                if "Basis" in chunk.columns:
                    chunk = chunk[chunk["Basis"].str.contains("Customs", case=False, na=False)]

                # Filter: Unadjusted only (skip seasonally adjusted)
                sa_col = None
                for c in chunk.columns:
                    if "seasonal" in c.lower() or "adjustment" in c.lower():
                        sa_col = c
                        break
                if sa_col:
                    chunk = chunk[chunk[sa_col].str.contains("Unadjusted", case=False, na=False)]

                # Filter to agri-food NAPCS codes
                mask = chunk[commodity_col].apply(_is_agrifood_napcs)
                filtered = chunk[mask].copy()

                if not filtered.empty:
                    chunks.append(filtered)
                    kept_rows += len(filtered)

    if not chunks:
        print("❌ No agri-food rows found in detailed table!")
        sys.exit(1)

    print(f"\n   ✅ Scan complete: {total_rows:,.0f} total rows → {kept_rows:,.0f} agri-food rows")

    df = pd.concat(chunks, ignore_index=True)

    # Standard type cleanup
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
        # Table 12-10-0163-01 reports VALUE in millions (SCALAR_FACTOR='millions').
        # Convert to thousands to match table 12-10-0175-01's convention,
        # so the dashboard's fmt_value() function works consistently.
        df["VALUE"] = df["VALUE"] * 1000
        print("   ℹ️ Converted VALUE from millions → thousands (×1000).")

    if "REF_DATE" in df.columns:
        df["YEAR"] = pd.to_datetime(
            df["REF_DATE"].astype(str).str[:7] + "-01", errors="coerce"
        ).dt.year

    # Add a clean NAPCS code column for easier grouping
    if commodity_col and commodity_col in df.columns:
        df["NAPCS_CODE"] = df[commodity_col].apply(_extract_napcs_code)
        df["NAPCS_LABEL"] = df["NAPCS_CODE"].map(AGRIFOOD_NAPCS_CODES).fillna(df[commodity_col])

    # Diagnostics
    trade_col = None
    for c in df.columns:
        if c.lower() == "trade":
            trade_col = c
            break

    print(f"\n   --- DIAGNOSTICS (Detailed) ---")
    print(f"   Columns: {list(df.columns)}")
    if trade_col:
        print(f"   Trade types: {df[trade_col].unique()}")
    if commodity_col and commodity_col in df.columns:
        print(f"   NAPCS commodities found: {sorted(df['NAPCS_CODE'].unique())}")
    if "YEAR" in df.columns:
        print(f"   Years: {sorted(df['YEAR'].dropna().unique().astype(int))}")

    return df


def aggregate_detailed_annual(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate detailed commodity monthly data to annual totals."""
    print("\n📊 Aggregating detailed commodities to annual totals...")

    group_cols = ["YEAR"]

    # Trade type
    trade_col = None
    for c in df.columns:
        if c.lower() == "trade":
            trade_col = c
            group_cols.append(c)
            break

    # NAPCS grouping
    if "NAPCS_CODE" in df.columns:
        group_cols.append("NAPCS_CODE")
    if "NAPCS_LABEL" in df.columns:
        group_cols.append("NAPCS_LABEL")

    # Keep the original commodity column too
    commodity_col = None
    for c in df.columns:
        if any(kw in c.lower() for kw in ["napcs", "product classification"]):
            commodity_col = c
            break

    # Only keep rows with valid VALUE and YEAR
    df = df.dropna(subset=["VALUE", "YEAR"])
    df["YEAR"] = df["YEAR"].astype(int)

    agg = df.groupby(group_cols, as_index=False)["VALUE"].sum()

    print(f"   Annual rows: {len(agg):,}")
    return agg


def save_detailed_output(df: pd.DataFrame) -> None:
    """Save detailed commodity data as Parquet and CSV."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    df.to_parquet(DETAILED_OUTPUT_PARQUET, index=False)
    parquet_mb = DETAILED_OUTPUT_PARQUET.stat().st_size / (1024 * 1024)
    print(f"   ✅ Parquet: {DETAILED_OUTPUT_PARQUET} ({parquet_mb:.1f} MB)")

    df.to_csv(DETAILED_OUTPUT_CSV, index=False)
    csv_mb = DETAILED_OUTPUT_CSV.stat().st_size / (1024 * 1024)
    print(f"   ✅ CSV: {DETAILED_OUTPUT_CSV} ({csv_mb:.1f} MB)")


def verify_detailed_output() -> bool:
    """Verify the detailed commodity output file."""
    print("\n🔍 Verifying detailed commodity output...")

    if not DETAILED_OUTPUT_PARQUET.exists():
        print(f"❌ Output not found: {DETAILED_OUTPUT_PARQUET}")
        return False

    df = pd.read_parquet(DETAILED_OUTPUT_PARQUET)

    checks = []

    n_rows = len(df)
    checks.append(("Has data", n_rows > 0))
    print(f"   Rows: {n_rows:,}")

    for col in ["YEAR", "VALUE"]:
        present = col in df.columns
        checks.append((f"Column '{col}' present", present))

    # Check NAPCS codes
    if "NAPCS_CODE" in df.columns:
        codes = sorted(df["NAPCS_CODE"].unique())
        checks.append(("Has multiple NAPCS codes", len(codes) > 5))
        print(f"   NAPCS codes ({len(codes)}): {codes}")

    # Check year range
    if "YEAR" in df.columns:
        years = sorted(df["YEAR"].unique())
        checks.append(("Multiple years", len(years) > 1))
        print(f"   Years: {years[0]}–{years[-1]} ({len(years)} years)")

    # Check export total for a recent year
    if "YEAR" in df.columns and "VALUE" in df.columns:
        trade_col = None
        for c in df.columns:
            if c.lower() == "trade":
                trade_col = c
                break

        recent_year = max(y for y in df["YEAR"].unique() if y <= 2024)
        df_yr = df[df["YEAR"] == recent_year]
        if trade_col:
            df_exports = df_yr[df_yr[trade_col].str.contains("export", case=False, na=False)]
            export_total = df_exports["VALUE"].sum()
        else:
            export_total = df_yr["VALUE"].sum()

        # Values are in thousands — convert to billions for readability
        export_billions = export_total * 1000 / 1e9
        in_range = 80 <= export_billions <= 120  # should be ~$92-100B
        checks.append((f"Export total for {recent_year} in $80-120B range (got ${export_billions:.1f}B)", in_range))
        print(f"   Export total ({recent_year}): ${export_billions:.1f}B")

    # Summary
    print(f"\n   --- VERIFICATION RESULTS (Detailed) ---")
    all_pass = True
    for label, passed in checks:
        status = "✅" if passed else "❌"
        print(f"   {status} {label}")
        if not passed:
            all_pass = False

    return all_pass


def run():
    parser = argparse.ArgumentParser(description="Process StatCan CIMT agri-food exports")
    parser.add_argument("--verify", action="store_true", help="Verify existing output only")
    parser.add_argument("--skip-download", action="store_true", help="Skip download, use existing ZIP")
    parser.add_argument("--detailed-only", action="store_true", help="Only process the detailed commodity table (12-10-0163)")
    args = parser.parse_args()

    if args.verify:
        ok1 = verify_output()
        ok2 = verify_detailed_output()
        sys.exit(0 if (ok1 and ok2) else 1)

    # =====================================================================
    # Pipeline 1: Table 12-10-0175-01 (province/partner breakdown)
    # =====================================================================
    if not args.detailed_only:
        print("\n" + "=" * 60)
        print("  PIPELINE 1: Table 12-10-0175-01 (Province & Partner)")
        print("=" * 60)

        if not args.skip_download:
            zip_path = download_table()
        else:
            zip_path = LOCAL_ZIP
            if not zip_path.exists():
                print(f"❌ ZIP not found: {zip_path}")
                sys.exit(1)

        df_raw = process_table(zip_path)
        df_annual = aggregate_annual(df_raw)
        save_output(df_annual)

        print("\n" + "=" * 60)
        verify_output()

    # =====================================================================
    # Pipeline 2: Table 12-10-0163-01 (detailed commodity breakdown)
    # =====================================================================
    print("\n" + "=" * 60)
    print("  PIPELINE 2: Table 12-10-0163-01 (Detailed Commodities)")
    print("=" * 60)

    if not args.skip_download:
        detailed_zip = download_detailed_table()
    else:
        detailed_zip = DETAILED_LOCAL_ZIP
        if not detailed_zip.exists():
            print(f"❌ Detailed ZIP not found: {detailed_zip}")
            sys.exit(1)

    df_detailed_raw = process_detailed_table(detailed_zip)
    df_detailed_annual = aggregate_detailed_annual(df_detailed_raw)
    save_detailed_output(df_detailed_annual)

    print("\n" + "=" * 60)
    ok = verify_detailed_output()

    if ok:
        print("\n🎉 Both pipelines complete! Data ready for dashboard.")
    else:
        print("\n⚠️ Some verification checks failed. Review output above.")


if __name__ == "__main__":
    run()

