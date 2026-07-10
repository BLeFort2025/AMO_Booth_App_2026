import os
import glob
import pandas as pd
import numpy as np

def main():
    profile_dir = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\County Profiles"
    files = glob.glob(os.path.join(profile_dir, "*.xlsx"))
    
    all_records = []
    
    for f in files:
        try:
            xlsx = pd.ExcelFile(f)
            # Find the census sheet
            sheet_name = [s for s in xlsx.sheet_names if "census over time" in s.lower()]
            if not sheet_name:
                continue
            sheet = sheet_name[0]
            
            df = pd.read_excel(xlsx, sheet_name=sheet, header=None)
            
            # Find anchor row
            anchor_idx = None
            for i in range(min(15, len(df))):
                if str(df.iloc[i, 0]).strip() == "Total number of farms":
                    anchor_idx = i
                    break
            
            if anchor_idx is None:
                continue
                
            geo_row = df.iloc[anchor_idx - 2]
            year_row = df.iloc[anchor_idx - 1]
            
            # Find area row
            area_idx = None
            for i in range(len(df)):
                if str(df.iloc[i, 0]).strip() == "Total farm area - Acres":
                    area_idx = i
                    break
                    
            if area_idx is None:
                continue
                
            area_row = df.iloc[area_idx]
            
            current_geo = None
            for col in range(1, len(df.columns)):
                g = geo_row.iloc[col]
                if pd.notnull(g) and str(g).strip() != "":
                    current_geo = str(g).strip()
                
                y = year_row.iloc[col]
                val = area_row.iloc[col]
                
                if current_geo and pd.notnull(y):
                    try:
                        yr = int(float(y))
                        if yr in [2006, 2011, 2016, 2021]:
                            all_records.append({
                                "municipality_omafra": current_geo,
                                "year": yr,
                                "census_acres": float(val) if pd.notnull(val) else np.nan
                            })
                    except ValueError:
                        pass
        except Exception as e:
            print(f"Error processing {f}: {e}")
            
    # Combine and drop duplicates (like Ontario appearing in every file)
    raw_df = pd.DataFrame(all_records).drop_duplicates(subset=["municipality_omafra", "year"])
    
    # Pivot to make years columns, so we can interpolate
    pivoted = raw_df.pivot(index="municipality_omafra", columns="year", values="census_acres")
    
    # We want years 2010 to 2024
    interpolated_records = []
    for index, row in pivoted.iterrows():
        muni = index
        acres_2006 = row.get(2006, np.nan)
        acres_2011 = row.get(2011, np.nan)
        acres_2016 = row.get(2016, np.nan)
        acres_2021 = row.get(2021, np.nan)
        
        for yr in range(2010, 2025):
            acres = np.nan
            if yr == 2010:
                acres = acres_2011
            elif yr == 2011:
                acres = acres_2011
            elif 2011 < yr < 2016:
                if pd.notnull(acres_2011) and pd.notnull(acres_2016):
                    fraction = (yr - 2011) / 5.0
                    acres = acres_2011 + fraction * (acres_2016 - acres_2011)
            elif yr == 2016:
                acres = acres_2016
            elif 2016 < yr < 2021:
                if pd.notnull(acres_2016) and pd.notnull(acres_2021):
                    fraction = (yr - 2016) / 5.0
                    acres = acres_2016 + fraction * (acres_2021 - acres_2016)
            elif yr >= 2021:
                acres = acres_2021
                
            interpolated_records.append({
                "municipality_omafra": muni,
                "year": yr,
                "census_acres": acres
            })
            
    final_df = pd.DataFrame(interpolated_records)
    
    # Some basic cleaning of municipality_omafra to help with matching
    def clean_name(n):
        n = n.replace(" Township", " Tp").replace(" Municipality", " Mun").replace(" County", " Co")
        n = n.replace(" Town", " Twn").replace(" City", " Cty")
        return n
        
    final_df["municipality_clean"] = final_df["municipality_omafra"].apply(clean_name)
    
    os.makedirs(r"data\derived", exist_ok=True)
    out_path = r"data\derived\census_farm_metrics.csv"
    final_df.to_csv(out_path, index=False)
    print(f"Successfully processed {len(final_df)} records. Saved to {out_path}")

if __name__ == "__main__":
    main()
