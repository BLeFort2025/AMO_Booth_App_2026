import pandas as pd

# Load data
df = pd.read_csv('data/latest/io_multipliers_standardized.csv.gz')

# Get the code for the Greenhouse industry
greenhouse = df[df['industry_name'].str.contains('Greenhouse', case=False, na=False)]
print(greenhouse[['industry_code', 'industry_name']].drop_duplicates())