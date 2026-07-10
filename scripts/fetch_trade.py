import pandas as pd
from pathlib import Path
import zipfile
import sys

# --- CONFIGURATION ---
STATCAN_PID = "12100136"
DATA_DIR = Path(__file__).parent.parent / "data" / "latest"
LOCAL_ZIP = DATA_DIR / f"{STATCAN_PID}-eng.zip"
OUT_FILE = DATA_DIR / "trade_dump_raw.csv"  # Intermediate "Broad" file

# Codes to keep (The "Filter List")
TARGET_NAICS_PREFIXES = ["111", "112", "311", "312", "3253"]

def run():
    print(f"--- RUNNING BROAD SWEEP TRADE FETCH ---")
    
    if not LOCAL_ZIP.exists():
        print(f"❌ Error: File not found at {LOCAL_ZIP}")
        return

    print(f"Reading {LOCAL_ZIP}...")
    print("Strategy: Capturing ALL rows for target NAICS codes (ignoring Trade/Partner type for now).")
    
    chunks = []
    chunk_size = 200_000
    row_count = 0
    saved_count = 0
    
    with zipfile.ZipFile(LOCAL_ZIP) as z:
        csv_name = f"{STATCAN_PID}.csv"
        
        with z.open(csv_name) as f:
            iterator = pd.read_csv(f, chunksize=chunk_size, low_memory=False)
            
            for i, chunk in enumerate(iterator):
                if i % 10 == 0:
                    print(f"Scanning chunk {i}... ({row_count:,.0f} rows scanned)")
                
                # --- FILTERING ---
                # 1. Identify Columns (Robust)
                naics_col = "North American Industry Classification System (NAICS)"
                
                # 2. Extract Code (Fast)
                # "Crop production [111]" -> "111"
                # Handle cases where brackets might be missing just in case
                chunk["clean_code"] = chunk[naics_col].astype(str).str.extract(r'\[(\d+)\]')[0]
                
                # 3. Filter ONLY by NAICS (The Broad Net)
                # We drop rows where clean_code is NaN
                chunk = chunk.dropna(subset=["clean_code"])
                
                # Match our target list
                mask_naics = chunk["clean_code"].str.match(f"^({'|'.join(TARGET_NAICS_PREFIXES)})")
                
                # Keep matching rows
                subset = chunk[mask_naics].copy()
                
                if not subset.empty:
                    chunks.append(subset)
                    saved_count += len(subset)
                
                row_count += len(chunk)

    if not chunks:
        print("❌ No matching NAICS codes found in the entire file.")
        return

    print(f"✅ Sweep Complete. Combining {len(chunks)} chunks...")
    df_final = pd.concat(chunks)
    
    print(f"Saving {saved_count:,} rows to {OUT_FILE}...")
    df_final.to_csv(OUT_FILE, index=False)
    
    # --- DIAGNOSTICS ---
    print("\n--- DIAGNOSTICS OF CAPTURED DATA ---")
    print("Unique Trade Types Found:", df_final["Trade"].unique())
    print("Unique Partners Found (First 10):", df_final["Trading Partners"].unique()[:10])
    print("Years Found:", df_final["REF_DATE"].str[:4].unique())
    
    # Run a quick check for our goal
    has_exports = df_final["Trade"].str.contains("Export", case=False).any()
    if has_exports:
        print("\n✅ SUCCESS: We captured EXPORT data!")
    else:
        print("\n⚠️ WARNING: Only Imports were found. The file might not contain exports?")

if __name__ == "__main__":
    run()