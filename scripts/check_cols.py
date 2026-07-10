import pandas as pd
from pathlib import Path

# Path to the downloaded Rail data
csv_path = Path("data/latest/23-10-0216-02.csv")

if csv_path.exists():
    try:
        # Read just the first row to get headers
        df = pd.read_csv(csv_path, nrows=0) 
        print(f"\n--- Columns in {csv_path.name} ---")
        for col in df.columns:
            print(f"'{col}'")
        print("-----------------------------------\n")
    except Exception as e:
        print(f"Error reading file: {e}")
else:
    print(f"File not found: {csv_path}")