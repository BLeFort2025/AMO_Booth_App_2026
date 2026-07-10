import requests
import zipfile
import io
import pandas as pd
from pathlib import Path

# --- CONFIGURATION ---
STATCAN_PID = "34100035"  # Capital and repair expenditures (CAPEX)
DOWNLOAD_URL = f"https://www150.statcan.gc.ca/n1/tbl/csv/{STATCAN_PID}-eng.zip"
DATA_DIR = Path(__file__).parent.parent / "data" / "latest"
OUT_FILE = DATA_DIR / "capex_subset.csv"

def run():
    print(f"Downloading CAPEX Table {STATCAN_PID}...")
    
    # 1. Download
    try:
        r = requests.get(DOWNLOAD_URL)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return
    
    # 2. Extract
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = f"{STATCAN_PID}.csv"
        print(f"Extracting {csv_name}...")
        df = pd.read_csv(z.open(csv_name), low_memory=False)
        
    # --- DIAGNOSTIC PRINT ---
    print("\n📊 COLUMN NAMES FOUND:")
    print(list(df.columns))
    print("-" * 30)
    
    # 3. Smart Column Detection
    # We look for the column that distinguishes between "Capital" and "Repair"
    # It is usually "Capital and repair expenditures"
    target_col = "Capital and repair expenditures"
    
    if target_col not in df.columns:
        # Fallback search
        candidates = [c for c in df.columns if "expenditure" in c.lower()]
        if candidates:
            target_col = candidates[0]
            print(f"⚠️ 'Capital and repair expenditures' column not found. Guessing: '{target_col}'")
        else:
            print("❌ CRITICAL ERROR: Could not find the Expenditure Type column.")
            return

    # 4. Filter for Relevance
    print(f"Filtering using column: [{target_col}]...")
    
    # Filter A: Keep only Capital Expenditures (ignore Repair)
    # Note: StatCan value is usually "Capital expenditures"
    df_cap = df[df[target_col] == "Capital expenditures"].copy()
    
    # Filter B: Industries (NAICS)
    # Extract numeric code from "Crop production [111]"
    def extract_code(val):
        import re
        match = re.search(r"\[(\d+)\]", str(val))
        return match.group(1) if match else ""

    naics_col = "North American Industry Classification System (NAICS)"
    if naics_col not in df.columns:
        # Try finding the NAICS column
        naics_candidates = [c for c in df.columns if "NAICS" in c]
        if naics_candidates:
            naics_col = naics_candidates[0]
    
    print(f"Extracting codes from: [{naics_col}]")
    df_cap["naics_code"] = df_cap[naics_col].apply(extract_code)
    
    # Filter for our coalition codes (Start with 111, 112, 311, 312, 3253)
    mask = df_cap["naics_code"].str.match(r"^(111|112|311|312|3253)")
    df_subset = df_cap[mask].copy()
    
    if df_subset.empty:
        print("WARNING: No matching investment data found after filtering.")
        return

    # 5. Save Subset
    # Keep strictly necessary columns
    # Rename for standard dashboard use
    cols = ["REF_DATE", "GEO", naics_col, "naics_code", "VALUE"]
    df_final = df_subset[cols].rename(columns={"REF_DATE": "Year", naics_col: "Industry"})
    
    # Clean Year
    df_final["Year"] = pd.to_numeric(df_final["Year"], errors='coerce')
    df_final = df_final[df_final["Year"] >= 2010]
    
    # Ensure directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    df_final.to_csv(OUT_FILE, index=False)
    print(f"✅ Success! Saved {len(df_final)} rows to {OUT_FILE}")

if __name__ == "__main__":
    run()