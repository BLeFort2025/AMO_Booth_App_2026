"""Check who the two Zorra records are."""
import pandas as pd
df = pd.read_csv("data/derived/fir_indicators.csv")
z = df[df["municipality_name"].str.contains("Zorra", na=False)].sort_values(["year", "municipality_name"])
for _, r in z.iterrows():
    name = r["municipality_name"]
    yr = int(r["year"])
    fir = r["fir_code"]
    sgc = r.get("sgc_code", "?")
    exp = r.get("total_expenses")
    fc = r.get("farmland_cva")
    exp_s = f"${exp:,.0f}" if pd.notna(exp) else "NULL"
    fc_s = f"${fc:,.0f}" if pd.notna(fc) else "NULL"
    print(f"  {name:35s}  yr={yr}  fir={fir}  sgc={sgc}  expenses={exp_s:>15s}  farm_cva={fc_s}")
