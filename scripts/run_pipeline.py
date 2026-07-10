import json
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- UPDATED IMPORTS ---
# We added 'update_baskets' to this list
from scripts import config_loader, fetch_omafra, update_baskets, process_capex, process_output, fetch_pop_estimates
# -----------------------

from scripts.fetch_statcan import fetch_table, persist_if_changed
from scripts.transform import run as transform_run
from scripts.http_utils import get_robust_session

PIPELINE_STATUS_FP = Path("data/pipeline_status.json")


def save_pipeline_status(changed, failed, total_tables, active_tables) -> None:
    """
    Persist lightweight pipeline run metadata to data/pipeline_status.json.
    """
    PIPELINE_STATUS_FP.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "last_run_local": datetime.now().isoformat(timespec="seconds"),
        "changed_tables": list(changed),
        "failed_tables": list(failed),
        "total_tables": int(total_tables),
        "active_tables": int(active_tables),
    }
    # Use indent=2 for readability.
    PIPELINE_STATUS_FP.write_text(json.dumps(status, indent=2))


def run():
    print("--- Starting Data Pipeline ---")
    tables = config_loader.load_tables()
    active_tables = [t for t in tables if t.get("active", True)]
    statcan_tables = [t for t in active_tables if t.get("source", "statcan") == "statcan"]

    changed, failed = [], []
    session = get_robust_session()

    for t in statcan_tables:
        tid = t["id"]
        try:
            df, content_hash = fetch_table(tid, session)
        except Exception as e:
            print(f"[ERROR] Failed to fetch {tid}: {e}")
            failed.append(tid)
            continue

        try:
            if persist_if_changed(tid, df, content_hash):
                changed.append(tid)
        except Exception as e:
            print(f"[ERROR] Failed to persist {tid}: {e}")
            failed.append(tid)
            continue

    print(f"Updated: {changed}" if changed else "No changes.")
    if failed:
        print(f"Failed to update: {failed}")

    # --- NEW STEP: Process CapEx Data ---
    # Maps raw NAICS capital spending to our specific Industry Baskets
    print("Running CapEx Processor (Table 34-10-0035-01)...")
    try:
        process_capex.run()
    except Exception as e:
        print(f"[WARNING] CapEx processing failed: {e}")
    # -------------------------------------

    # --- NEW STEP: Process Output Data ---
    print("\nRunning Output Processor...")
    try:
        process_output.run()
    except Exception as e:
        print(f"[WARNING] Output processing failed: {e}")
    # -------------------------------------

    # Run OMAFRA fetcher
    fetch_omafra.run()

    # --- Download 2011 NHS (if not already present) ---
    print("\nChecking 2011 NHS Profile download...")
    try:
        from scripts import download_nhs_2011
        download_nhs_2011.run()
    except Exception as e:
        print(f"[WARNING] NHS download skipped: {e}")

    # --- Census Profile (Wellbeing Dashboard) ---
    # Processes manually-downloaded Census ZIPs from data/raw/
    print("\nRunning Census Profile Processor...")
    try:
        from scripts import fetch_census_profile
        fetch_census_profile.run()
    except Exception as e:
        print(f"[WARNING] Census Profile processing skipped: {e}")


    # --- Population Estimates (intercensal gap-filling) ---
    print("\nRunning Population Estimates Processor (Table 17-10-0155-01)...")
    try:
        fetch_pop_estimates.run()
    except Exception as e:
        print(f"[WARNING] Population Estimates processing skipped: {e}")

    # --- CSD Boundaries (Map support for Wellbeing Dashboard) ---
    print("\nRunning CSD Boundary Processor...")
    try:
        from scripts import fetch_csd_boundaries
        fetch_csd_boundaries.run()
    except Exception as e:
        print(f"[WARNING] CSD Boundary processing skipped: {e}")

    # --- Tier 2: Climate Normals (ECCC API) ---
    # Audit 2026-02-24: deprecated fetch_climate (Pipeline A / GitHub data).
    # fetch_climate_normals (Pipeline B / ECCC API) is now the sole climate source.
    print("\nRunning Climate Normals Processor (ECCC Geomet API)...")
    try:
        from scripts import fetch_climate_normals
        fetch_climate_normals.run()
    except Exception as e:
        print(f"[WARNING] Climate normals processing skipped: {e}")

    # --- Tier 2: Broadband Coverage (manual download) ---
    print("\nRunning Broadband Coverage Processor ...")
    try:
        from scripts import fetch_broadband
        fetch_broadband.run()
    except Exception as e:
        print(f"[WARNING] Broadband processing skipped: {e}")

    # --- Tier 2: Health Facilities (manual download) ---
    print("\nRunning Health Facilities Processor ...")
    try:
        from scripts import fetch_health_facilities
        fetch_health_facilities.run()
    except Exception as e:
        print(f"[WARNING] Health facilities processing skipped: {e}")
    # -----------------------------------------------

    # --- NEW STEP: Rural Labour & Housing Data (Page 9) ---
    print("\nRunning Rural Labour & Housing Fetcher (SEPH 14-10-0203-01 + CMHC 34-10-0143-01)...")
    try:
        from scripts import fetch_rural_labour_housing
        fetch_rural_labour_housing.run()
    except Exception as e:
        print(f"[WARNING] Rural Labour & Housing fetch skipped: {e}")
    # -------------------------------------------------------
    
    # --- NEW STEP: Calculate Agri-Food Shares & Update Baskets ---
    # This runs BEFORE the dashboard loads so weights are always fresh
    print("Running Basket Update...")
    update_baskets.run()
    # -------------------------------------------------------------

    transform_run()

    save_pipeline_status(
        changed=changed,
        failed=failed,
        total_tables=len(tables),
        active_tables=len(active_tables),
    )
    print("--- Pipeline Complete ---")

if __name__ == "__main__":
    run()