import pandas as pd
from pathlib import Path

# Path to the file you confirmed exists
FILE_PATH = Path("data/latest/16-10-0047-01.csv")

def run():
    print(f"--- Inspecting {FILE_PATH} ---")
    if not FILE_PATH.exists():
        print("❌ File not found.")
        return

    # Read just the first 10,000 rows to be fast
    df = pd.read_csv(FILE_PATH, nrows=10000, low_memory=False)
    
    print("\n1. COLUMN NAMES:")
    print(df.columns.tolist())
    
    # Check for likely "Adjustment" columns
    potential_cols = [c for c in df.columns if "adj" in c.lower() or "season" in c.lower() or "type" in c.lower()]
    
    print("\n2. UNIQUE VALUES IN ADJUSTMENT COLUMNS:")
    for col in potential_cols:
        print(f"   Column '{col}': {df[col].unique().tolist()}")

if __name__ == "__main__":
    run()