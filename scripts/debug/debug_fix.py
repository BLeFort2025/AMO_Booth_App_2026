import pandas as pd
import yaml
from pathlib import Path
import sys

# --- CONFIG ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data" / "latest"
SUT_FILE = DATA_DIR / "io_supply_use_subset.csv"
MULT_FILE = DATA_DIR / "io_multipliers_standardized.csv.gz"
BASKET_FILE = PROJECT_ROOT / "config" / "io_baskets.yml"

def normalize_code_simple(code):
    """Matches the logic in your engine script"""
    s = str(code).upper().strip()
    for prefix in ["BS", "GS", "NP"]:
        s = s.replace(prefix, "")
    return s.rstrip("0")

print(f"--- DIAGNOSTIC MODE ---")
print(f"Root: {PROJECT_ROOT}")

# 1. DIAGNOSE DOUBLE COUNTING
print(f"\n1. CHECKING OUTPUT DATA ({SUT_FILE.name})...")
if not SUT_FILE.exists():
    print(f"❌ File not found: {SUT_FILE}")
else:
    df_sut = pd.read_csv(SUT_FILE)
    # Check Ontario 2022 Crop Production (BS111A)
    mask = (
        (df_sut["GEO"] == "Ontario") & 
        (df_sut["YEAR"] == 2022) & 
        (df_sut["join_code"] == "111A")
    )
    row = df_sut[mask]
    
    if row.empty:
        print("❌ No data found for Ontario 2022 Crop Production (111A)")
    else:
        val = row["VALUE"].iloc[0]
        print(f"   Found Row: {row.to_dict('records')[0]}")
        print(f"   Value: ${val:,.0f}")
        
        if 18_000_000_000 < val < 20_000_000_000:
            print("   🔴 RESULT: DOUBLE COUNTED (~$19B). The Transform script needs to be re-run.")
        elif 9_000_000_000 < val < 10_000_000_000:
            print("   🟢 RESULT: CORRECT (~$9.5B). The file is clean. Streamlit Cache is the problem.")
        else:
            print("   ⚠️ RESULT: Unexpected value.")

# 2. DIAGNOSE BASKETS
print(f"\n2. CHECKING BASKETS CONFIG ({BASKET_FILE.name})...")
if not BASKET_FILE.exists():
    print(f"❌ File not found at: {BASKET_FILE}")
else:
    print(f"   ✅ Found config file.")
    try:
        with open(BASKET_FILE, "r") as f:
            baskets = yaml.safe_load(f)
        
        # Check Primary Ag
        ag_conf = baskets.get("baskets", {}).get("primary_agriculture", {})
        prefixes = ag_conf.get("match", {}).get("any_code_prefix", [])
        print(f"   Loaded Prefixes for Primary Ag: {prefixes}")
        
        # Check matching against Multipliers
        if MULT_FILE.exists():
            df_mult = pd.read_csv(MULT_FILE)
            sample_code = "111A" # Crop production
            
            # Simulate matching logic
            clean_prefixes = [normalize_code_simple(p) for p in prefixes]
            print(f"   Cleaned Prefixes: {clean_prefixes}")
            
            is_match = any(sample_code.startswith(p) for p in clean_prefixes)
            if is_match:
                print(f"   🟢 LOGIC TEST: Code '111A' successfully matches prefix.")
            else:
                print(f"   🔴 LOGIC TEST: Code '111A' FAILED to match. Check normalization.")
                
            # Count total matches
            all_codes = df_mult["join_code"].unique().astype(str)
            matches = [c for c in all_codes if any(c.startswith(p) for p in clean_prefixes)]
            print(f"   Found {len(matches)} industries matching Primary Ag in the actual data.")
        else:
            print("   ⚠️ Cannot test matching (Multipliers file missing).")
            
    except Exception as e:
        print(f"   ❌ Error parsing YAML: {e}")

print("\n--- END DIAGNOSTIC ---")