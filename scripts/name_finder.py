import pandas as pd
from pathlib import Path

# 1. Point to the file
file_path = Path("data/latest/io_supply_use_subset.csv")

if not file_path.exists():
    print(f"❌ Error: File not found at {file_path}")
else:
    print(f"✅ Reading {file_path}...")
    df = pd.read_csv(file_path)
    
    # Ensure join_code is string
    df['join_code'] = df['join_code'].astype(str)

    # 2. Define the Target Codes we need for the Dashboard
    # 3253 = Fertilizer, 3331 = Machinery, 482 = Rail, 484 = Trucking, 411/413/445 = Wholesale/Retail
    targets = ["3253", "3331", "482", "484", "411", "413", "445"]
    
    print("\n--- FORENSIC CODE AUDIT ---")
    
    for target in targets:
        # Find rows starting with this code
        mask = df['join_code'].str.startswith(target)
        subset = df[mask]
        
        if not subset.empty:
            # Check what variables we have (Output vs GDP)
            vars_found = subset['variable'].unique().tolist()
            total_val = subset['VALUE'].sum()
            exact_codes = subset['join_code'].unique().tolist()
            
            print(f"✅ Target {target}: FOUND matches {exact_codes}")
            print(f"   -> Variables: {vars_found}")
            print(f"   -> Total Value: ${total_val/1e9:,.2f} Billion")
        else:
            print(f"❌ Target {target}: NO MATCH found.")

    print("\n---------------------------")
    print("If you see ✅ matches above, 'process_missing_links.py' will work.")