import pandas as pd
from pathlib import Path
import sys

# --- Configuration ---
DATA_PATH = Path("data/latest/io_multipliers_standardized.csv.gz")

def debug_multiplier_data():
    print("--- MULTIPLIER DATA FORENSIC START ---")
    
    # 1. Load Data
    print(f"\n1. Loading data from: {DATA_PATH}")
    if not DATA_PATH.exists():
        print("ERROR: File not found!")
        return
        
    try:
        df = pd.read_csv(DATA_PATH, low_memory=False)
        print(f"   Loaded {len(df):,} rows.")
    except Exception as e:
        print(f"   Error loading data: {e}")
        return

    # 2. Filter Target: Ontario, 111A
    print("\n2. Filtering for Ontario, join_code='111A'...")
    # Find latest year for this combo
    mask_base = (df["GEO"] == "Ontario") & (df["join_code"] == "111A")
    subset_base = df[mask_base]
    
    if subset_base.empty:
        print("   No data found for Ontario 111A!")
        return
        
    avail_years = sorted(subset_base["YEAR"].unique())
    target_year = avail_years[-1]
    print(f"   Latest Year Found: {target_year} (Available: {avail_years})")
    
    # Filter for target year
    mask_final = mask_base & (df["YEAR"] == target_year)
    subset = df[mask_final].copy()
    print(f"   Rows for {target_year}: {len(subset)}")

    # 3. Inspect "Direct Output"
    print("\n3. Inspecting 'Direct Output' Multiplier...")
    # Flexible match for "Output"
    mask_direct_out = (
        (subset["multiplier_type"] == "Direct multiplier") & 
        (subset["variable"].str.contains("Output", case=False, na=False))
    )
    direct_out_rows = subset[mask_direct_out]
    
    print(f"   Row Count: {len(direct_out_rows)}")
    
    total_val = direct_out_rows["value"].sum()
    print(f"   Sum of Values: {total_val}")
    
    if len(direct_out_rows) > 0:
        print("\n   --- Evidence Rows ---")
        cols = ["variable", "multiplier_type", "uom", "SCALAR_FACTOR", "value"]
        # Only print cols that exist
        cols = [c for c in cols if c in df.columns]
        print(direct_out_rows[cols].to_string())
    else:
        print("   No 'Direct multiplier' rows found for 'Output' variable.")

    # 4. Inspect "Variables" for Lookalikes
    print("\n4. Unique Variables for this Industry:")
    unique_vars = sorted(subset["variable"].unique().astype(str))
    for v in unique_vars:
        print(f"   - {v}")
        
    # Check for duplicates across ALL variables for Direct Multiplier
    print("\n5. Checking for ANY duplicate variables in Direct Multiplier...")
    direct_all = subset[subset["multiplier_type"] == "Direct multiplier"]
    dup_check = direct_all[direct_all.duplicated(subset=["variable"], keep=False)]
    
    if not dup_check.empty:
        print("   [WARNING] Duplicates found for the same variable!")
        print(dup_check[["variable", "value"]].sort_values("variable").to_string())
    else:
        print("   No duplicates found in Direct Multiplier set.")

    print("\n--- MULTIPLIER DATA FORENSIC END ---")

if __name__ == "__main__":
    # Redirect stdout to UTF-8 file to avoid encoding issues on Windows
    # and print to console
    class Tee(object):
        def __init__(self, *files):
            self.files = files
        def write(self, obj):
            for f in self.files:
                f.write(obj)
        def flush(self):
            for f in self.files:
                f.flush()

    with open("debug_multiplier_report.txt", "w", encoding="utf-8") as f:
        original_stdout = sys.stdout
        sys.stdout = Tee(sys.stdout, f)
        try:
            debug_multiplier_data()
        finally:
            sys.stdout = original_stdout
            
