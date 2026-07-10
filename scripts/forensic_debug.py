import pandas as pd
import yaml
from pathlib import Path

# --- Configuration ---
# Use absolute paths if possible or relative to where script is run. 
# We'll assume the script is run from project root or handles paths robustly.
# But for this forensic script, hardcoded relative paths from project root work best if run from root.
DATA_PATH = Path("data/latest/io_supply_use_subset.csv")
CONFIG_PATH = Path("config/io_baskets.yml")

def normalize_code_simple(code: str) -> str:
    """Helper to strip prefixes from YAML config to match data.
       Copied from scripts/io_multipliers_engine.py
    """
    s = str(code).upper().strip()
    for prefix in ["BS", "GS", "NP"]:
        s = s.replace(prefix, "")
    return s.rstrip("0")

def forensic_investigation():
    print("--- FORENSIC INVESTIGATION START ---\n")
    
    # Check if running from correct directory
    if not DATA_PATH.exists():
        print(f"ERROR: Data file not found at {DATA_PATH.resolve()}")
        print("Please run this script from the project root.")
        return

    # 1. Load Data
    print(f"Loading data from: {DATA_PATH}")
    try:
        df = pd.read_csv(DATA_PATH, low_memory=False)
        print("Data loaded successfully.")
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # 2. Filter Raw Rows
    print("\n--- TEST CASE: Ontario 2022, join_code 111A ---")
    
    # Ensure columns exist
    required_cols = ["YEAR", "GEO", "join_code", "VALUE"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"CRITICAL ERROR: Missing columns: {missing}")
        print(f"Available columns: {df.columns.tolist()}")
        return

    # Filter
    mask = (
        (df["YEAR"] == 2022) & 
        (df["GEO"] == "Ontario") & 
        (df["join_code"].astype(str) == "111A")
    )
    subset = df[mask]
    
    # 3. Print Evidence
    print(f"Row Count: {len(subset)}")
    
    if len(subset) > 0:
        print("\nFull Rows Evidence:")
        cols_to_show = ["io_name", "join_code", "io_code", "Product", "VALUE", "SCALAR_FACTOR"]
        # Only show columns that actually exist
        cols_to_show = [c for c in cols_to_show if c in df.columns]
        print(subset[cols_to_show].to_string())
        
        # Check for multiple rows mapping to same join_code via different io_codes
        unique_io_codes = subset["io_code"].unique() if "io_code" in df.columns else []
        if len(unique_io_codes) > 1:
            print(f"\n[WARNING] Multiple raw io_codes mapping to '111A': {unique_io_codes}")
        else:
             print("\nSingle unique io_code found for this join_code.")

        # Simulate get_actual_output
        total_value = subset["VALUE"].sum()
        print(f"\nSimulated get_actual_output Result: {total_value:,.2f}")
    else:
        print("No rows found for this filter!")

    # 4. Check Aggregation
    print("\n--- CHECKING AGGREGATION & BASKET CONFIG ---")
    if not CONFIG_PATH.exists():
        print(f"Config file not found at {CONFIG_PATH.resolve()}")
        return

    try:
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        
        baskets = config.get("baskets", {})
        primary_ag = baskets.get("primary_agriculture", {})
        
        print("Basket: Primary Agriculture")
        match_conf = primary_ag.get("match", {})
        prefixes = [normalize_code_simple(p) for p in match_conf.get("any_code_prefix", [])]
        exacts = [normalize_code_simple(e) for e in match_conf.get("any_code_exact", [])]
        
        print(f"Configured Prefixes (Normalized): {prefixes}")
        print(f"Configured Exact Matches (Normalized): {exacts}")

        # Get all available codes in the data for Ontario 2022
        # Use simple logic from engine: get unique join_codes
        # We need to see which ones would be selected for the basket.
        
        data_mask = (df["YEAR"] == 2022) & (df["GEO"] == "Ontario")
        # Ensure join_code is string
        df.loc[data_mask, "join_code"] = df.loc[data_mask, "join_code"].astype(str)
        
        all_codes_in_data = df.loc[data_mask, ["join_code", "io_name"]].drop_duplicates()
        
        selected_codes = []
        for _, row in all_codes_in_data.iterrows():
            code = str(row["join_code"])
            # Simplified matching logic from engine
            is_match = False
            if code in exacts: 
                is_match = True
            elif any(code.startswith(str(p)) for p in prefixes): 
                is_match = True
            
            # Check exclusions (logic simplified for this check as we suspect inclusion)
            exclusion_conf = primary_ag.get("exclude", {})
            ex_exacts = [normalize_code_simple(e) for e in exclusion_conf.get("any_code_exact", [])]
            
            if code in ex_exacts:
                is_match = False
            
            if is_match:
                selected_codes.append((code, row["io_name"]))
        
        print("\nSelected Industry Codes for 'Primary Agriculture':")
        selected_codes.sort()
        for code, name in selected_codes:
            print(f" - {code}: {name}")
            
        # Specific double counting check
        has_111A = any(c == "111A" for c, n in selected_codes)
        has_1114 = any(c == "1114" for c, n in selected_codes) # Greenhouse
        
        if has_111A and has_1114:
            print("\n[CRITICAL WARNING] POTENTIAL DOUBLE COUNTING DETECTED!")
            print("Both '111A' (Parent) and '1114' (Child/Greenhouse) are selected.")
        elif has_111A:
             print("\nNote: '111A' is selected.")

        # --- EXTENDED INVESTIGATION: SUMMATION ---
        print("\n--- COMPONENT BREAKDOWN (Ontario 2022) ---")
        codes_list = [c for c, n in selected_codes]
        
        mask_basket = (
            (df["YEAR"] == 2022) & 
            (df["GEO"] == "Ontario") & 
            (df["join_code"].astype(str).isin(codes_list))
        )
        basket_rows = df[mask_basket]
        
        print(f"{'Code':<8} | {'Value ($)':>20} | {'Name'}")
        print("-" * 80)
        total_val = 0
        for _, row in basket_rows.iterrows():
            val = row["VALUE"]
            total_val += val
            print(f"{row['join_code']:<8} | {val:,.2f} | {row['io_name']}")
            
        print("-" * 80)
        print(f"{'TOTAL':<8} | {total_val:,.2f} | Primary Agriculture Basket Sum")

        print("\n--- REFERENCE CHECK (Canada 2022) ---")
        # Check Canada 111A value
        mask_can = (df["YEAR"] == 2022) & (df["GEO"] == "Canada") & (df["join_code"].astype(str) == "111A")
        val_can = df.loc[mask_can, "VALUE"].sum()
        print(f"Canada 2022 '111A' Value: {val_can:,.2f} (User expects ~$63B)")
        
        # Check Canada Total Basket Sum
        mask_can_basket = (df["YEAR"] == 2022) & (df["GEO"] == "Canada") & (df["join_code"].astype(str).isin(codes_list))
        basket_rows_can = df[mask_can_basket]
        val_can_total = basket_rows_can["VALUE"].sum()
        
        print("\n--- COMPONENT BREAKDOWN (Canada 2022) ---")
        print(f"{'Code':<8} | {'Value ($)':>20} | {'Name'}")
        print("-" * 80)
        for _, row in basket_rows_can.iterrows():
            print(f"{row['join_code']:<8} | {row['VALUE']:,.2f} | {row['io_name']}")
        print("-" * 80)
        print(f"{'TOTAL':<8} | {val_can_total:,.2f} | Primary Agriculture Basket Sum")


        
    except Exception as e:
        print(f"Error parsing config: {e}")

    print("\n--- FORENSIC INVESTIGATION END ---")

if __name__ == "__main__":
    import sys
    # Redirect stdout to a file with UTF-8 encoding
    with open("debug_report_utf8.txt", "w", encoding="utf-8") as f:
        original_stdout = sys.stdout
        sys.stdout = f
        try:
            forensic_investigation()
        finally:
            sys.stdout = original_stdout
    
    # Also print to console for confirmation
    print("Forensic investigation complete. Report saved to debug_report_utf8.txt")
