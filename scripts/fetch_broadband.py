"""
fetch_broadband.py
==================
Process ISED National Broadband Data to compute per-CSD terrestrial broadband
coverage metrics for Ontario.

Uses the "Golden Pipeline" approach recommended by broadband policy experts:
  1. PHH Speeds CSV   — per-PHH availability flags (Wired/Wireless/Combined)
  2. PHH Demographics  — dwelling counts & dissemination block IDs
  3. DGRF Crosswalk    — dissemination block → CSD mapping

By merging on PHH_ID and DBUID, every pseudo-household is assigned to the
correct Census Subdivision *without* any spatial join or GeoPandas dependency.

Satellite is excluded by using ONLY the Wired and Wireless columns
(ignoring Combined, which includes LEO satellite coverage).  Coverage is
weighted by actual 2021 Census dwelling counts (TDwell2021), so a 50 km
logging road with zero homes no longer inflates the denominator.

Prerequisites (manual downloads):
  - data/raw/NBD_PHH_Speeds.zip          (ISED Open Canada – NBD PHH Speeds)
  - data/raw/PHH_2021_CSV (1).zip        (ISED Open Canada – PHH Demographics)
  - data/raw/2021_98260004.zip           (StatCan – DGRF 2021 Census)

Output:   data/derived/broadband_coverage.csv
Columns:  sgc_code, indicator, value

Indicators produced (5, dwelling-weighted, terrestrial-only):
  broadband_50_10_pct          – % dwellings with terrestrial ≥50/10 Mbps (CRTC USO)
  broadband_25_5_pct           – % dwellings with terrestrial ≥25/5 Mbps
  broadband_underserved_pct    – 100 − broadband_50_10_pct (< 50/10)
  broadband_unserved_pct       – % dwellings with NO terrestrial ≥5/1 Mbps
  broadband_total_dwellings    – total 2021 Census dwellings per CSD
"""

import json
import pathlib
import zipfile
import io

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUT_DIR = BASE_DIR / "data" / "derived"
OUT_FILE = OUT_DIR / "broadband_coverage.csv"
VINTAGE_FILE = OUT_DIR / "broadband_vintage.json"

# Source files
PHH_SPEEDS_ZIP = RAW_DIR / "NBD_PHH_Speeds.zip"
PHH_SPEEDS_ENTRY = "PHH_Speeds_Current-PHH_Vitesses_Actuelles_ON.csv"

PHH_DEMO_ZIP = RAW_DIR / "PHH_2021_CSV (1).zip"
PHH_DEMO_ENTRY = "PHH_2021_CSV/PHH-ON.csv"

DGRF_ZIP = RAW_DIR / "2021_98260004.zip"
DGRF_ENTRY = "2021_98260004.csv"

# ISED CKAN metadata endpoint for data vintage
ISED_CKAN_URL = (
    "https://open.canada.ca/data/api/3/action/package_show"
    "?id=00a331db-121b-445d-b119-35dbbe3eedd9"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_csv_from_zip(zip_path: pathlib.Path, entry_name: str,
                       usecols=None, dtype=None) -> pd.DataFrame:
    """Read a single CSV from within a ZIP file."""
    if not zip_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {zip_path}\n"
            "See docstring for download instructions."
        )
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(entry_name) as f:
            return pd.read_csv(
                io.BytesIO(f.read()),
                usecols=usecols,
                dtype=dtype,
                encoding="utf-8-sig",
            )


def _fetch_vintage() -> str | None:
    """Query the ISED CKAN API for the dataset's metadata_modified date."""
    try:
        import requests
        resp = requests.get(ISED_CKAN_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data["result"].get("metadata_modified", "")[:10]  # YYYY-MM-DD
    except Exception as e:
        print(f"  [WARN] Could not fetch ISED vintage: {e}")
        return None


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------
def _compute_broadband() -> pd.DataFrame:
    """Merge PHH Speeds + Demographics + DGRF crosswalk, compute coverage.

    This is the 'Golden Pipeline' — zero GeoPandas, zero spatial joins.
    """
    # ------------------------------------------------------------------
    # 1. Load PHH Speeds (Ontario only, from ZIP)
    # ------------------------------------------------------------------
    print("  Loading PHH Speeds (Ontario) ...")
    speed_cols = [
        "PHH_ID",
        "Wired_50_10_Filaire", "Wireless_50_10_Sans_fil",
        "Wired_25_5_Filaire", "Wireless_25_5_Sans_fil",
        "Wired_5_1_Filaire", "Wireless_5_1_Sans_fil",
    ]
    speeds = _read_csv_from_zip(PHH_SPEEDS_ZIP, PHH_SPEEDS_ENTRY,
                                usecols=speed_cols)
    print(f"    {len(speeds):,} PHH speed records loaded")

    # ------------------------------------------------------------------
    # 2. Load PHH Demographics (Ontario only, from ZIP)
    # ------------------------------------------------------------------
    print("  Loading PHH Demographics (Ontario) ...")
    demo_cols = ["PHH_ID", "TDwell2021_TLog2021", "DBUID_Ididu"]
    demo = _read_csv_from_zip(PHH_DEMO_ZIP, PHH_DEMO_ENTRY,
                              usecols=demo_cols,
                              dtype={"DBUID_Ididu": str})
    demo.rename(columns={"TDwell2021_TLog2021": "TDwell2021"}, inplace=True)
    print(f"    {len(demo):,} PHH demographic records loaded")

    # ------------------------------------------------------------------
    # 3. Load DGRF crosswalk (DBUID → CSDUID)
    #    The DGRF uses DGUIDs; extract raw IDs from the last characters.
    #    DBDGUID format:  2021S0513XXXXXXXXXXX  → last 11 = DBUID
    #    CSDDGUID format: 2021A0005XXXXXXX      → last 7  = CSDUID
    # ------------------------------------------------------------------
    print("  Loading DGRF crosswalk ...")
    dgrf_cols = ["DBDGUID_IDIDUGD", "CSDDGUID_SDRIDUGD"]
    dgrf = _read_csv_from_zip(DGRF_ZIP, DGRF_ENTRY,
                              usecols=dgrf_cols, dtype=str)
    dgrf["DBUID"] = dgrf["DBDGUID_IDIDUGD"].str[9:]     # last 11 chars
    dgrf["CSDUID"] = dgrf["CSDDGUID_SDRIDUGD"].str[9:]  # last 7 chars

    # Filter to Ontario only (DBUID starts with 35)
    dgrf = dgrf[dgrf["DBUID"].str.startswith("35")].copy()
    dgrf = dgrf[["DBUID", "CSDUID"]].drop_duplicates()
    print(f"    {len(dgrf):,} Ontario DB→CSD mappings")

    # ------------------------------------------------------------------
    # 4. Merge: Speeds ↔ Demographics on PHH_ID
    # ------------------------------------------------------------------
    print("  Merging PHH Speeds ↔ Demographics ...")
    df = pd.merge(speeds, demo, on="PHH_ID", how="inner")
    print(f"    {len(df):,} records after PHH merge")

    # ------------------------------------------------------------------
    # 5. Merge: result ↔ DGRF on DBUID → get CSDUID
    # ------------------------------------------------------------------
    print("  Merging with DGRF crosswalk (DBUID → CSDUID) ...")
    df["DBUID_Ididu"] = df["DBUID_Ididu"].astype(str)
    df = pd.merge(df, dgrf, left_on="DBUID_Ididu", right_on="DBUID",
                  how="inner")
    print(f"    {len(df):,} records after DGRF merge")

    # Sanity: filter Ontario CSDs (should already be, but belt-and-suspenders)
    df = df[df["CSDUID"].str.startswith("35")].copy()

    # ------------------------------------------------------------------
    # 6. Create terrestrial flags (exclude satellite/Combined columns)
    # ------------------------------------------------------------------
    print("  Computing terrestrial availability flags ...")

    # For each speed tier, terrestrial = max(Wired, Wireless)
    # These are boolean (0/1) flags: 1 = at least one provider at this tier
    for col in ["Wired_50_10_Filaire", "Wireless_50_10_Sans_fil",
                "Wired_25_5_Filaire", "Wireless_25_5_Sans_fil",
                "Wired_5_1_Filaire", "Wireless_5_1_Sans_fil"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["terrestrial_50_10"] = df[["Wired_50_10_Filaire",
                                  "Wireless_50_10_Sans_fil"]].max(axis=1)
    df["terrestrial_25_5"] = df[["Wired_25_5_Filaire",
                                 "Wireless_25_5_Sans_fil"]].max(axis=1)
    df["terrestrial_5_1"] = df[["Wired_5_1_Filaire",
                                "Wireless_5_1_Sans_fil"]].max(axis=1)

    # ------------------------------------------------------------------
    # 7. Weight by actual 2021 Census dwellings
    # ------------------------------------------------------------------
    df["TDwell2021"] = pd.to_numeric(df["TDwell2021"], errors="coerce").fillna(0)

    df["dwellings_50_10"] = df["terrestrial_50_10"] * df["TDwell2021"]
    df["dwellings_25_5"] = df["terrestrial_25_5"] * df["TDwell2021"]
    df["dwellings_5_1"] = df["terrestrial_5_1"] * df["TDwell2021"]

    # ------------------------------------------------------------------
    # 8. Aggregate by CSD
    # ------------------------------------------------------------------
    print("  Aggregating by CSD ...")
    csd_stats = df.groupby("CSDUID").agg(
        total_dwellings=("TDwell2021", "sum"),
        dwellings_50_10=("dwellings_50_10", "sum"),
        dwellings_25_5=("dwellings_25_5", "sum"),
        dwellings_5_1=("dwellings_5_1", "sum"),
    ).reset_index()

    print(f"    {len(csd_stats)} CSDs with data")

    # ------------------------------------------------------------------
    # 9. Compute percentages (avoid division by zero)
    # ------------------------------------------------------------------
    mask = csd_stats["total_dwellings"] > 0

    csd_stats["broadband_50_10_pct"] = 0.0
    csd_stats.loc[mask, "broadband_50_10_pct"] = (
        100 * csd_stats["dwellings_50_10"] / csd_stats["total_dwellings"]
    ).round(1)

    csd_stats["broadband_25_5_pct"] = 0.0
    csd_stats.loc[mask, "broadband_25_5_pct"] = (
        100 * csd_stats["dwellings_25_5"] / csd_stats["total_dwellings"]
    ).round(1)

    csd_stats["broadband_unserved_pct"] = 0.0
    csd_stats.loc[mask, "broadband_unserved_pct"] = (
        100 - 100 * csd_stats["dwellings_5_1"] / csd_stats["total_dwellings"]
    ).round(1)

    csd_stats["broadband_underserved_pct"] = (
        100 - csd_stats["broadband_50_10_pct"]
    ).round(1)

    # ------------------------------------------------------------------
    # 10. Summary stats
    # ------------------------------------------------------------------
    print("\n  Per-CSD Summary (terrestrial, dwelling-weighted):")
    pct_50_10 = csd_stats.loc[mask, "broadband_50_10_pct"]
    print(f"    CSDs with data: {len(pct_50_10)}")
    print(f"    Median 50/10 coverage: {pct_50_10.median():.1f}%")
    print(f"    Mean 50/10 coverage: {pct_50_10.mean():.1f}%")
    print(f"    Min: {pct_50_10.min():.1f}%, Max: {pct_50_10.max():.1f}%")
    below_100 = (pct_50_10 < 100).sum()
    print(f"    CSDs below 100%: {below_100}")
    below_90 = (pct_50_10 < 90).sum()
    print(f"    CSDs below 90%:  {below_90}")

    # ------------------------------------------------------------------
    # 11. Build output (long format: sgc_code, indicator, value)
    # ------------------------------------------------------------------
    records = []
    for _, row in csd_stats.iterrows():
        sgc = row["CSDUID"]
        td = round(row["total_dwellings"])  # round away float noise

        records.append((sgc, "broadband_50_10_pct",
                        float(row["broadband_50_10_pct"]) if td > 0 else None))
        records.append((sgc, "broadband_25_5_pct",
                        float(row["broadband_25_5_pct"]) if td > 0 else None))
        records.append((sgc, "broadband_underserved_pct",
                        float(row["broadband_underserved_pct"]) if td > 0 else None))
        records.append((sgc, "broadband_unserved_pct",
                        max(0.0, float(row["broadband_unserved_pct"])) if td > 0 else None))
        records.append((sgc, "broadband_total_dwellings",
                        float(td) if td > 0 else None))

    return pd.DataFrame(records, columns=["sgc_code", "indicator", "value"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    """Process broadband coverage data."""
    print("[fetch_broadband] Processing ISED PHH broadband data (terrestrial-only) ...")
    try:
        indicators = _compute_broadband()
    except FileNotFoundError as e:
        print(f"[fetch_broadband] [WARN] {e}")
        print("[fetch_broadband] Skipping broadband integration.")
        return

    if indicators.empty:
        print("[fetch_broadband] [ERROR] No broadband data extracted")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    indicators.to_csv(OUT_FILE, index=False)
    n_csds = indicators["sgc_code"].nunique()
    n_ind = indicators["indicator"].nunique()
    print(
        f"[fetch_broadband] [OK] Saved {len(indicators)} rows "
        f"({n_csds} CSDs x {n_ind} indicators, dwelling-weighted terrestrial) "
        f"-> {OUT_FILE}"
    )

    # Fetch and save data vintage
    vintage = _fetch_vintage()
    if vintage:
        vintage_data = {
            "source": "ISED National Broadband Data",
            "metadata_modified": vintage,
            "methodology": "Dwelling-weighted terrestrial (Wired + Fixed Wireless)",
        }
        with open(VINTAGE_FILE, "w") as f:
            json.dump(vintage_data, f, indent=2)
        print(f"[fetch_broadband] [OK] Vintage saved -> {VINTAGE_FILE} (as of {vintage})")


if __name__ == "__main__":
    run()
