"""Audit TFW and employment StatCan data to derive vacancy/labor metrics."""
import sys
sys.stdout = open("_tfw_audit.txt", "w", encoding="utf-8")
import pandas as pd

# === TFW data (32-10-0218) ===
print("=== TFW (32-10-0218) ===")
tfw = pd.read_csv("data/latest/32-10-0218-01.csv", low_memory=False)
print(f"Rows: {len(tfw)}, Cols: {list(tfw.columns)}")
print(f"REF_DATE range: {tfw['REF_DATE'].min()} - {tfw['REF_DATE'].max()}")
print(f"GEO unique: {sorted(tfw['GEO'].unique())}")
non_std = [c for c in tfw.columns if c not in ['REF_DATE','GEO','DGUID','UOM','UOM_ID','SCALAR_FACTOR','SCALAR_ID','VECTOR','COORDINATE','VALUE','STATUS','SYMBOL','TERMINATED','DECIMALS']]
print(f"Dim columns: {non_std}")
for c in non_std:
    print(f"  {c}: {sorted(tfw[c].unique())}")
latest = tfw[tfw['REF_DATE'] == tfw['REF_DATE'].max()]
print(f"\nLatest year ({tfw['REF_DATE'].max()}):")
for _, r in latest.head(10).iterrows():
    print(f"  {r['GEO']:<25} | {r.get(non_std[0], ''):<50} | {r['VALUE']}")

# === Employment by province (32-10-0216) ===
print("\n\n=== Employment by Province (32-10-0216) ===")
emp = pd.read_csv("data/latest/32-10-0216-01.csv", low_memory=False)
print(f"Rows: {len(emp)}")
print(f"REF_DATE range: {emp['REF_DATE'].min()} - {emp['REF_DATE'].max()}")
print(f"GEO unique: {sorted(emp['GEO'].unique())}")
non_std2 = [c for c in emp.columns if c not in ['REF_DATE','GEO','DGUID','UOM','UOM_ID','SCALAR_FACTOR','SCALAR_ID','VECTOR','COORDINATE','VALUE','STATUS','SYMBOL','TERMINATED','DECIMALS']]
print(f"Dim columns: {non_std2}")
for c in non_std2:
    print(f"  {c}: {sorted(emp[c].unique())}")
latest2 = emp[emp['REF_DATE'] == emp['REF_DATE'].max()]
print(f"\nLatest year ({emp['REF_DATE'].max()}):")
for _, r in latest2.head(15).iterrows():
    dims = " | ".join(str(r.get(c, "")) for c in non_std2)
    print(f"  {r['GEO']:<25} | {dims:<60} | {r['VALUE']}")

# === Try to compute TFW dependency ratio per province ===
print("\n\n=== TFW Dependency Analysis ===")
# Get total employees by province (latest year, total category if possible)
latest_emp = emp[emp['REF_DATE'] == emp['REF_DATE'].max()].copy()
latest_tfw = tfw[tfw['REF_DATE'] == tfw['REF_DATE'].max()].copy()

# Show all unique dimension combos for Ontario as an example
print("\nOntario TFW rows:")
ont_tfw = latest_tfw[latest_tfw['GEO'].str.contains('Ontario', case=False)]
for _, r in ont_tfw.iterrows():
    dims = " | ".join(str(r.get(c, "")) for c in non_std)
    print(f"  {dims}: {r['VALUE']}")

print("\nOntario Employment rows:")
ont_emp = latest2[latest2['GEO'].str.contains('Ontario', case=False)]
for _, r in ont_emp.iterrows():
    dims = " | ".join(str(r.get(c, "")) for c in non_std2)
    print(f"  {dims}: {r['VALUE']}")
