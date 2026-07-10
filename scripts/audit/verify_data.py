import pandas as pd
from pathlib import Path

FILE = Path("data/latest/io_supply_use_subset.csv")

if not FILE.exists():
    print("❌ File NOT found!")
else:
    df = pd.read_csv(FILE)
    codes = df['io_code'].astype(str).unique()
    
    # Check for Food Mfg (311)
    has_food = any("311" in c for c in codes)
    
    print(f"File Size: {len(df):,} rows")
    if has_food:
        print("✅ SUCCESS: Found Detailed Food Manufacturing codes (e.g. BS3111).")
        print("   -> The Dashboard WILL work now.")
    else:
        print("❌ FAILURE: Only found Summary codes (e.g. BS3A0).")
        print("   -> The Dashboard will show $0/Empty.")