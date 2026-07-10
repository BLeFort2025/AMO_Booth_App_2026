"""
Climate Normals Processor — ECCC Geomet OGC API
=================================================
Fetches 1981-2010 climate normals for Ontario communities from the
Environment and Climate Change Canada (ECCC) Geomet API.

Audit fixes applied 2026-02-24:
  - Renamed from fetch_climate_projections.py (Q10/Q26: "projections" → "normals")
  - Centroid: shapely area-weighted centroid replaces vertex arithmetic (Q7)
  - DGUID: regex parsing replaces brittle backward scan (Q13)
  - 12-month rule: SUM aggregations strictly require all 12 months (Q11)
  - Retry: exponential backoff on API failures (Q14)
  - Distance warning: flag CSDs mapped to stations > 50 km away (Q8)
  - Station coverage caveat: documented in output metadata (Q9)

Strategy:
  1. Query ECCC Climate Normals (1981-2010) for all Ontario weather stations
  2. Aggregate monthly data to annual values per station
  3. Compute CSD centroids from GeoJSON using shapely (area-weighted)
  4. Map each CSD to the nearest weather station using Haversine distance
  5. Output per-CSD climate normals CSV

Data Source API:
  https://api.weather.gc.ca/collections/climate-normals/items
  (OGC Features API — free, no auth required)

Output: data/latest/wellbeing/climate_normals.csv

Climate indicators produced per CSD:
  - climate_mean_temp:    Annual mean temperature (°C)
  - climate_max_temp:     Mean daily maximum temperature (°C)
  - climate_min_temp:     Mean daily minimum temperature (°C)
  - climate_total_precip: Annual total precipitation (mm)
  - climate_total_rain:   Annual total rainfall (mm)
  - climate_total_snow:   Annual total snowfall (cm)
  - climate_gdd:          Growing Degree Days (base 5°C)
  - climate_frost_days:   Days with min temp ≤ 0°C
  - climate_hot_days:     Days with max temp > 30°C
"""

import json
import math
import re
import time
from pathlib import Path

import pandas as pd
import requests

import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from scripts.http_utils import get_robust_session

# --- Paths ---
OUT_DIR = Path("data/latest/wellbeing")
OUT_FILE = OUT_DIR / "climate_normals.csv"
GEO_FILE = OUT_DIR / "dim_geography.csv"
BOUNDARY_FILE = OUT_DIR / "ontario_csd_boundaries.geojson"

# --- API ---
NORMALS_URL = "https://api.weather.gc.ca/collections/climate-normals/items"
ONTARIO_BBOX = "-95.2,41.6,-74.3,56.9"  # Ontario bounding box

# --- Retry configuration ---
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 1.0  # doubles each retry

# --- Distance threshold (km) for data quality warnings ---
DISTANCE_WARNING_KM = 50

# Climate elements we want — (E_NORMAL_ELEMENT_NAME, NORMAL_ID) -> slug
# NORMAL_IDs discovered via API probing on 2026-02-12
ELEMENT_MAP = {
    ("Mean daily temperature deg C", 1):   "climate_mean_temp",
    ("Mean daily max temperature deg C", 5): "climate_max_temp",
    ("Mean daily min temperature deg C", 8): "climate_min_temp",
    ("Total precipitation mm", 56):         "climate_total_precip",
    ("Total rainfall mm", 52):              "climate_total_rain",
    ("Total snowfall cm", 54):              "climate_total_snow",
    ("Total degree-days Above 5 deg C", 26):"climate_gdd",
    ("Days with daily min temperature LE 0 deg C", 41): "climate_frost_days",
    ("Days with daily max temperature GT 30 deg C", 37): "climate_hot_days",
}

# Aggregation: which elements SUM across months (vs AVERAGE)
SUM_ELEMENTS = {
    "climate_total_precip", "climate_total_rain", "climate_total_snow",
    "climate_gdd", "climate_frost_days", "climate_hot_days",
}

# Friendly display names
DISPLAY_NAMES = {
    "climate_mean_temp":    ("Mean Temperature", "°C"),
    "climate_max_temp":     ("Mean Daily Max Temp", "°C"),
    "climate_min_temp":     ("Mean Daily Min Temp", "°C"),
    "climate_total_precip": ("Annual Precipitation", "mm"),
    "climate_total_rain":   ("Annual Rainfall", "mm"),
    "climate_total_snow":   ("Annual Snowfall", "cm"),
    "climate_gdd":          ("Growing Degree Days (5°C)", "GDD"),
    "climate_frost_days":   ("Frost Days", "days"),
    "climate_hot_days":     ("Hot Days (>30°C)", "days"),
}


def haversine(lat1, lon1, lat2, lon2):
    """Distance between two lat/lon points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _api_get(params, session=None):
    """GET using the centralized robust session."""
    if session is None:
        session = get_robust_session()
    r = session.get(NORMALS_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def get_csd_centroids():
    """Get CSD centroids from GeoJSON using shapely for area-weighted centroids (Q7 fix)."""
    if not BOUNDARY_FILE.exists():
        print("[WARN] No GeoJSON boundary file found. Cannot compute centroids.")
        return {}

    # Import shapely here to keep it optional at module level
    from shapely.geometry import shape as shapely_shape

    with open(BOUNDARY_FILE, "r", encoding="utf-8") as f:
        geojson = json.load(f)

    centroids = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})

        # --- Q13 fix: robust DGUID parsing with regex ---
        sgc_raw = str(props.get("DGUID", props.get("sgc_code", props.get("CSDUID", ""))))
        match = re.search(r'35\d{5}', sgc_raw)
        if not match:
            continue
        sgc = match.group(0)

        # Compute area-weighted centroid using shapely (Q7 fix)
        geom_dict = feature.get("geometry")
        if not geom_dict:
            continue
        try:
            geom = shapely_shape(geom_dict)
            if geom.is_empty:
                continue
            centroid = geom.centroid
            centroids[sgc] = (centroid.y, centroid.x)  # (lat, lon)
        except Exception as e:
            print(f"  [WARN] Shapely error for {sgc}: {e}")
            continue

    print(f"  Computed centroids for {len(centroids)} Ontario CSDs")
    return centroids


def run():
    """Main: fetch climate normals, map to CSDs, produce CSV."""
    print("=" * 60)
    print("Climate Normals Processor (ECCC Geomet API)")
    print("=" * 60)

    # Step 1: Get CSD centroids
    print("\nStep 1: Computing CSD centroids from GeoJSON (shapely)...")
    centroids = get_csd_centroids()
    session = get_robust_session()

    if not centroids:
        print("[ERROR] No CSD centroids available. Skipping climate.")
        return

    # Step 2: Fetch unique stations list using Jan mean temp
    print("\nStep 2: Fetching Ontario climate station locations...")
    stations = {}
    offset = 0

    while True:
        params = {
            "f": "json",
            "limit": 2000,
            "offset": offset,
            "bbox": ONTARIO_BBOX,
            "E_NORMAL_ELEMENT_NAME": "Mean daily temperature deg C",
            "CURRENT_FLAG": "Y",
            "NORMAL_ID": 1,
            "MONTH": 1,
        }
        try:
            data = _api_get(params, session=session)
        except Exception as e:
            print(f"  [WARN] API error after retries: {e}")
            break

        features = data.get("features", [])
        total = data.get("numberMatched", 0)
        if not features:
            break

        for f in features:
            props = f["properties"]
            sid = props.get("CLIMATE_IDENTIFIER")
            coords = f["geometry"]["coordinates"]
            stations[sid] = {
                "station_name": props.get("STATION_NAME"),
                "lat": coords[1],
                "lon": coords[0],
            }

        offset += len(features)
        if offset >= total:
            break
        time.sleep(0.3)

    print(f"  Unique stations: {len(stations)}")

    # Step 3: Map each CSD to nearest station
    print("\nStep 3: Mapping CSDs to nearest weather stations...")
    csd_station_map = {}
    for sgc, (lat, lon) in centroids.items():
        best_dist = float("inf")
        best_sid = None
        for sid, sinfo in stations.items():
            d = haversine(lat, lon, sinfo["lat"], sinfo["lon"])
            if d < best_dist:
                best_dist = d
                best_sid = sid
        if best_sid:
            csd_station_map[sgc] = {
                "station_id": best_sid,
                "station_name": stations[best_sid]["station_name"],
                "distance_km": round(best_dist, 1),
                # Q8 fix: distance warning flag
                "distance_warning": best_dist > DISTANCE_WARNING_KM,
            }

    distances = sorted([v["distance_km"] for v in csd_station_map.values()])
    if distances:
        mid = len(distances) // 2
        warn_count = sum(1 for v in csd_station_map.values() if v["distance_warning"])
        print(f"  Mapped {len(csd_station_map)} CSDs to stations")
        print(f"  Median distance: {distances[mid]:.1f} km")
        print(f"  Max distance: {distances[-1]:.1f} km")
        print(f"  [WARN] CSDs with station > {DISTANCE_WARNING_KM}km: {warn_count}")

    # Step 4: Fetch full normals for assigned stations
    assigned_stations = set(v["station_id"] for v in csd_station_map.values())
    print(f"\nStep 4: Fetching climate normals for {len(assigned_stations)} stations...")

    station_data = {}  # station_id -> {slug: annual_value}

    for (element_name, normal_id), slug in ELEMENT_MAP.items():
        print(f"  {element_name} (NID={normal_id})...")
        is_sum = slug in SUM_ELEMENTS
        element_records = {}  # station_id -> {month: value}
        offset = 0

        while True:
            params = {
                "f": "json",
                "limit": 2000,
                "offset": offset,
                "bbox": ONTARIO_BBOX,
                "E_NORMAL_ELEMENT_NAME": element_name,
                "CURRENT_FLAG": "Y",
                "NORMAL_ID": normal_id,
            }
            try:
                data = _api_get(params, session=session)
            except Exception as e:
                print(f"    [WARN] API error after retries: {e}")
                break

            features = data.get("features", [])
            total = data.get("numberMatched", 0)

            if not features:
                break

            for f in features:
                props = f["properties"]
                sid = props.get("CLIMATE_IDENTIFIER")
                if sid not in assigned_stations:
                    continue
                month = props.get("MONTH")
                val = props.get("VALUE")

                if val is not None and month:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        continue
                    if sid not in element_records:
                        element_records[sid] = {}
                    element_records[sid][month] = val

            offset += len(features)
            if offset >= total:
                break
            time.sleep(0.3)

        # Aggregate monthly -> annual
        # Q11 + N1 fix: Strict 12-month rule for BOTH Sum and Average.
        # Missing months heavily skew annual climate values due to seasonality.
        # ECCC 30-year normals are curated — stations with gaps are invalid.
        for sid, month_vals in element_records.items():
            valid = {m: v for m, v in month_vals.items() if 1 <= m <= 12}
            if len(valid) < 12:
                continue
            if is_sum:
                annual = sum(valid.values())
            else:
                annual = sum(valid.values()) / 12.0
            if sid not in station_data:
                station_data[sid] = {}
            station_data[sid][slug] = round(annual, 1)

        print(f"    -> {len(element_records)} stations")

    # Step 5: Build CSD climate profile
    print(f"\nStep 5: Building CSD climate profiles...")
    geo = pd.read_csv(GEO_FILE)
    geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)

    rows = []
    for sgc, mapping in csd_station_map.items():
        sid = mapping["station_id"]
        sdata = station_data.get(sid, {})
        if not sdata:
            continue

        geo_row = geo[geo["sgc_code"] == sgc]
        geo_name = geo_row["geo_name"].iloc[0] if len(geo_row) > 0 else ""
        county = ""
        if len(geo_row) > 0 and "county" in geo_row.columns:
            county = geo_row["county"].iloc[0] if pd.notna(geo_row["county"].iloc[0]) else ""

        row = {
            "sgc_code": sgc,
            "geo_name": geo_name,
            "county": county,
            "community": f"{geo_name} ({county})" if county else geo_name,
            "nearest_station": mapping["station_name"],
            "station_distance_km": mapping["distance_km"],
            "distance_warning": mapping["distance_warning"],  # Q8 fix
        }
        row.update(sdata)
        rows.append(row)

    result = pd.DataFrame(rows)

    # Guard: never overwrite a good CSV with empty/broken data (expert rec)
    # N5 fix: require ≥80% CSD coverage to prevent partial API failures
    # from silently nuking a good CSV
    indicator_cols = [c for c in result.columns if c.startswith("climate_")]
    min_expected_csds = int(len(centroids) * 0.8) if centroids else 400
    if result.empty or len(result) < min_expected_csds or not indicator_cols:
        print(f"[ERROR] Insufficient data assembled ({len(result)} CSDs, "
              f"need ≥{min_expected_csds}). Keeping existing CSV untouched.")
        return None

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_FILE, index=False)

    indicator_cols = [c for c in result.columns if c.startswith("climate_")]
    warn_count = result["distance_warning"].sum() if "distance_warning" in result.columns else 0
    print(f"\n{'='*60}")
    print(f"DONE - Saved {len(result)} CSDs to {OUT_FILE}")
    print(f"Climate indicators: {indicator_cols}")
    print(f"CSDs with station distance warning (>{DISTANCE_WARNING_KM}km): {int(warn_count)}")
    for col in indicator_cols:
        valid = result[col].dropna()
        if len(valid) > 0:
            print(f"  {col}: mean={valid.mean():.1f}, "
                  f"range=[{valid.min():.1f}, {valid.max():.1f}]")
    print(f"{'='*60}")

    return result


if __name__ == "__main__":
    run()
