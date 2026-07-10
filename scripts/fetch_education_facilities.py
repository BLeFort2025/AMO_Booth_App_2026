"""
fetch_education_facilities.py
=============================
Process the StatCan Open Database of Educational Facilities (ODEF)
and count educational facilities per Ontario CSD.

Expects:  data/raw/ODEF*.zip  (download from StatCan LODE page)
          https://www.statcan.gc.ca/en/lode/databases/odef

Outputs:
  WIDE  → data/latest/wellbeing/education_facility_counts.csv
          Pivot by facility type with totals and per-capita rates
  LONG  → data/derived/education_facilities.csv
          Columns: sgc_code, indicator="education_facilities", value

Created Feb 2026 (Rec 9 — expand LODE suite)
"""

import io
import glob
import zipfile
from pathlib import Path

import pandas as pd

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
WELLBEING_DIR = BASE_DIR / "data" / "latest" / "wellbeing"
DERIVED_DIR = BASE_DIR / "data" / "derived"

WIDE_FILE = WELLBEING_DIR / "education_facility_counts.csv"
LONG_FILE = DERIVED_DIR / "education_facilities.csv"

# Hardcoded column names — update if ODEF schema changes
# These are the expected ODEF column names (similar to ODHF/ODCAF pattern)
ODEF_CSD_COL = "CSDUID"           # May also be "CSDuid"
ODEF_PROV_COL = "Prov_Terr"       # May also be "province"
ODEF_TYPE_COL = "ODEF_Facility_Type"  # May also be "ISCED_Level"

# Fallback column name candidates (checked if primary not found)
CSD_CANDIDATES = ["CSDUID", "CSDuid", "csduid", "csd_uid", "CSD"]
PROV_CANDIDATES = ["Prov_Terr", "province", "Province", "Province / Territory"]
TYPE_CANDIDATES = ["ODEF_Facility_Type", "ISCED_Level", "Facility_Type",
                    "Source_Facility_Type"]


def _find_column(df: pd.DataFrame, candidates: list, desc: str) -> str:
    """Find the first matching column from a list of candidates."""
    for c in candidates:
        if c in df.columns:
            return c
    # Try case-insensitive match
    cols_lower = {col.lower().strip(): col for col in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    raise RuntimeError(
        f"Cannot find {desc} column. Tried: {candidates}. "
        f"Available: {list(df.columns)}"
    )


def run():
    """Process ODEF data into per-CSD education facility counts — dual output."""
    # Find ODEF ZIP
    pattern = str(RAW_DIR / "ODEF*.zip")
    zips = glob.glob(pattern)
    if not zips:
        pattern2 = str(RAW_DIR / "odef*.zip")
        zips = glob.glob(pattern2)
    if not zips:
        print("[fetch_education] ⚠ No ODEF ZIP found. Skipping education facilities.")
        print("  Download from: https://www.statcan.gc.ca/en/lode/databases/odef")
        return

    zip_path = zips[0]
    print(f"[fetch_education] Processing from: {zip_path}")

    # Read CSV from ZIP
    with zipfile.ZipFile(zip_path) as z:
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            print("[fetch_education] ERROR: No CSV files found inside ZIP.")
            return
        data_csvs = [n for n in csv_names
                     if "data_source" not in n.lower()
                     and "meta" not in n.lower()]
        csv_name = max(data_csvs or csv_names,
                       key=lambda n: z.getinfo(n).file_size)
        print(f"  Using CSV: {csv_name}")
        df = pd.read_csv(io.BytesIO(z.read(csv_name)), encoding="latin-1",
                         low_memory=False)

    print(f"  Total facility records: {len(df):,}")
    print(f"  Columns: {list(df.columns)}")

    # Find required columns
    csd_col = _find_column(df, CSD_CANDIDATES, "CSD UID")
    prov_col = _find_column(df, PROV_CANDIDATES, "Province")

    # Filter to Ontario
    on = df[df[prov_col].astype(str).str.lower().str.strip().isin(
        ["on", "ontario", "35"]
    )].copy()
    print(f"  Ontario facilities: {len(on):,}")

    if on.empty:
        print("[fetch_education] ⚠ No Ontario facilities found.")
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
    print(f"  Valid Ontario CSD records: {len(on):,}")

    # Build pivot by type (if type column exists)
    type_col = None
    for c in TYPE_CANDIDATES:
        if c in on.columns:
            type_col = c
            break

    if type_col:
        counts = (
            on.groupby(["sgc_code", type_col])
            .size()
            .reset_index(name="count")
            .rename(columns={type_col: "facility_type"})
        )
        counts["facility_type"] = (
            counts["facility_type"].str.strip().str.lower().str.replace(" ", "_")
        )
        pivot = counts.pivot_table(
            index="sgc_code", columns="facility_type", values="count",
            aggfunc="sum", fill_value=0,
        ).reset_index()
        pivot.columns.name = None
        type_cols = [c for c in pivot.columns if c != "sgc_code"]
        pivot["total_facilities"] = pivot[type_cols].sum(axis=1)
    else:
        pivot = on.groupby("sgc_code").size().reset_index(name="total_facilities")

    # Enrich with geo names
    geo_file = WELLBEING_DIR / "dim_geography.csv"
    if geo_file.exists():
        geo = pd.read_csv(geo_file)
        geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)
        pivot = pivot.merge(
            geo[["sgc_code", "geo_name", "county"]], on="sgc_code", how="left"
        )
        if "geo_name" in pivot.columns:
            pivot["community"] = pivot.apply(
                lambda r: f"{r['geo_name']} ({r['county']})"
                if pd.notna(r.get("county")) and r["county"]
                else str(r.get("geo_name", r["sgc_code"])),
                axis=1,
            )

    # Per-capita rate
    ind_file = WELLBEING_DIR / "census_indicators.csv"
    if ind_file.exists():
        inds = pd.read_csv(ind_file)
        inds["sgc_code"] = inds["sgc_code"].astype(str).str.zfill(7)
        pop = inds[
            (inds["indicator"] == "population")
            & (inds["census_year"] == inds["census_year"].max())
        ][["sgc_code", "value"]].rename(columns={"value": "population"})
        pivot = pivot.merge(pop, on="sgc_code", how="left")
        pivot["facilities_per_10k"] = (
            pivot["total_facilities"] / pivot["population"] * 10_000
        ).round(1)
        pivot["facilities_per_10k"] = pivot["facilities_per_10k"].replace(
            [float("inf"), float("-inf")], None
        )

    # Save WIDE
    WELLBEING_DIR.mkdir(parents=True, exist_ok=True)
    pivot.to_csv(WIDE_FILE, index=False)
    print(f"[fetch_education] ✓ WIDE: {len(pivot)} CSDs → {WIDE_FILE}")

    # Save LONG
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    long_df = pd.DataFrame({
        "sgc_code": pivot["sgc_code"],
        "indicator": "education_facilities",
        "value": pivot["total_facilities"].astype(int),
    })
    long_df.to_csv(LONG_FILE, index=False)
    print(f"[fetch_education] ✓ LONG: {len(long_df)} rows → {LONG_FILE}")

    return pivot


if __name__ == "__main__":
    run()
