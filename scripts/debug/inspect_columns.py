import pandas as pd
import requests, zipfile, io

# Target Table
URL = "https://www150.statcan.gc.ca/n1/tbl/csv/36100478-eng.zip"

print(f"🚀 Sampling {URL}...")
r = requests.get(URL)
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    with z.open("36100478.csv") as f:
        # Read just a small chunk to see the headers/values
        df = pd.read_csv(f, nrows=5000)

print("\n--- COLUMN ANALYSIS ---")
print("Columns found:", df.columns.tolist())

# Check the crucial filter columns
if "Supply and use" in df.columns:
    print("\nUnique values in 'Supply and use':")
    print(df["Supply and use"].unique())
else:
    print("\n❌ Column 'Supply and use' NOT FOUND!")

if "Valuation" in df.columns:
    print("\nUnique values in 'Valuation':")
    print(df["Valuation"].unique())
else:
    print("\n❌ Column 'Valuation' NOT FOUND!")

print("\n--- SAMPLE ROW ---")
print(df.iloc[0])