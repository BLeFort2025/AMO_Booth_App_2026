"""Extract historical Census trend data for Wellington & Perth."""
import pandas as pd
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = os.path.join(BASE, "data", "latest")

ceag = pd.read_csv(os.path.join(LATEST, "ontario_county_ceag.csv"))

for county_name in ['perth', 'wellington']:
    print(f"\n{'='*80}")
    print(f"  {county_name.upper()} - HISTORICAL CENSUS TREND")
    print(f"{'='*80}")
    
    county = ceag[ceag['GEO'] == county_name].sort_values('YEAR')
    
    key_metrics = [
        ('Total farm area - Farms reporting', 'Total farms'),
        ('Total farm area - Acres', 'Total farm area (acres)'),
        ('Land in crops (ecluding Christmas tree area) - Acres', 'Land in crops (acres)'),
        ('Total number of farm operators', 'Total operators'),
        ('Average age of farm operators - Years', 'Average age'),
        ('Age: Under 35 years - Number of farm operators', 'Operators under 35'),
        ('Age: 55 years and over - Number of farm operators', 'Operators 55+'),
        ('Gender: Female - Number of farm operators', 'Female operators'),
        ('Gender: Male - Number of farm operators', 'Male operators'),
        ('Total farm capital - Market value $', 'Total farm capital ($)'),
        ('Total value of land and buildings - Market value $', 'Land & buildings ($)'),
        ('Value of all farm machinery and equipment - Market value $', 'Machinery ($)'),
        ('Value of livestock and poultry - Market value $', 'Livestock ($)'),
        ('Total gross farm receipts (ecluding sales of forest products) in the calendar year prior to the census or for the last complete accounting (fiscal) year prior to the census - Amount $', 'Gross farm receipts ($)'),
        ('Total farm business operating epenses in the calendar year prior to the census or for the last complete accounting (fiscal) year prior to the census - Amount $', 'Operating expenses ($)'),
        ('Total cattle and calves - Number', 'Total cattle'),
        ('Dairy cows - Number', 'Dairy cows'),
        ('Beef cows - Number', 'Beef cows'),
        ('Total pigs - Number', 'Total pigs'),
        ('Total hens and chickens - Number', 'Hens & chickens'),
        ('Total sheep and lambs - Number', 'Sheep & lambs'),
        ('Turkeys - Number', 'Turkeys'),
        ('Total corn - Acres', 'Corn (acres)'),
        ('Soybeans - Acres', 'Soybeans (acres)'),
        ('Wheat (total) - Acres', 'Wheat (acres)'),
        ('Alfalfa and alfalfa mitures - Acres', 'Alfalfa (acres)'),
        ('Employees with paid work in the calendar year prior to the census - Number', 'Paid employees'),
        ('Farm operating arrangement: Sole proprietorship - Farms reporting', 'Sole proprietorship'),
        ('Farm operating arrangement: Partnership - Farms reporting', 'Partnership'),
        ('Farm operating arrangement: Family corporation - Farms reporting', 'Family corporation'),
        ('Cattle ranching and farming - Farm Reporting', 'Cattle farms'),
        ('Dairy cattle and milk production - Farm Reporting', 'Dairy farms'),
        ('Oilseed and grain farming - Farm Reporting', 'Grain farms'),
        ('Hog and pig farming - Farm Reporting', 'Hog farms'),
        ('Poultry and egg production - Farm Reporting', 'Poultry farms'),
    ]
    
    years = sorted(county['YEAR'].unique())
    print(f"  Census years: {years}")
    print()
    
    for col, label in key_metrics:
        values = []
        for yr in years:
            row = county[county['YEAR'] == yr]
            if len(row) > 0 and col in row.columns:
                val = row.iloc[0][col]
                if pd.notna(val):
                    if '$' in label:
                        values.append(f"${val:,.0f}")
                    elif isinstance(val, float) and val == int(val):
                        values.append(f"{int(val):,}")
                    elif isinstance(val, float):
                        values.append(f"{val:.1f}")
                    else:
                        values.append(f"{val:,}")
                else:
                    values.append("N/A")
            else:
                values.append("N/A")
        print(f"  {label:30s}  |  {'  |  '.join(f'{yr}: {v}' for yr, v in zip(years, values))}")

# Ontario totals for context
print(f"\n{'='*80}")
print(f"  ONTARIO PROVINCIAL TOTALS")
print(f"{'='*80}")
ont = ceag[ceag['GEO'] == 'ontario'].sort_values('YEAR')
years = sorted(ont['YEAR'].unique())
for col, label in [
    ('Total farm area - Farms reporting', 'Total farms'),
    ('Total farm area - Acres', 'Total farm area (acres)'),
    ('Total number of farm operators', 'Total operators'),
    ('Total farm capital - Market value $', 'Total farm capital ($)'),
]:
    values = []
    for yr in years:
        row = ont[ont['YEAR'] == yr]
        if len(row) > 0 and col in row.columns:
            val = row.iloc[0][col]
            if pd.notna(val):
                if '$' in label:
                    values.append(f"${val:,.0f}")
                else:
                    values.append(f"{int(val):,}")
            else:
                values.append("N/A")
        else:
            values.append("N/A")
    print(f"  {label:30s}  |  {'  |  '.join(f'{yr}: {v}' for yr, v in zip(years, values))}")
