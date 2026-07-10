"""
Arts & Culture Facility Processor
==================================
Reads the StatCan Open Database of Cultural and Art Facilities (ODCAF)
and produces per-CSD facility counts for Ontario communities.

User must download the ODCAF ZIP from Statistics Canada:
  https://www.statcan.gc.ca/en/lode/databases/odcaf

Place the downloaded ZIP in:  data/raw/ODCAF*.zip

Outputs:
  WIDE  → data/latest/wellbeing/arts_facility_counts.csv
          Pivot by facility type with totals and per-capita rates
  LONG  → data/derived/arts_culture.csv
          Columns: sgc_code, indicator="arts_culture_facilities", value
  META  → data/latest/wellbeing/amenities_vintage.json  (updated)

Updated Feb 2026 — expert review recommendations:
  - Rec 4: Consolidated from two scripts into one (replaces fetch_arts_culture.py)
  - Rec 5: Alias-based column resolution (lowercase-normalized, fail-fast)
  - Rec 2: Generate amenities_vintage.json for dynamic UI disclaimers
"""

import io
import glob
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
WELLBEING_DIR = BASE_DIR / "data" / "latest" / "wellbeing"
DERIVED_DIR = BASE_DIR / "data" / "derived"

WIDE_FILE = WELLBEING_DIR / "arts_facility_counts.csv"
LONG_FILE = DERIVED_DIR / "arts_culture.csv"
VINTAGE_FILE = WELLBEING_DIR / "amenities_vintage.json"

# Accepted column-name aliases (lowercase-normalized).  Rec 5 audit fix:
CSD_ALIASES = ["csduid", "csd_uid", "csd"]
PROV_ALIASES = ["prov_terr", "province", "province / territory"]
TYPE_ALIASES = ["odcaf_facility_type", "facility_type", "source_facility_type"]


# ---------------------------------------------------------------------------
# Column resolution
# ---------------------------------------------------------------------------
def _find_column(df: pd.DataFrame, aliases: list, desc: str) -> str:
    """Resolve a column name using lowercase-normalized alias matching."""
    cols_lower = {col.lower().strip(): col for col in df.columns}
    for alias in aliases:
        if alias in cols_lower:
            return cols_lower[alias]
    raise RuntimeError(
        f"Cannot find {desc} column.  "
        f"Tried aliases: {aliases}.  "
        f"Available (lowercase): {sorted(cols_lower.keys())}"
    )


def run():
    """Process ODCAF data into per-CSD arts facility counts — dual output."""
    # Find ODCAF ZIP
    pattern = str(RAW_DIR / "ODCAF*.zip")
    zips = glob.glob(pattern)
    if not zips:
        # Try alternate case
        pattern2 = str(RAW_DIR / "odcaf*.zip")
        zips = glob.glob(pattern2)
    if not zips:
        print("[WARN] No ODCAF ZIP found. Skipping arts facilities.")
        print("       Download from https://www.statcan.gc.ca/en/lode/databases/odcaf")
        return

    zip_path = zips[0]
    print(f"Processing arts facilities from: {zip_path}")

    # Read CSV from ZIP — prefer the main data CSV (largest, excluding metadata)
    with zipfile.ZipFile(zip_path) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            print("[ERROR] No CSV files found inside ZIP.")
            return
        data_csvs = [n for n in csv_names
                     if "data_source" not in n.lower()
                     and "meta" not in n.lower()]
        if data_csvs:
            csv_name = max(data_csvs, key=lambda n: z.getinfo(n).file_size)
        else:
            csv_name = max(csv_names, key=lambda n: z.getinfo(n).file_size)
        print(f"  Using CSV: {csv_name}")
        _csv_bytes = z.read(csv_name)
        try:
            df = pd.read_csv(io.BytesIO(_csv_bytes), encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(_csv_bytes), encoding="latin-1")
            print("  ⚠ Fell back to latin-1 encoding")

    print(f"  Total facilities: {len(df):,}")

    # Resolve columns via aliases (Rec 5 audit fix)
    csd_col = _find_column(df, CSD_ALIASES, "CSD UID")
    prov_col = _find_column(df, PROV_ALIASES, "Province/Territory")

    # Filter to Ontario
    on = df[df[prov_col].str.lower().str.strip().isin(["on", "ontario"])].copy()
    print(f"  Ontario facilities: {len(on):,}")

    if on.empty:
        print("[WARN] No Ontario facilities found.")
        return

    # Normalize CSD codes
    on = on.dropna(subset=[csd_col])

    def _safe_csd(x):
        try:
            return str(int(float(x))).zfill(7)
        except (ValueError, TypeError):
            return None

    on["sgc_code"] = on[csd_col].apply(_safe_csd)
    on = on.dropna(subset=["sgc_code"])
    on = on[on["sgc_code"].str.match(r"^35\d{5}$")].copy()
    print(f"  Facilities with valid Ontario CSD: {len(on):,}")

    # --- Build WIDE format ---
    # Try to find type column via aliases
    type_col = None
    try:
        type_col = _find_column(on, TYPE_ALIASES, "Facility type")
    except RuntimeError:
        print("  ⚠ No facility type column found — falling back to simple count")

    if type_col:
        # Count by CSD × type
        counts = (
            on.groupby(["sgc_code", type_col])
            .size()
            .reset_index(name="count")
            .rename(columns={type_col: "facility_type"})
        )

        # Normalize type names for column headers
        counts["facility_type"] = (
            counts["facility_type"]
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        # Pivot to wide format
        pivot = counts.pivot_table(
            index="sgc_code", columns="facility_type", values="count",
            aggfunc="sum", fill_value=0,
        ).reset_index()
        pivot.columns.name = None

        # Add total
        type_cols = [c for c in pivot.columns if c != "sgc_code"]
        pivot["total_facilities"] = pivot[type_cols].sum(axis=1)
    else:
        # No type column — simple count
        pivot = on.groupby("sgc_code").size().reset_index(name="total_facilities")

    # Add CSD name from geo dimension
    geo_file = WELLBEING_DIR / "dim_geography.csv"
    if geo_file.exists():
        geo = pd.read_csv(geo_file)
        geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)
        pivot = pivot.merge(
            geo[["sgc_code", "geo_name", "county"]],
            on="sgc_code", how="left",
        )
        if "geo_name" in pivot.columns:
            pivot["community"] = pivot.apply(
                lambda r: f"{r['geo_name']} ({r['county']})"
                if pd.notna(r.get("county")) and r["county"]
                else str(r.get("geo_name", r["sgc_code"])),
                axis=1,
            )

    # Per-capita rate (per 10,000 pop)
    ind_file = WELLBEING_DIR / "census_indicators.csv"
    if ind_file.exists():
        inds = pd.read_csv(ind_file)
        inds["sgc_code"] = inds["sgc_code"].astype(str).str.zfill(7)
        pop = inds[
            (inds["indicator"] == "population") &
            (inds["census_year"] == inds["census_year"].max())
        ][["sgc_code", "value"]].rename(columns={"value": "population"})
        # FIX A1: RIGHT JOIN keeps ALL Ontario CSDs (even with 0 facilities)
        # so benchmark denominators include zero-facility communities.
        pivot = pivot.merge(pop, on="sgc_code", how="right")
        # Fill NaN facility counts for CSDs with no ODCAF entries
        fill_cols = [c for c in pivot.columns if c not in ["sgc_code", "population"]]
        pivot[fill_cols] = pivot[fill_cols].fillna(0)
        pivot["total_facilities"] = pivot["total_facilities"].fillna(0)
        pivot["facilities_per_10k"] = (
            pivot["total_facilities"] / pivot["population"] * 10_000
        ).round(1)
        pivot["facilities_per_10k"] = pivot["facilities_per_10k"].replace(
            [float("inf"), float("-inf")], None
        )

    # Save WIDE format (for standalone §8c Arts & Culture section)
    WELLBEING_DIR.mkdir(parents=True, exist_ok=True)
    pivot.to_csv(WIDE_FILE, index=False)
    total = pivot["total_facilities"].sum()
    print(f"  ✓ WIDE: {len(pivot)} CSDs ({total:,} total facilities) → {WIDE_FILE}")

    # --- Build LONG format (Rec 4 — single script for both outputs) ---
    long_records = []
    for _, row in pivot.iterrows():
        long_records.append((
            row["sgc_code"],
            "arts_culture_facilities",
            int(row["total_facilities"]),
        ))
    long_df = pd.DataFrame(long_records, columns=["sgc_code", "indicator", "value"])

    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    long_df.to_csv(LONG_FILE, index=False)
    print(f"  ✓ LONG: {len(long_df)} rows → {LONG_FILE}")

    # --- Write vintage metadata (Rec 2 audit fix) ---
    _write_vintage(zip_path)

    return pivot


def _write_vintage(zip_path: str):
    """Write/update amenities_vintage.json with ODCAF metadata."""
    vintage = {}
    if VINTAGE_FILE.exists():
        with open(VINTAGE_FILE, "r") as f:
            vintage = json.load(f)

    vintage["arts"] = {
        "source": "Open Database of Cultural and Art Facilities (ODCAF)",
        "version": "v1.0",
        "source_release_year": 2019,
        "pipeline_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "zip_file": Path(zip_path).name,
    }

    with open(VINTAGE_FILE, "w") as f:
        json.dump(vintage, f, indent=2)
    print(f"  ✓ Vintage metadata → {VINTAGE_FILE}")


if __name__ == "__main__":
    run()
