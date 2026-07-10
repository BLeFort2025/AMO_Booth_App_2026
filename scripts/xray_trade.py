import pandas as pd
from pathlib import Path
import zipfile

# Configuration
STATCAN_PID = "12100136"
DATA_DIR = Path(__file__).parent.parent / "data" / "latest"
LOCAL_ZIP = DATA_DIR / f"{STATCAN_PID}-eng.zip"
CSV_NAME = f"{STATCAN_PID}.csv"

def run():
    print(f"🔍 X-Raying {LOCAL_ZIP}...")
    
    if not LOCAL_ZIP.exists():
        print("❌ File not found.")
        return

    with zipfile.ZipFile(LOCAL_ZIP) as z:
        with z.open(CSV_NAME) as f:
            # Read a larger chunk to ensure we catch variety
            df = pd.read_csv(f, nrows=50000)
            
            print("\n--- 1. TRADE TYPES SEEN ---")
            print(df['Trade'].unique())
            
            print("\n--- 2. TRADING PARTNERS SEEN ---")
            if 'Trading Partners' in df.columns:
                print(df['Trading Partners'].unique())
            else:
                print("Column 'Trading Partners' not found.")

            print("\n--- 3. NAICS FORMAT SAMPLES (First 20) ---")
            naics_col = 'North American Industry Classification System (NAICS)'
            if naics_col in df.columns:
                unique_naics = df[naics_col].unique()
                for x in unique_naics[:20]:
                    print(f"  '{x}'")
            else:
                print(f"Column '{naics_col}' not found.")

if __name__ == "__main__":
    run()