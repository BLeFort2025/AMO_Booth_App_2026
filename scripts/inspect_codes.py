import pandas as pd
from pathlib import Path
import sys

# --- ROBUST PATH SETUP ---
# Resolves to the folder containing this script (scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
# Resolves to the project root (one level up)
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "latest"

# File Paths
MULT_FILE = DATA_DIR / "io_multipliers_standardized.csv"
HIST_FILE = DATA_DIR / "io_supply_use_subset.csv"

# Keywords to hunt for
KEYWORDS = [
    "cannabis", "marijuana", "hemp", 
    "beer", "brew", "wine", "alcohol", "beverage", 
    "tobacco", "cig", 
    "312", "111", "112"
]

def search_file(filepath: Path, label: str):
    print(f"\n{'='*60}")
    print(f" SEARCHING: {label}")
    print(f" Location: {filepath}")
    print(f"{'='*60}")

    if not filepath.exists():
        print(f"❌ File not found. Checked: {filepath}")
        return

    try:
        # Load data
        df = pd.read_csv(filepath, low_memory=False)
        
        # Determine likely columns
        code_col = "join_code" if "join_code" in df.columns else "industry_code"
        if code_col not in df.columns: code_col = "io_code"
        
        name_col = "industry_name" if "industry_name" in df.columns else "io_name"
        if name_col not in df.columns: name_col = "Industry_Raw"

        print(f"--> Using columns: [{code_col}] and [{name_col}]")
        
        # Search
        mask = pd.Series(False, index=df.index)
        for kw in KEYWORDS:
            mask |= df[name_col].astype(str).str.contains(kw, case=False, na=False)
            mask |= df[code_col].astype(str).str.contains(kw, case=False, na=False)
        
        hits = df[mask][[code_col, name_col]].drop_duplicates().sort_values(code_col)
        
        if hits.empty:
            print("⚠️ No matches found.")
        else:
            print(f"✅ Found {len(hits)} unique codes:\n")
            print(hits.to_string(index=False))
            
    except Exception as e:
        print(f"❌ Error reading file: {e}")

if __name__ == "__main__":
    print(f"Script running from: {SCRIPT_DIR}")
    print(f"Looking for data in: {DATA_DIR}")
    search_file(MULT_FILE, "MULTIPLIERS (The 'Engine' looks here for impact)")
    search_file(HIST_FILE, "HISTORY (The 'Engine' looks here for output values)")