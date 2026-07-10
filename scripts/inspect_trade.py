import pandas as pd
from pathlib import Path
import zipfile

# Point to the file you already downloaded
LOCAL_ZIP = Path("data/latest/12100136-eng.zip")
CSV_NAME = "12100136.csv"

def run():
    if not LOCAL_ZIP.exists():
        print(f"❌ File not found: {LOCAL_ZIP}")
        return

    print(f"Inspecting {LOCAL_ZIP}...")
    
    with zipfile.ZipFile(LOCAL_ZIP) as z:
        with z.open(CSV_NAME) as f:
            # Read just 5 rows to check structure
            df = pd.read_csv(f, nrows=5)
            
            print("\n--- COLUMN NAMES ---")
            print(list(df.columns))
            
            print("\n--- FIRST ROW DATA ---")
            print(df.iloc[0])

if __name__ == "__main__":
    run()