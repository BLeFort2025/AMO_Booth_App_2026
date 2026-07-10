"""Check the actual CSV output for potential S22A issues."""
import pandas as pd

df = pd.read_csv("data/derived/fir_indicators.csv")

# Check all municipalities for tax_ratio > 1 (should ALWAYS be <= 1 for farmland)
bad = df[df["farmland_tax_ratio"] > 1.0]
if not bad.empty:
    print(f"ERROR: {len(bad)} rows have farmland_tax_ratio > 1.0!")
    print(bad[["municipality_name", "year", "farmland_tax_ratio"]].head(20).to_string())
else:
    print("OK: All farmland_tax_ratio values <= 1.0")

# Check Zorra specifically
z = df[df["municipality_name"].str.contains("Zorra", na=False)].sort_values("year")
print(f"\nZorra records: {len(z)}")
for _, r in z.iterrows():
    name = r["municipality_name"]
    yr = int(r["year"])
    ratio = r.get("farmland_tax_ratio")
    exp = r.get("total_expenses")
    ratio_s = f"{ratio:.4f}" if pd.notna(ratio) else "NULL"
    exp_s = f"${exp:,.0f}" if pd.notna(exp) else "NULL"
    print(f"  {name:35s}  yr={yr}  ratio={ratio_s:>8s}  expenses={exp_s}")

# Check for multi_res_tax_ratio column
if "multi_res_tax_ratio" in df.columns:
    z_mr = z[["municipality_name", "year", "multi_res_tax_ratio"]].dropna(subset=["multi_res_tax_ratio"])
    if not z_mr.empty:
        print(f"\nZorra multi_res_tax_ratio values:")
        for _, r in z_mr.iterrows():
            print(f"  {r['municipality_name']:35s}  yr={int(r['year'])}  mr_ratio={r['multi_res_tax_ratio']:.4f}")
