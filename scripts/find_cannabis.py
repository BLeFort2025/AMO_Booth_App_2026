import pandas as pd

# Load the data
print("Loading data...")
df = pd.read_csv('data/latest/io_multipliers_standardized.csv.gz')

# 1. Print the actual column names
print("\n--- ACTUAL COLUMN NAMES ---")
print(df.columns.tolist())

# 2. Search EVERY text column for 'Cannabis'
print("\n--- SEARCHING FOR 'CANNABIS' ---")
found = False
for col in df.select_dtypes(include=['object']).columns:
    # Look for the word Cannabis (case insensitive)
    matches = df[df[col].astype(str).str.contains('Cannabis', case=False, na=False)]
    
    if not matches.empty:
        found = True
        print(f"\n[MATCH FOUND] In column: '{col}'")
        # Print the first few results
        # We try to show the first column (usually the Code) and the matching column
        cols_to_show = [df.columns[0], col] 
        print(matches[cols_to_show].drop_duplicates().head(10))

if not found:
    print("\n❌ 'Cannabis' not found in any column.")