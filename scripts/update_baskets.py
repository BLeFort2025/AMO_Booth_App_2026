import pandas as pd
import yaml
from pathlib import Path
import sys

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configuration Paths
DATA_DIR = PROJECT_ROOT / "data" / "latest"
CONFIG_PATH = PROJECT_ROOT / "config" / "io_baskets.yml"

def load_local_csv(table_id):
    fp = DATA_DIR / f"{table_id}.csv"
    if not fp.exists():
        print(f"[WARN] Missing dataset {table_id}. Skipping calculation.")
        return None
    try:
        df = pd.read_csv(fp, low_memory=False)
        if 'YEAR' not in df.columns and 'REF_DATE' in df.columns:
            df['YEAR'] = pd.to_datetime(df['REF_DATE'], errors='coerce').dt.year
        return df
    except Exception as e:
        print(f"[ERROR] Could not read {table_id}: {e}")
        return None

def calculate_rail_share():
    print("--- Calculating Rail Transport Share ---")
    df = load_local_csv("23-10-0216-02")
    if df is None: return 0.15

    latest_year = int(df['YEAR'].max())
    df = df[df['YEAR'] == latest_year].copy()
    
    # Use the specific column name we verified
    comm_col = "Railway carloading components"
    
    if comm_col not in df.columns:
        print(f"[ERROR] Column '{comm_col}' not found. Available: {list(df.columns)}")
        return 0.15

    # Define Agri-Food Keywords
    ag_keywords = [
        "Wheat", "Canola", "Grain", "Oilseed", "Barley", "Oats", "Rye", 
        "Vegetable", "Fruit", "Animal feed", "Fertilizer", "Pesticide", 
        "Potash", "Meat", "Food", "Beverage", "Agricultural", "Live animals",
        "Sugar", "Milled grain", "Fats, oils"
    ]
    
    # 1. Get Total Volume (Sum of all months in the year)
    total_mask = df[comm_col].str.contains("Total traffic", case=False, na=False)
    total_rows = df[total_mask]
    
    if total_rows.empty:
        # Fallback: Sum the max values if no total row exists (unlikely)
        total_volume = df['VALUE'].sum()
    else:
        # --- FIX: Sum the total rows (12 months), don't just take the max ---
        total_volume = total_rows['VALUE'].sum()
    
    # 2. Get Ag Volume (Sum of all months for Ag commodities)
    # We use 'title' case matching to be safer with StatCan formatting
    ag_mask = df[comm_col].str.contains('|'.join(ag_keywords), case=False, na=False)
    ag_rows = df[ag_mask & ~total_mask]
    
    ag_volume = ag_rows['VALUE'].sum()

    # Debug Output
    print(f"DEBUG: Matched {len(ag_rows[comm_col].unique())} categories.")
    
    if total_volume == 0:
        return 0.0
        
    share = ag_volume / total_volume
    
    # Sanity check: Cap at 100% just in case of data anomalies
    if share > 1.0:
        print(f"[WARN] Calculated share {share:.1%} > 100%. Data anomaly detected. Capping at 100%.")
        share = 1.0
        
    print(f"[RESULT] Ag Share of Rail ({latest_year}): {share:.1%}")
    return float(share)

def update_config(rail_share):
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Config file not found at {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)

    if 'baskets' in config and 'agri_transport_logistics' in config['baskets']:
        config['baskets']['agri_transport_logistics']['calculated_share'] = rail_share
        
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(config, f, sort_keys=False)
        print(f"[SUCCESS] Updated {CONFIG_PATH} with live weights.")
    else:
        print("[ERROR] Could not find 'agri_transport_logistics' in 'baskets'. Check io_baskets.yml")

def run():
    rail_share = calculate_rail_share()
    update_config(rail_share)

if __name__ == "__main__":
    run()