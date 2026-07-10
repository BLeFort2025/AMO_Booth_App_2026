import pandas as pd
from pathlib import Path
import sys
import re

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Constants
OUTPUT_FILE = Path("data/derived/basket_output.csv")
RAW_DATA_DIR = Path("data/latest")

# Table IDs
MFG_TABLE_ID = "16-10-0047-01" 
FARM_TABLE_ID = "32-10-0045-01"

# Baskets Config
BASKETS = {
    "food_beverage_manufacturing": ["311", "3121"], 
}

def load_data(table_id):
    raw_path = RAW_DATA_DIR / f"{table_id}.csv"
    if not raw_path.exists():
        print(f"[WARNING] Raw data for {table_id} not found at {raw_path}.")
        return None
    return pd.read_csv(raw_path, low_memory=False)

def process_manufacturing():
    print(f"\n--- Processing Manufacturing (Table {MFG_TABLE_ID}) ---")
    df = load_data(MFG_TABLE_ID)
    if df is None: return 0.0, 0

    df.columns = df.columns.str.strip()
    
    # 1. Seasonal Filter
    if "Seasonal adjustment" in df.columns:
        df = df[df["Seasonal adjustment"].astype(str).str.contains("Seasonally adjusted", case=False, na=False)]
    
    # 2. Sales Filter
    if "Principal statistics" in df.columns:
        df = df[df["Principal statistics"].astype(str).str.contains("Sales", case=False, na=False)]

    # 3. Date Filter (Last 12 Months)
    df["REF_DATE"] = pd.to_datetime(df["REF_DATE"])
    latest_date = df["REF_DATE"].max()
    start_date = latest_date - pd.DateOffset(months=11)
    
    mask = (df["REF_DATE"] >= start_date) & (df["REF_DATE"] <= latest_date)
    df = df[mask]
    
    # 4. Geo Filter
    if "GEO" in df.columns:
        df = df[df["GEO"] == "Canada"]

    # 5. Extract NAICS
    ind_col = next((c for c in df.columns if "NAICS" in c), None)
    def extract_code(val):
        match = re.search(r'\[(\d+)\]', str(val))
        return match.group(1) if match else None
    df['clean_code'] = df[ind_col].apply(extract_code)

    # Calculate Total
    codes = BASKETS["food_beverage_manufacturing"]
    subset = df[df['clean_code'].isin(codes)].copy()
    
    scalar = 1000 
    if "SCALAR_FACTOR" in subset.columns and not subset.empty:
        first_scalar = str(subset["SCALAR_FACTOR"].iloc[0]).lower()
        if "millions" in first_scalar: scalar = 1_000_000
    
    total_val = subset["VALUE"].sum() * scalar
    print(f"   > Manufacturing: ${total_val/1e9:,.1f} B")
    return total_val, latest_date.year

def process_agriculture():
    print(f"\n--- Processing Agriculture (Table {FARM_TABLE_ID}) ---")
    df = load_data(FARM_TABLE_ID)
    if df is None: return 0.0, 0

    df.columns = df.columns.str.strip()

    # --- INTELLIGENT COLUMN SEARCH ---
    # We now look for 'Total farm cash receipts' exactly as found in your file inspector
    target_row_val = "Total farm cash receipts"
    target_col = None
    
    for col in df.columns:
        if df[col].astype(str).str.contains(target_row_val, case=False, regex=False).any():
            target_col = col
            break
            
    if target_col:
        # Strict filter on that column
        df = df[df[target_col].astype(str).str.strip() == target_row_val]
    else:
        print(f"   [ERROR] Could not find row '{target_row_val}' in any column.")
        return 0.0, 0

    # 2. Date Filter (Latest Year)
    if "REF_DATE" in df.columns:
        latest_year = df["REF_DATE"].max()
        df = df[df["REF_DATE"] == latest_year]
    else:
        latest_year = 2024

    # 3. Geo Filter
    if "GEO" in df.columns:
        df = df[df["GEO"] == "Canada"]

    # Scalar Logic
    scalar = 1000
    if "SCALAR_FACTOR" in df.columns and not df.empty:
        first_scalar = str(df["SCALAR_FACTOR"].iloc[0]).lower()
        if "millions" in first_scalar: scalar = 1_000_000
    
    total_val = df["VALUE"].sum() * scalar
    print(f"   > Agriculture: ${total_val/1e9:,.1f} B (Year {latest_year})")
    return total_val, latest_year

def run():
    print("--- Generating Consolidated Output Baseline ---")
    
    mfg_val, mfg_year = process_manufacturing()
    ag_val, ag_year = process_agriculture()
    
    results = []
    
    if mfg_val > 0:
        results.append({
            "basket_key": "food_beverage_manufacturing",
            "verified_output": mfg_val,
            "data_year": mfg_year
        })
        
    if ag_val > 0:
        results.append({
            "basket_key": "primary_agriculture",
            "verified_output": ag_val,
            "data_year": ag_year
        })
 
    if mfg_val > 0 and ag_val > 0:
        total_system = mfg_val + ag_val
        print(f"\n   > CFA Food System (Combined): ${total_system/1e9:,.1f} B")
        results.append({
            "basket_key": "cfa_food_system",
            "verified_output": total_system,
            "data_year": max(mfg_year, ag_year)
        })
 
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False)
    print(f"\n[OK] Saved Consolidated Output to {OUTPUT_FILE}")

if __name__ == "__main__":
    run()