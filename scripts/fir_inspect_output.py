"""Final inspection of FIR ETL output."""
import pandas as pd

df = pd.read_csv("data/derived/fir_indicators.csv")

with open("scripts/fir_final_check.txt", "w", encoding="utf-8") as f:
    f.write(f"Shape: {df.shape}\n")
    f.write(f"Municipality codes: {df['fir_code'].nunique()}\n")
    f.write(f"Years: {sorted(df['year'].unique())}\n")
    f.write(f"Records per year:\n")
    for yr, grp in df.groupby("year"):
        f.write(f"  {int(yr)}: {len(grp)} records\n")
    
    f.write(f"\n=== Non-null counts ===\n")
    nn = df.notna().sum()
    for col in df.columns:
        f.write(f"  {col:36s}  {nn[col]:>5d}/{len(df)} ({nn[col]/len(df)*100:5.1f}%)\n")
    
    # Sample from 2024
    f.write(f"\n=== Sample: Toronto 2024 ===\n")
    toronto = df[(df['fir_code'] == '3520') & (df['year'] == 2024)]
    if len(toronto) > 0:
        row = toronto.iloc[0]
        for col in df.columns:
            val = row[col]
            if pd.notna(val) and isinstance(val, float) and abs(val) > 1000:
                f.write(f"  {col:36s} = {val:>18,.0f}\n")
            elif pd.notna(val):
                f.write(f"  {col:36s} = {val}\n")
            else:
                f.write(f"  {col:36s} = NULL\n")
    else:
        f.write("  (Toronto not found in 2024)\n")
        # Find any city for 2024
        sample24 = df[df['year'] == 2024].head(1)
        if len(sample24) > 0:
            row = sample24.iloc[0]
            f.write(f"\n=== Sample: {row['municipality_name']} 2024 ===\n")
            for col in df.columns:
                val = row[col]
                if pd.notna(val) and isinstance(val, float) and abs(val) > 1000:
                    f.write(f"  {col:36s} = {val:>18,.0f}\n")
                elif pd.notna(val):
                    f.write(f"  {col:36s} = {val}\n")
                else:
                    f.write(f"  {col:36s} = NULL\n")

print("Done - see scripts/fir_final_check.txt")
