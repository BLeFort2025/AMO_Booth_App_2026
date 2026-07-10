"""Verify all economic impact data points in the report."""
import pandas as pd

df = pd.read_excel('data/latest/omafa_agrifood_value_chain.xlsx', sheet_name='county_En', header=None)

# Parse GDP data (rows 2-57)
years = [int(x) for x in df.iloc[2, 1:14].values]
gdp_data = {}
for i in range(3, 58):
    county = str(df.iloc[i, 0]).strip()
    vals = df.iloc[i, 1:14].values
    gdp_data[county] = dict(zip(years, [float(v) for v in vals]))

# Parse Employment (rows 61-116) 
emp_years = [int(x) for x in df.iloc[61, 1:14].values]
emp_data = {}
for i in range(62, 117):
    county = str(df.iloc[i, 0]).strip()
    vals = df.iloc[i, 1:14].values
    emp_data[county] = dict(zip(emp_years, [float(v) for v in vals]))

errors = []
verified = []

def check(label, reported, actual, tol=0.01):
    if abs(reported - actual) <= abs(actual * tol) + 0.5:
        verified.append(f"  OK: {label}: {reported} (actual: {actual:.1f})")
    else:
        errors.append(f"  ERR: {label}: reported={reported}, actual={actual:.1f}, diff={reported-actual:.1f}")

# PERTH COUNTY
print("=== PERTH COUNTY ECONOMIC DATA ===")
p = gdp_data['Perth County']
check("Perth GDP 2024", 2983.8, p[2024])
check("Perth GDP 2012", 2204.6, p[2012])
check("Perth GDP 2014", 2439.8, p[2014])
check("Perth GDP 2016", 2522.9, p[2016])
check("Perth GDP 2017", 2666.0, p[2017])
check("Perth GDP 2019", 2798.4, p[2019])
check("Perth GDP 2020", 2593.1, p[2020])
check("Perth GDP 2022", 2907.3, p[2022])
check("Perth GDP 2023", 2970.2, p[2023])

# Growth calc
growth = (p[2024]/p[2012] - 1) * 100
check("Perth GDP growth 35.3%", 35.3, growth, tol=0.02)
cagr = ((p[2024]/p[2012])**(1/12) - 1) * 100
check("Perth CAGR 2.6%", 2.6, cagr, tol=0.05)

# Provincial share
prov_gdp = gdp_data['PROVINCE'][2024]
share = p[2024] / prov_gdp * 100
check("Perth provincial share 5.8%", 5.8, share, tol=0.05)
check("Provincial GDP $51,430.2M", 51430.2, prov_gdp)

# Employment
pe = emp_data['Perth County']
check("Perth emp 2012", 39957, pe[2012])
check("Perth emp 2023", 47487, pe[2023])

# Rankings
counties = {k: v for k, v in gdp_data.items() if 'Region' not in k and 'PROVINCE' not in k and 'Imports' not in k}
ranked = sorted(counties.items(), key=lambda x: -x[1][2024])
perth_rank = [c[0] for c in ranked].index('Perth County') + 1
check("Perth GDP rank #3", 3, perth_rank)

# 2020 pandemic dip
p_dip = (p[2020] - p[2019]) / p[2019] * 100
print(f"  INFO: Perth 2020 dip = {p_dip:.1f}% (report says -7.3%)")

# WELLINGTON COUNTY
print("\n=== WELLINGTON COUNTY ECONOMIC DATA ===")
w = gdp_data['Wellington County']
check("Wellington GDP 2024", 2692.1, w[2024])
check("Wellington GDP 2012", 2037.0, w[2012])
check("Wellington GDP 2020", 2225.0, w[2020])

w_growth = (w[2024]/w[2012] - 1) * 100
check("Wellington GDP growth 32.2%", 32.2, w_growth, tol=0.02)
w_cagr = ((w[2024]/w[2012])**(1/12) - 1) * 100
check("Wellington CAGR 2.4%", 2.4, w_cagr, tol=0.05)
w_share = w[2024] / prov_gdp * 100
check("Wellington provincial share 5.2%", 5.2, w_share, tol=0.05)

well_rank = [c[0] for c in ranked].index('Wellington County') + 1
check("Wellington GDP rank #5", 5, well_rank)

we = emp_data['Wellington County']
check("Wellington emp 2023", 42845, we[2023])
w_emp_share = we[2023] / emp_data['PROVINCE'][2023] * 100
check("Wellington emp share 4.9%", 4.9, w_emp_share, tol=0.05)

# Wellington 2020 dip
w_dip = (w[2020] - w[2019]) / w[2019] * 100
print(f"  INFO: Wellington 2020 dip = {w_dip:.1f}% (report says -3.5% ... but was from 2019)")
# Actually: report says "modest 3.5% GDP decline" - check: (2225.0 - 2205.1)/2205.1 = 0.9% INCREASE!
# Wait - 2019 GDP was $2,205.1M, 2020 was $2,225.0M ... that's actually an INCREASE!
# Hmm, let me check vs 2017 peak or 2014 peak
print(f"  CRITICAL: Wellington 2019={w[2019]:.1f}, 2020={w[2020]:.1f} - this is +{(w[2020]/w[2019]-1)*100:.1f}% NOT a 3.5% decline!")
# The pandemic dip comparison should be vs 2019 for Perth too
print(f"  Perth 2019={p[2019]:.1f}, 2020={p[2020]:.1f} = {(p[2020]/p[2019]-1)*100:.1f}%")

# Combined
combined = p[2024] + w[2024]
check("Combined GDP $5,675.9M", 5675.9, combined)
combined_share = combined / prov_gdp * 100
check("Combined share 11.0%", 11.0, combined_share, tol=0.05)
combined_emp = pe[2023] + we[2023]
check("Combined emp 90,332", 90332, combined_emp)

print(f"\nVerified: {len(verified)}, Errors: {len(errors)}")
if errors:
    print("\nERRORS:")
    for e in errors:
        print(e)
