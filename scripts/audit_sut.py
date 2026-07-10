"""Write audit results to JSON for reliable reading"""
import pandas as pd
import json

df = pd.read_csv("data/latest/3610047801.csv", nrows=100000, low_memory=False)

result = {
    "columns": list(df.columns),
    "column_uniques": {}
}

for col in df.columns:
    uniques = [str(x) for x in df[col].dropna().unique()[:50]]
    result["column_uniques"][col] = uniques

# Search for Output/GDP keywords
result["output_found_in"] = []
result["gdp_found_in"] = []

for col in df.columns:
    if df[col].astype(str).str.contains("output", case=False, na=False).any():
        result["output_found_in"].append(col)
    if df[col].astype(str).str.contains("gross domestic|gdp", case=False, na=False).any():
        result["gdp_found_in"].append(col)

with open("data/audit_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("Done. Check data/audit_result.json")
