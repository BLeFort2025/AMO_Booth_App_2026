import pandas as pd
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# We look for the file in data/raw or data/latest
# The fetcher usually caches it. Let's try to find it.
def find_gdp_file():
    candidates = [
        Path("data/latest/36-10-0434-01.csv"),
        Path("data/raw/36-10-0434-01.csv"),
        Path("data/latest/36100434.csv")
    ]
    for p in candidates:
        if p.exists(): return p
    return None

def run():
    print("--- 🔍 Inspecting GDP Data Structure ---")
    file_path = find_gdp_file()
    
    if not file_path:
        print("❌ Could not find the GDP CSV file. Did the previous script download it?")
        # Try running fetch manually if you want, but usually it saves to disk.
        return

    print(f"Reading {file_path}...")
    df = pd.read_csv(file_path, nrows=500) # Read first 500 rows
    
    # 1. Identify NAICS Column
    naics_col = next((c for c in df.columns if "NAICS" in c), None)
    
    if naics_col:
        print(f"\n✅ Found NAICS Column: '{naics_col}'")
        print("Sample Values (First 20):")
        unique_vals = df[naics_col].unique()[:20]
        for v in unique_vals:
            print(f"   '{v}'")
    else:
        print("\n❌ Could not find a column with 'NAICS' in the name.")
        print("Available Columns:", df.columns.tolist())

if __name__ == "__main__":
    run()