import pandas as pd
from pathlib import Path

# Use the path that worked
FILE_PATH = Path("data/latest/32-10-0136-01.csv")

def run():
    print(f"🕵️ Inspecting {FILE_PATH}...")
    try:
        # Load just the header and a subset of rows to be fast
        df = pd.read_csv(FILE_PATH, low_memory=False)
        
        # 1. Check Column Names
        print("\n--- COLUMN NAMES ---")
        print(list(df.columns))
        
        # 2. Check "Estimates" values (to find the right Expense names)
        if "Estimates" in df.columns:
            print("\n--- FOUND 'ESTIMATES' (First 20 unique containing 'xpense') ---")
            # Filter for string 'xpense' to see relevant ones
            unique_vals = df["Estimates"].unique()
            expenses = [x for x in unique_vals if "xpense" in str(x)]
            for e in expenses[:20]:
                print(f"  '{e}'")
        else:
            print("❌ Column 'Estimates' not found!")

        # 3. Check "Farm type" values
        if "Farm type" in df.columns:
            print("\n--- FOUND 'FARM TYPE' (First 5 unique) ---")
            print(df["Farm type"].unique()[:5])
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run()