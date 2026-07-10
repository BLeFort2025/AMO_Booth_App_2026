import pandas as pd
from pathlib import Path

# Path to the raw provincial multipliers we downloaded
RAW_FILE = Path("data/latest/3610059501.csv")

def inspect():
    if not RAW_FILE.exists():
        print("❌ Raw file not found. Run fetch_all_raw.py first.")
        return

    print(f"📖 Reading {RAW_FILE}...")
    # Read columns to find the exact name for "Geographical coverage"
    df_head = pd.read_csv(RAW_FILE, nrows=5)
    cols = df_head.columns.tolist()
    
    # Look for likely candidates
    geo_cov_col = next((c for c in cols if "coverage" in c.lower()), None)
    
    if geo_cov_col:
        print(f"✅ Found column: '{geo_cov_col}'")
        
        # Read the full column to get unique values
        df = pd.read_csv(RAW_FILE, usecols=[geo_cov_col])
        uniques = df[geo_cov_col].unique()
        
        print("\n📊 Unique Geographic Coverages found:")
        for u in uniques:
            print(f"   - {u}")
    else:
        print("❌ 'Geographical coverage' column not found in headers:")
        print(cols)

if __name__ == "__main__":
    inspect()