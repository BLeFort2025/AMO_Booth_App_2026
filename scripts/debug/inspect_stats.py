import pandas as pd

# The large file path you mentioned
file_path = r"C:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter\data\latest\36-10-0478-01.csv"

print(f"Scanning file: {file_path}...\n")

try:
    # 1. READ ONLY THE FIRST 5 ROWS to see headers
    df_head = pd.read_csv(file_path, nrows=5)
    print("--- COLUMN NAMES ---")
    print(df_head.columns.tolist())
    print("\n")

    # 2. READ A CHUNK to find the correct 'Output' variable
    # We read 50,000 rows to ensure we capture the metadata categories
    df_chunk = pd.read_csv(file_path, nrows=50000)

    # 3. IDENTIFY KEY COLUMNS
    # We are looking for columns that might distinguish "Output" from "GDP" or "Inputs"
    # Common names in Stats Can tables: 'Estimates', 'Variables', 'Prices', 'Valuation'
    
    print("--- UNIQUE VALUES IN KEY COLUMNS ---")
    
    # List of columns to check for categorical values
    potential_columns = [
        'Variable', 'Estimates', 'Prices', 'Valuation', 
        'UOM', 'Unit of measure', 
        'North American Industry Classification System (NAICS)'
    ]
    
    for col in df_chunk.columns:
        if col in potential_columns or "Variable" in col or "Estimates" in col:
            unique_vals = df_chunk[col].dropna().unique()
            print(f"\nUnique values in column '{col}':")
            # Print all if small list, else print first 20
            if len(unique_vals) < 50:
                print(unique_vals)
            else:
                print(f"(Showing first 20 of {len(unique_vals)}): {unique_vals[:20]}")

    print("\n--- SAMPLE ROW ---")
    print(df_chunk.iloc[0].to_dict())

except Exception as e:
    print(f"Error reading file: {e}")