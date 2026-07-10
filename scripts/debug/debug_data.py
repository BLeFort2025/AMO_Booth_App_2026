import pandas as pd
import sys
from pathlib import Path

# Paths (Relative to project root)
MULT_FILE = Path("data/latest/io_multipliers_standardized.csv")
HIST_FILE = Path("data/latest/io_supply_use_subset.csv")

def x_ray():
    print("--- STARTING DATA X-RAY ---\n")

    # 1. Check Multiplier File
    if not MULT_FILE.exists():
        print(f"❌ ERROR: Multiplier file not found at {MULT_FILE}")
        print("   Make sure you are running this script from the project root!")
        return
    
    print(f"✅ Found Multiplier File: {MULT_FILE}")
    try:
        mult_df = pd.read_csv(MULT_FILE)
        print(f"   Rows: {len(mult_df)}")
        print("   Sample Industry Codes (First 5):", mult_df['industry_code'].dropna().unique()[:5])
        
        # Look for Food-related terms
        print("\n   [Scanning for Food Manufacturing...]")
        food_mask = mult_df['industry_name'].astype(str).str.contains("Food|Beverage", case=False, na=False)
        food_codes = mult_df.loc[food_mask, ['industry_code', 'industry_name']].drop_duplicates().head(10)
        
        if not food_codes.empty:
            print(food_codes.to_string(index=False))
        else:
            print("   ⚠️ No 'Food' or 'Beverage' industries found in Multipliers!")

    except Exception as e:
        print(f"   ❌ Error reading file: {e}")

    # 2. Check History File
    print("-" * 30)
    if not HIST_FILE.exists():
        print(f"\n❌ ERROR: History file not found at {HIST_FILE}")
        return

    print(f"\n✅ Found History File: {HIST_FILE}")
    try:
        hist_df = pd.read_csv(HIST_FILE)
        print(f"   Rows: {len(hist_df)}")
        print("   Columns:", hist_df.columns.tolist())
        
        print("\n   [Checking for matching codes in History file...]")
        
        # Grab a target code from the multiplier file to test
        target_code = food_codes['industry_code'].iloc[0] if not food_codes.empty else "BS311100"
        print(f"   Target Code from Multipliers: '{target_code}'")
        
        # Check Exact Match
        exact = hist_df[hist_df['io_code'] == target_code]
        if not exact.empty:
            print(f"   ✅ Found EXACT match for '{target_code}'")
        else:
            print(f"   ❌ NO exact match for '{target_code}'")
            
        # Check Fuzzy Matches (Do we have *any* 311?)
        print("\n   [Scanning History for ANY '311' codes...]")
        fuzzy = hist_df[hist_df['io_code'].astype(str).str.contains("311", na=False)]['io_code'].unique()
        
        if len(fuzzy) > 0:
            print(f"   ✅ Found these related codes: {fuzzy}")
        else:
            print("   ❌ NO codes containing '311' found. (Is the file aggregated?)")

    except Exception as e:
        print(f"   ❌ Error reading file: {e}")

    print("\n--- END X-RAY ---")

if __name__ == "__main__":
    x_ray()