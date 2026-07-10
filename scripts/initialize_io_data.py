import pandas as pd
import numpy as np
from pathlib import Path

# Paths
DATA_DIR = Path(__file__).parent.parent / "data" / "latest"
RAW_SUT = DATA_DIR / "36-10-0489-01.csv"
RAW_MULT = DATA_DIR / "36-10-0113-01.csv"
OUTPUT_SUT = DATA_DIR / "io_supply_use_subset.csv"
OUTPUT_MULT = DATA_DIR / "io_multipliers_standardized.csv"

def clean_join_code(row):
    """Try to extract code from [Bracket], otherwise fallback to map."""
    text = str(row).strip()
    # 1. Regex for [BS111A]
    import re
    match = re.search(r'\[(.*?)\]', text)
    if match:
        return match.group(1)
    
    # 2. Fallback map for common Agri-Food sectors (if brackets missing)
    mapping = {
        "Crop production": "BS111A",
        "Animal production": "BS112A",
        "Aquaculture": "BS1125",
        "Food manufacturing": "BS311",
        "Animal food manufacturing": "BS3111",
        "Grain and oilseed milling": "BS3112",
        "Meat product manufacturing": "BS3116",
        "Beverage and tobacco product manufacturing": "BS312",
        "Greenhouse, nursery and floriculture": "BS1114"
    }
    for key, code in mapping.items():
        if key.lower() in text.lower():
            return code
    return None

def main():
    print("Initializing Economic Impact Data (Robust Mode)...")

    # --- 1. PROCESS SUPPLY USE (SUT) ---
    if RAW_SUT.exists():
        print(f"Processing SUT from {RAW_SUT.name}...")
        df = pd.read_csv(RAW_SUT, low_memory=False)
        
        # Standardize columns
        cols_map = {"REF_DATE": "YEAR", "VALUE": "value_dollars", "Geography": "GEO"}
        df.rename(columns={k: v for k, v in cols_map.items() if k in df.columns}, inplace=True)
        
        # Filter for Canada but KEEP ALL YEARS to ensure overlap with multipliers
        if "GEO" in df.columns:
            df = df[df['GEO'].str.contains("Canada", case=False, na=False)]
        
        # Generate Join Codes
        if "North American Industry Classification System (NAICS)" in df.columns:
             df['io_name'] = df["North American Industry Classification System (NAICS)"]
             df['join_code'] = df['io_name'].apply(clean_join_code)
        
        # Drop rows where we couldn't identify the industry
        df = df.dropna(subset=['join_code'])
        
        df.to_csv(OUTPUT_SUT, index=False)
        print(f"✔ Created {OUTPUT_SUT.name} with {len(df)} rows (Years: {df['YEAR'].unique()})")
    else:
        print(f"❌ Missing raw file: {RAW_SUT}")

    # --- 2. PROCESS MULTIPLIERS ---
    if RAW_MULT.exists():
        print(f"Processing Multipliers from {RAW_MULT.name}...")
        df = pd.read_csv(RAW_MULT, low_memory=False)
        
        cols_map = {"REF_DATE": "YEAR", "VALUE": "value", "Geography": "GEO"}
        df.rename(columns={k: v for k, v in cols_map.items() if k in df.columns}, inplace=True)
        
        # Generate Join Codes using same logic
        if "Input-output industry classification (IOIC)" in df.columns:
            df['industry_name'] = df["Input-output industry classification (IOIC)"]
            df['join_code'] = df['industry_name'].apply(clean_join_code)
        
        # Filter for Total Multipliers (Output & Jobs) to keep file small
        if "Multiplier" in df.columns:
            df.rename(columns={"Multiplier": "multiplier_type"}, inplace=True)
        
        # Keep relevant rows
        target_vars = ["Output", "Jobs", "Gross domestic product at market prices"]
        if "Variables" in df.columns:
            df.rename(columns={"Variables": "variable"}, inplace=True)
            df = df[df['variable'].isin(target_vars)]

        df.to_csv(OUTPUT_MULT, index=False)
        print(f"✔ Created {OUTPUT_MULT.name} with {len(df)} rows (Years: {df['YEAR'].unique()})")
    else:
        print("⚠ Multiplier raw file missing. Please download Table 36-10-0113-01.")

if __name__ == "__main__":
    main()