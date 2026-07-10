"""
fetch_health_facilities.py
==========================
Process the StatCan Open Database of Healthcare Facilities (ODHF)
and produce per-CSD facility counts for Ontario communities.

Expects:  data/raw/ODHF_v1.1.zip  (download from StatCan LODE page)

Outputs:
  WIDE  → data/latest/wellbeing/health_facility_counts.csv
          Columns: sgc_code, ambulatory, hospitals, nursing_residential,
                   other, total_facilities, community, county, population,
                   facilities_per_10k
  LONG  → data/derived/health_facilities.csv
          Columns: sgc_code, indicator, value
  META  → data/latest/wellbeing/amenities_vintage.json
          Dynamic vintage metadata read by Streamlit at runtime

Indicators produced:
  health_facilities  – Count of health facilities (hospitals, clinics, etc.)

Updated Feb 2026 — expert review recommendations:
  - Rec 3: Produce wide-format with facility type breakdowns + "other" bin
  - Rec 5: Alias-based column resolution (lowercase-normalized, fail-fast)
  - Rec 2: Generate amenities_vintage.json for dynamic UI disclaimers
"""

import json
import pathlib
import zipfile
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
WELLBEING_DIR = BASE_DIR / "data" / "latest" / "wellbeing"
DERIVED_DIR = BASE_DIR / "data" / "derived"

WIDE_FILE = WELLBEING_DIR / "health_facility_counts.csv"
LONG_FILE = DERIVED_DIR / "health_facilities.csv"
VINTAGE_FILE = WELLBEING_DIR / "amenities_vintage.json"

ODHF_ZIP = RAW_DIR / "ODHF_v1.1.zip"

# Accepted column-name aliases (lowercase-normalized).  Rec 5 audit fix:
# StatCan changes header casing between releases (CSDuid → CSDUID → csd_uid).
# We normalize to lowercase and check against explicit aliases.
CSD_ALIASES = ["csduid", "csd_uid", "csd"]
PROV_ALIASES = ["province", "prov_terr", "province / territory"]
TYPE_ALIASES = ["odhf_facility_type", "facility_type", "source_facility_type"]

# Map ODHF facility types → our internal column names (case-insensitive)
FACILITY_TYPE_MAP = {
    "hospitals":                               "hospitals",
    "ambulatory health care services":         "ambulatory",
    "nursing and residential care facilities": "nursing_residential",
}


# ---------------------------------------------------------------------------
# Column resolution
# ---------------------------------------------------------------------------
def _find_column(df: pd.DataFrame, aliases: list[str], desc: str) -> str:
    """Resolve a column name using lowercase-normalized alias matching.

    Normalizes all DataFrame columns to lowercase and checks against
    a predefined list of accepted aliases.  If no match is found,
    raises a fail-fast RuntimeError.
    """
    cols_lower = {col.lower().strip(): col for col in df.columns}
    for alias in aliases:
        if alias in cols_lower:
            return cols_lower[alias]
    raise RuntimeError(
        f"Cannot find {desc} column.  "
        f"Tried aliases: {aliases}.  "
        f"Available (lowercase): {sorted(cols_lower.keys())}"
    )


# ---------------------------------------------------------------------------
# Load & Process
# ---------------------------------------------------------------------------
def _process_odhf() -> pd.DataFrame:
    """Load ODHF, filter Ontario, pivot by facility type per CSD."""
    if not ODHF_ZIP.exists():
        raise FileNotFoundError(
            f"ODHF ZIP not found at {ODHF_ZIP}.\n"
            "Download from: https://www.statcan.gc.ca/en/lode/databases/odhf"
        )

    zf = zipfile.ZipFile(ODHF_ZIP)
    csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
    main_csv = max(csv_names, key=lambda n: zf.getinfo(n).file_size)
    print(f"  Reading {main_csv} from ZIP ...")
    with zf.open(main_csv) as f:
        df = pd.read_csv(f, encoding='latin-1', low_memory=False)
    print(f"  Loaded {len(df):,} facility records")

    # Resolve columns via aliases (Rec 5 audit fix)
    csd_col = _find_column(df, CSD_ALIASES, "CSD UID")
    prov_col = _find_column(df, PROV_ALIASES, "Province")
    type_col = _find_column(df, TYPE_ALIASES, "Facility type")

    # Filter to Ontario
    ontario = df[
        df[prov_col].astype(str).str.strip().str.lower().isin(
            ['on', 'ontario', '35']
        )
    ].copy()

    if ontario.empty:
        raise RuntimeError("No Ontario facilities found in ODHF")
    print(f"  Ontario facilities: {len(ontario):,}")

    # Normalize CSD codes (handle float-encoded UIDs like 3523043.0)
    ontario["sgc_code"] = pd.to_numeric(ontario[csd_col], errors="coerce")
    ontario = ontario.dropna(subset=["sgc_code"])
    ontario["sgc_code"] = ontario["sgc_code"].astype(int).astype(str).str.zfill(7)
    ontario = ontario[ontario["sgc_code"].str.match(r"^35\d{5}$")].copy()

    # Map facility types (case-insensitive) with "other" fallback (Rec 3 audit fix)
    ontario["facility_cat"] = (
        ontario[type_col]
        .str.strip()
        .str.lower()
        .map(FACILITY_TYPE_MAP)
        .fillna("other")
    )
    n_other = (ontario["facility_cat"] == "other").sum()
    if n_other > 0:
        unmapped_types = ontario.loc[
            ontario["facility_cat"] == "other", type_col
        ].value_counts().to_dict()
        print(f"  [WARN] {n_other} facilities mapped to 'other': {unmapped_types}")

    # Count by CSD × category
    pivot = (
        ontario
        .groupby(["sgc_code", "facility_cat"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    # Ensure all expected columns exist
    for cat in list(FACILITY_TYPE_MAP.values()) + ["other"]:
        if cat not in pivot.columns:
            pivot[cat] = 0

    # Total across all categories
    cat_cols = list(FACILITY_TYPE_MAP.values()) + ["other"]
    pivot["total_facilities"] = pivot[cat_cols].sum(axis=1)

    # Convert counts to int
    for col in cat_cols + ["total_facilities"]:
        pivot[col] = pivot[col].astype(int)

    print(f"  {len(pivot)} CSDs with health facilities")
    return pivot


def _enrich(counts: pd.DataFrame) -> pd.DataFrame:
    """Add community names, zero-facility CSDs, and per-capita rates.

    P0/P1 audit fix: Uses OUTER join with dim_geography to include ALL
    Ontario CSDs (even those with zero facilities), fixing survivorship
    bias in rural averages and ensuring zero-facility communities are
    visible in the UI.
    """
    import numpy as np

    # Merge geography names — OUTER join to include 0-facility CSDs
    geo_file = WELLBEING_DIR / "dim_geography.csv"
    if geo_file.exists():
        geo = pd.read_csv(geo_file)
        geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)
        geo_on = geo[geo["sgc_code"].str.match(r"^35\d{5}$")].copy()
        counts = counts.merge(
            geo_on[["sgc_code", "geo_name", "county"]],
            on="sgc_code", how="outer",
        )
        # Backfill NaN facility counts with 0 for newly-joined CSDs
        cat_cols = list(FACILITY_TYPE_MAP.values()) + ["other", "total_facilities"]
        for col in cat_cols:
            if col in counts.columns:
                counts[col] = counts[col].fillna(0).astype(int)

        if "geo_name" in counts.columns:
            counts["community"] = counts.apply(
                lambda r: f"{r['geo_name']} ({r['county']})"
                if pd.notna(r.get("geo_name")) and pd.notna(r.get("county")) and r["county"]
                # Issue 14 fix: avoid literal "nan" strings
                else (r["geo_name"] if pd.notna(r.get("geo_name")) else str(r["sgc_code"])),
                axis=1,
            )
    else:
        print("  [WARN] dim_geography.csv not found - skipping community names")

    # Per-capita rate (per 10,000 pop) from latest Census
    ind_file = WELLBEING_DIR / "census_indicators.csv"
    if ind_file.exists():
        inds = pd.read_csv(ind_file)
        inds["sgc_code"] = inds["sgc_code"].astype(str).str.zfill(7)
        pop = inds[
            (inds["indicator"] == "population") &
            (inds["census_year"] == inds["census_year"].max())
        ][["sgc_code", "value"]].rename(columns={"value": "population"})
        counts = counts.merge(pop, on="sgc_code", how="left")
        counts["facilities_per_10k"] = (
            counts["total_facilities"] / counts["population"] * 10_000
        ).round(1)
        # Issue 15 fix: handle inf, -inf, and NaN explicitly
        counts["facilities_per_10k"] = counts["facilities_per_10k"].replace(
            [float("inf"), float("-inf"), np.nan], None
        )
    else:
        print("  [WARN] census_indicators.csv not found - skipping per-capita rates")

    return counts


def _to_long(counts: pd.DataFrame) -> pd.DataFrame:
    """Melt wide format into long format (sgc_code, indicator, value)."""
    records = []
    for _, row in counts.iterrows():
        records.append((
            row["sgc_code"],
            "health_facilities",
            int(row["total_facilities"]),
        ))
    return pd.DataFrame(records, columns=["sgc_code", "indicator", "value"])


def _write_vintage(zip_name: str):
    """Write/update amenities_vintage.json with ODHF metadata (Rec 2 audit fix)."""
    vintage = {}
    if VINTAGE_FILE.exists():
        with open(VINTAGE_FILE, "r") as f:
            vintage = json.load(f)

    vintage["health"] = {
        "source": "Open Database of Healthcare Facilities (ODHF)",
        "version": "v1.1",
        "source_release_year": 2021,
        "pipeline_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "zip_file": zip_name,
    }

    with open(VINTAGE_FILE, "w") as f:
        json.dump(vintage, f, indent=2)
    print(f"[fetch_health_facilities] [OK] Vintage metadata -> {VINTAGE_FILE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    """Process ODHF health facilities data — dual-output."""
    print("[fetch_health_facilities] Loading ODHF from ZIP ...")
    try:
        counts = _process_odhf()
    except FileNotFoundError as e:
        print(f"[fetch_health_facilities] [WARN] {e}")
        print("[fetch_health_facilities] Skipping health facilities.")
        return

    if counts.empty:
        print("[fetch_health_facilities] [ERROR] No data extracted")
        return

    # Enrich with names and per-capita rates
    counts = _enrich(counts)

    # Save WIDE format (for standalone §9 Health Access section)
    WELLBEING_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(WIDE_FILE, index=False)
    print(f"[fetch_health_facilities] [OK] WIDE: {len(counts)} CSDs -> {WIDE_FILE}")

    # Save LONG format (for generic indicator views)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    long_df = _to_long(counts)
    long_df.to_csv(LONG_FILE, index=False)
    print(f"[fetch_health_facilities] [OK] LONG: {len(long_df)} rows -> {LONG_FILE}")

    # Write vintage metadata
    _write_vintage(ODHF_ZIP.name)


if __name__ == "__main__":
    run()
