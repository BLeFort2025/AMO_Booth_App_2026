"""Check provincial rankings for key livestock categories."""
import pandas as pd
ceag = pd.read_csv(r'data/latest/ontario_county_ceag.csv')
c2021 = ceag[ceag['YEAR'] == 2021]

# Top hog counties
print('=== TOP HOG COUNTIES (2021 Census, Total pigs) ===')
pig_col = 'Total pigs - Number'
pigs = c2021[['GEO', pig_col]].dropna().sort_values(pig_col, ascending=False).head(10)
for _, r in pigs.iterrows():
    print(f'  {r["GEO"]:30s} {r[pig_col]:>10,.0f}')

# Top dairy cow counties
print()
print('=== TOP DAIRY COW COUNTIES (2021 Census) ===')
dairy_col = 'Dairy cows - Number'
dairy = c2021[['GEO', dairy_col]].dropna().sort_values(dairy_col, ascending=False).head(10)
for _, r in dairy.iterrows():
    print(f'  {r["GEO"]:30s} {r[dairy_col]:>10,.0f}')

# Top cattle counties
print()
print('=== TOP CATTLE & CALVES COUNTIES (2021 Census) ===')
cattle_col = 'Total cattle and calves - Number'
cattle = c2021[['GEO', cattle_col]].dropna().sort_values(cattle_col, ascending=False).head(10)
for _, r in cattle.iterrows():
    print(f'  {r["GEO"]:30s} {r[cattle_col]:>10,.0f}')

# Top poultry counties
print()
print('=== TOP POULTRY COUNTIES (2021 Census, Hens & chickens) ===')
poultry_col = 'Total hens and chickens - Number'
poultry = c2021[['GEO', poultry_col]].dropna().sort_values(poultry_col, ascending=False).head(10)
for _, r in poultry.iterrows():
    print(f'  {r["GEO"]:30s} {r[poultry_col]:>10,.0f}')
