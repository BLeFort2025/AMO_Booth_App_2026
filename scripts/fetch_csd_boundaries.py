"""
Fetch Ontario CSD Boundary File
================================
Downloads StatCan 2021 Census Subdivision cartographic boundary file,
filters to Ontario, simplifies geometry, and saves as GeoJSON for
the Wellbeing Dashboard map.

Usage:
    python scripts/fetch_csd_boundaries.py
"""

import os
import sys
import zipfile
import tempfile
import geopandas as gpd
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from scripts.http_utils import get_robust_session

# -- Configuration --
# StatCan 2021 Census cartographic boundary file (CSD level)
# Format: lcsd000b21a_e.zip  (cartographic = 'b', digital = 'a')
BOUNDARY_URL = "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lcsd000b21a_e.zip"

# Alternative URL pattern (in case primary is unavailable)
BOUNDARY_URL_ALT = "https://www12.statcan.gc.ca/census-recensement/2011/geo/bound-limit/files-fichiers/2021/lcsd000b21a_e.zip"

OUTPUT_DIR = Path("data/latest/wellbeing")
OUTPUT_FILE = OUTPUT_DIR / "ontario_csd_boundaries.geojson"
RAW_DIR = Path("data/raw")

# Ontario province code in SGC = "35"
ONTARIO_PRUID = "35"

# Simplification tolerance in degrees (~100m at Ontario latitudes)
SIMPLIFY_TOLERANCE = 0.001


def download_boundary_zip(url, dest_path):
    """Download the boundary ZIP file."""
    print(f"Downloading CSD boundary file from StatCan...")
    print(f"  URL: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FarmFinanceDashboard/1.0"
    }

    session = get_robust_session()
    resp = session.get(url, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    # Q8 Fix: Write to temp file, then atomic rename to prevent corrupted ZIPs
    tmp_path = dest_path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    print(f"\r  Downloaded {downloaded / 1_000_000:.1f} MB / {total / 1_000_000:.1f} MB ({pct:.0f}%)", end="")

    tmp_path.rename(dest_path)  # Atomic operation prevents corrupted states
    print(f"\n  Saved to {dest_path} ({os.path.getsize(dest_path) / 1_000_000:.1f} MB)")
    return dest_path


def process_boundaries(zip_path):
    """Extract, filter to Ontario, simplify, and save as GeoJSON."""
    print("\nProcessing boundary file...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract ZIP
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmpdir)
            print(f"  Extracted {len(z.namelist())} files")

        # Find the .shp file
        shp_files = list(Path(tmpdir).rglob("*.shp"))
        if not shp_files:
            raise FileNotFoundError("No .shp file found in ZIP archive")

        print(f"  Reading shapefile: {shp_files[0].name}")
        gdf = gpd.read_file(shp_files[0])
        print(f"  Total CSDs across Canada: {len(gdf):,}")
        print(f"  Columns: {list(gdf.columns)}")

        # Find the province/territory column
        # StatCan uses PRUID or PRENAME
        pruid_col = None
        for candidate in ["PRUID", "PRENAME", "PR_UID"]:
            if candidate in gdf.columns:
                pruid_col = candidate
                break

        if pruid_col is None:
            # Try to extract PRUID from CSDUID (first 2 digits)
            csduid_col = None
            for c in ["CSDUID", "DGUID"]:
                if c in gdf.columns:
                    csduid_col = c
                    break
            if csduid_col:
                gdf["_pruid"] = gdf[csduid_col].astype(str).str[:2]
                pruid_col = "_pruid"
            else:
                raise KeyError(f"Cannot identify province column. Available: {list(gdf.columns)}")

        # Filter to Ontario
        if pruid_col == "PRENAME":
            ontario = gdf[gdf[pruid_col] == "Ontario"].copy()
        else:
            ontario = gdf[gdf[pruid_col].astype(str) == ONTARIO_PRUID].copy()

        print(f"  Ontario CSDs: {len(ontario):,}")

        # Q2 Fix: Fallback CRS if missing from shapefile
        if ontario.crs is None:
            print("  WARNING: No CRS found in shapefile. Assuming EPSG:3347 (StatCan Lambert).")
            ontario.set_crs(epsg=3347, allow_override=True, inplace=True)

        # Q2 Fix: Simplify in metric CRS (EPSG:3347, StatCan Lambert Conformal Conic)
        # to ensure uniform simplification in meters, not degrees.
        # Simplifying in WGS84 (degrees) causes anisotropic distortion at high latitudes.
        if ontario.crs.to_epsg() != 3347:
            print(f"  Reprojecting from {ontario.crs} to EPSG:3347 for uniform simplification...")
            ontario = ontario.to_crs(epsg=3347)

        # Simplify using 100 meters uniformly
        print(f"  Simplifying geometry (tolerance=100m in metric CRS)...")
        ontario["geometry"] = ontario["geometry"].simplify(
            100, preserve_topology=True
        )

        # Finally, project to WGS84 for pydeck web mapping
        print(f"  Reprojecting to EPSG:4326 (WGS84) for web mapping...")
        ontario = ontario.to_crs(epsg=4326)

        # Keep only essential columns for the dashboard
        # Rename to match our data schema
        col_map = {}
        for src, dst in [
            ("CSDUID", "sgc_code"),
            ("CSDNAME", "geo_name"),
            ("CSDTYPE", "csd_type"),
            ("CDNAME", "county"),
        ]:
            if src in ontario.columns:
                col_map[src] = dst

        ontario = ontario.rename(columns=col_map)

        # Keep only mapped columns + geometry
        keep_cols = [v for v in col_map.values() if v in ontario.columns] + ["geometry"]
        ontario = ontario[keep_cols]

        # Save as GeoJSON
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ontario.to_file(OUTPUT_FILE, driver="GeoJSON")

        file_size = os.path.getsize(OUTPUT_FILE) / 1_000_000
        print(f"\n  Saved {len(ontario):,} Ontario CSDs to {OUTPUT_FILE}")
        print(f"  File size: {file_size:.1f} MB")

        return len(ontario), file_size


def run():
    """Main entry point."""
    print("=" * 60)
    print("CSD Boundary File Processor")
    print("=" * 60)

    # Check if output already exists
    if OUTPUT_FILE.exists():
        size_mb = os.path.getsize(OUTPUT_FILE) / 1_000_000
        print(f"\nBoundary file already exists: {OUTPUT_FILE} ({size_mb:.1f} MB)")
        print("Delete it to re-download and re-process.")
        return

    # Check for pre-downloaded ZIP in data/raw/
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "lcsd000b21a_e.zip"

    if not zip_path.exists():
        # Try to download
        try:
            download_boundary_zip(BOUNDARY_URL, zip_path)
        except Exception as e:
            print(f"\n[WARNING] Download failed: {e}")
            print(f"\nPlease manually download the CSD boundary file:")
            print(f"  1. Go to: https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21")
            print(f"  2. Select: Census subdivision, Cartographic Boundary File, Shapefile (.shp)")
            print(f"  3. Save the ZIP to: {zip_path.resolve()}")
            return
    else:
        print(f"\nUsing existing ZIP: {zip_path}")

    # Process
    n_csds, file_mb = process_boundaries(zip_path)
    print(f"\nDone! {n_csds} Ontario CSD boundaries ready for the map ({file_mb:.1f} MB)")


if __name__ == "__main__":
    run()
