import pandas as pd
from pathlib import Path

# Path to the file
FILE_PATH = Path("data/latest/32-10-0045-01.csv")

def run():
    print(f"--- Inspecting {FILE_PATH} ---")
    if not FILE_PATH.exists():
        print("❌ File not found.")
        return

    df = pd.read_csv(FILE_PATH, low_memory=False)
    
    # Check the specific column we identified from your error message
    target_col = "Type of cash receipts"
    
    if target_col in df.columns:
        print(f"\nUnique values in '{target_col}':")
        # Get unique values, sort them, and print
        uniques = sorted(df[target_col].astype(str).unique())
        for val in uniques:
            print(f"  - '{val}'")
    else:
        print(f"❌ Column '{target_col}' not found.")

if __name__ == "__main__":
    run()