"""Quick: show 2024 Total crop receipts value per GEO and total sum."""
import pandas as pd

df = pd.read_csv("data/latest/32-10-0045-01.csv", low_memory=False)
tcr = df[df["Type of cash receipts"] == "Total crop receipts"]
y24 = tcr[tcr["REF_DATE"] == 2024].groupby("GEO")["VALUE"].sum()

print("2024 'Total crop receipts' VALUE per GEO:")
for geo, val in y24.items():
    scaled = val * 1000  # scalar = thousands
    print(f"  {geo:35s}  raw={val:>14,.0f}  scaled=${scaled/1e9:.1f}B")

print(f"\nSum of ALL GEOs (raw):    {y24.sum():>14,.0f}")
print(f"Sum of ALL GEOs (scaled): ${y24.sum()*1000/1e9:.1f}B")
print(f"Canada only (raw):        {y24.get('Canada', 0):>14,.0f}")
print(f"Canada only (scaled):     ${y24.get('Canada', 0)*1000/1e9:.1f}B")

# Check how many geos the default selection would pick
all_geos = sorted(tcr["GEO"].dropna().unique().tolist())
print(f"\nAll GEOs in data: {all_geos}")
print(f"Count: {len(all_geos)}")
