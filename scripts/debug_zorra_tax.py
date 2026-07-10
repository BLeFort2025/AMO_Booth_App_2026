import pandas as pd
df = pd.read_csv("data/derived/fir_indicators.csv")
z = df[(df["municipality_name"].str.contains("Zorra Tp", na=False)) & (df["year"] == 2018)]
r = z.iloc[0]
lt = r["farmland_lt_taxes"]
ut = r["farmland_ut_taxes"]
edu = r["farmland_edu_taxes"]
total = r["farmland_total_taxes"]
muni = r["farmland_muni_taxes"]
print(f"=== Zorra Tp 2018 — Our CSV ===")
print(f"farmland_total_taxes (S26A Col 3): {total:>15,.0f}")
print(f"farmland_lt_taxes    (S26A Col 4): {lt:>15,.0f}")
print(f"farmland_ut_taxes    (S26A Col 5): {ut:>15,.0f}")
print(f"farmland_edu_taxes   (S26A Col 6): {edu:>15,.0f}")
print(f"LT+UT+Edu manual sum:             {lt+ut+edu:>15,.0f}")
print(f"farmland_muni_taxes  (LT+UT):      {muni:>15,.0f}")
print()
print(f"User sees on S26 summary:           3,762,247")
print(f"Our farmland_total_taxes:          {total:>15,.0f}")
print(f"Difference:                        {3762247-total:>15,.0f}")
print()
print(f"Does our LT+UT+Edu = S26 summary?  {abs(lt+ut+edu - 3762247) < 1}")
