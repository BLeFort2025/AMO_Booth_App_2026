import pandas as pd
from pathlib import Path

# --- CONFIGURATION ---
DATA_DIR = Path(__file__).parent.parent / "data" / "latest"
INPUT_FILE = DATA_DIR / "trade_dump_raw.csv"
OUTPUT_FILE = DATA_DIR / "trade_subset.csv"

def run():
    print("--- SMART PROCESSING TRADE DATA ---")
    print(f"Reading: {INPUT_FILE}")
    
    if not INPUT_FILE.exists():
        print("❌ Error: Raw dump file not found.")
        return

    # 1. READ A SAMPLE TO FIND THE EXACT STRINGS
    # We read 100k rows to scan for 'Trade' values
    print("Scanning for Trade Types...")
    sample = pd.read_csv(INPUT_FILE, nrows=500000)
    
    unique_trade = sample["Trade"].unique()
    unique_partners = sample["Trading Partners"].unique()
    
    print(f"\n📢 FOUND TRADE TYPES: {unique_trade}")
    print(f"📢 FOUND PARTNERS (First 5): {unique_partners[:5]}")
    
    # 2. DETERMINE FILTERS DYNAMICALLY
    # We look for keywords regardless of exact phrasing
    export_term = next((t for t in unique_trade if "Export" in str(t)), None)
    total_term = next((t for t in unique_partners if "Total" in str(t) and "countries" in str(t)), None)
    
    if not export_term:
        print("\n❌ CRITICAL: No 'Export' data found in sample. The dump might contain Imports only.")
        # Fallback: Check if file is sorted by Trade Type (Imports first).
        # We might need to process the whole file to find Exports.
    
    print(f"\n🎯 Target Export Label: '{export_term}'")
    print(f"🎯 Target Partner Label: '{total_term}'")
    
    # 3. PROCESS FULL FILE
    print("\nProcessing full file with identified targets...")
    chunk_size = 500_000
    chunks = []
    
    # If we didn't find export_term in sample, we filter loosely for "Export" in the loop
    
    for chunk in pd.read_csv(INPUT_FILE, chunksize=chunk_size, low_memory=False):
        # Filter for EXPORTS (Any string containing 'Export')
        mask_export = chunk["Trade"].astype(str).str.contains("Export", case=False, na=False)
        
        # Filter for ALL COUNTRIES (Any string containing 'Total' and 'countries')
        mask_partner = chunk["Trading Partners"].astype(str).str.contains("Total.*countries", case=False, regex=True, na=False)
        
        subset = chunk[mask_export & mask_partner].copy()
        
        if not subset.empty:
            # Minimal columns
            # Ensure columns exist (handle slight variations if any)
            cols = chunk.columns
            ref_col = "REF_DATE"
            geo_col = "GEO"
            val_col = "VALUE"
            # We already have clean_code from the dump
            
            subset = subset[[ref_col, geo_col, "clean_code", val_col]]
            subset = subset.rename(columns={ref_col: "Year", "clean_code": "naics_code"})
            chunks.append(subset)

    if not chunks:
        print("❌ No Export/Total rows found in the entire file.")
        return

    # 4. AGGREGATE
    df = pd.concat(chunks)
    df["Year"] = df["Year"].astype(str).str[:4].astype(int)
    df_annual = df.groupby(["Year", "GEO", "naics_code"], as_index=False)["VALUE"].sum()
    
    df_annual.to_csv(OUTPUT_FILE, index=False)
    
    total_2022 = df_annual[df_annual["Year"] == 2022]["VALUE"].sum()
    print(f"\n✅ SUCCESS! Created {OUTPUT_FILE}")
    print(f"   (2022 Total Exports Found: ${total_2022/1e9:,.1f} Billion)")

if __name__ == "__main__":
    run()