import pandas as pd
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_statcan import fetch_table

def run():
    print("--- 🔍 Direct Inspection of GDP Data ---")
    
    # 1. Fetch directly using the project's own tool
    try:
        # This handles finding the file, unzipping, or downloading automatically
        df, _ = fetch_table("36-10-0434-01")
        print("✅ Data Loaded Successfully.")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        return

    # 2. Inspect NAICS Column
    naics_col = next((c for c in df.columns if "NAICS" in c), None)
    
    if naics_col:
        print(f"\n✅ Found NAICS Column: '{naics_col}'")
        print("-" * 40)
        print("Sample Values (First 20 unique codes):")
        unique_vals = sorted(df[naics_col].astype(str).unique())[:20]
        for v in unique_vals:
            print(f"   '{v}'")
            
        print("-" * 40)
        print("Checking for specific targets:")
        targets = ["3253", "482", "484", "411"]
        for t in targets:
            match = next((v for v in unique_vals if t in v), None)
            if match:
                print(f"   🎯 Found target '{t}' as: '{match}'")
            else:
                # Search deeper if not in first 20
                deep_match = next((v for v in df[naics_col].unique() if t in str(v)), "NOT FOUND")
                print(f"   ❓ Target '{t}' found deeper? '{deep_match}'")
                
    else:
        print("\n❌ Could not find a column with 'NAICS' in the name.")
        print("Available Columns:", df.columns.tolist())

if __name__ == "__main__":
    run()