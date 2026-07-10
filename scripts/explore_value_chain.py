"""Extract and analyze Perth & Wellington value chain data + comparative industry context."""
import pandas as pd

df = pd.read_excel('data/latest/omafa_agrifood_value_chain.xlsx', sheet_name='county_En', header=None)

# Parse GDP section (rows 2-57)
years = [int(x) for x in df.iloc[2, 1:14].values]
gdp_data = {}
for i in range(3, 58):
    county = str(df.iloc[i, 0]).strip()
    vals = df.iloc[i, 1:14].values
    gdp_data[county] = dict(zip(years, vals))

# Parse Employment section (rows 61-116)
emp_years = [int(x) for x in df.iloc[61, 1:14].values]
emp_data = {}
for i in range(62, 117):
    county = str(df.iloc[i, 0]).strip()
    vals = df.iloc[i, 1:14].values
    emp_data[county] = dict(zip(emp_years, vals))

print("="*80)
print("PERTH COUNTY - AGRI-FOOD VALUE CHAIN")
print("="*80)

print("\nGDP (millions of chained 2017 dollars):")
for yr in years:
    print(f"  {yr}: ${gdp_data['Perth County'][yr]:,.1f}M")

print(f"\n  2012-2024 growth: {(gdp_data['Perth County'][2024]/gdp_data['Perth County'][2012]-1)*100:.1f}%")
print(f"  CAGR: {((gdp_data['Perth County'][2024]/gdp_data['Perth County'][2012])**(1/12)-1)*100:.1f}%")

print(f"\n  Provincial GDP: ${gdp_data['PROVINCE'][2024]:,.1f}M")
print(f"  Perth share: {gdp_data['Perth County'][2024]/gdp_data['PROVINCE'][2024]*100:.1f}%")

print("\nEmployment (jobs):")
for yr in emp_years:
    print(f"  {yr}: {emp_data['Perth County'][yr]:,.0f}")

print(f"\n  Provincial employment: {emp_data['PROVINCE'][2023]:,.0f}")
print(f"  Perth share: {emp_data['Perth County'][2023]/emp_data['PROVINCE'][2023]*100:.1f}%")

print("\n" + "="*80)
print("WELLINGTON COUNTY - AGRI-FOOD VALUE CHAIN")
print("="*80)

print("\nGDP (millions of chained 2017 dollars):")
for yr in years:
    print(f"  {yr}: ${gdp_data['Wellington County'][yr]:,.1f}M")

print(f"\n  2012-2024 growth: {(gdp_data['Wellington County'][2024]/gdp_data['Wellington County'][2012]-1)*100:.1f}%")
print(f"  CAGR: {((gdp_data['Wellington County'][2024]/gdp_data['Wellington County'][2012])**(1/12)-1)*100:.1f}%")

print(f"\n  Provincial GDP: ${gdp_data['PROVINCE'][2024]:,.1f}M")
print(f"  Wellington share: {gdp_data['Wellington County'][2024]/gdp_data['PROVINCE'][2024]*100:.1f}%")

print("\nEmployment (jobs):")
for yr in emp_years:
    print(f"  {yr}: {emp_data['Wellington County'][yr]:,.0f}")

print(f"\n  Provincial employment: {emp_data['PROVINCE'][2023]:,.0f}")
print(f"  Wellington share: {emp_data['Wellington County'][2023]/emp_data['PROVINCE'][2023]*100:.1f}%")

# Regional rankings
print("\n" + "="*80)
print("COUNTY RANKINGS (2024 GDP)")
print("="*80)
counties_only = {k: v for k, v in gdp_data.items() if 'Region' not in k and 'PROVINCE' not in k and 'Imports' not in k}
ranked = sorted(counties_only.items(), key=lambda x: -x[1][2024])
for i, (county, data) in enumerate(ranked[:15]):
    marker = " <---" if county in ['Perth County', 'Wellington County'] else ""
    print(f"  #{i+1:2d}: {county:45s} ${data[2024]:,.1f}M{marker}")

print("\n" + "="*80)
print("COUNTY RANKINGS (2023 Employment)")
print("="*80)
emp_counties = {k: v for k, v in emp_data.items() if 'Region' not in k and 'PROVINCE' not in k and 'Imports' not in k}
emp_ranked = sorted(emp_counties.items(), key=lambda x: -x[1][2023])
for i, (county, data) in enumerate(emp_ranked[:15]):
    marker = " <---" if county in ['Perth County', 'Wellington County'] else ""
    print(f"  #{i+1:2d}: {county:45s} {data[2023]:,.0f} jobs{marker}")

# Note about employment 2024 column - check if it matches 2023
print("\n--- Employment data note ---")
print(f"Perth 2023 emp col = {emp_data['Perth County'][2023]:,.0f}")
print(f"Wellington 2023 emp col = {emp_data['Wellington County'][2023]:,.0f}")
# The 2024 column in employment might actually be 2023 (note the header had 2023 twice)
print(f"Employment years header: {emp_years}")
