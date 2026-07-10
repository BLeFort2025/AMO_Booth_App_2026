import os
import pandas as pd
import requests
import zipfile
import io
from pathlib import Path
import datetime

# Setup directories
DATA_DIR = Path(r"C:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter\data\raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def download_kilian_index():
    print("Downloading Kilian Index (IGREA) from FRED...")
    try:
        # We can use pandas_datareader, or just hit the FRED FRED API/CSV endpoint directly
        # The direct CSV download URL for a FRED series is:
        csv_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IGREA"
        df = pd.read_csv(csv_url)
        output_path = DATA_DIR / "kilian_igrea_index.csv"
        df.to_csv(output_path, index=False)
        print(f"Successfully saved Kilian Index to {output_path}")
    except Exception as e:
        print(f"Error downloading Kilian Index: {e}")

def download_cftc_cot():
    print("Downloading recent CFTC COT data...")
    try:
        # CFTC provides historical data in zip files containing excel/csv files.
        # Let's get the 2024 and 2025 disaggregated futures data
        current_year = datetime.datetime.now().year
        urls = [
            f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{current_year}.zip",
            f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{current_year-1}.zip"
        ]
        
        for url in urls:
            year = url.split('_')[-1].split('.')[0]
            print(f"Fetching {url}")
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    # Extract the text/csv file
                    for filename in z.namelist():
                        z.extract(filename, DATA_DIR)
                        # Rename to be specific
                        extracted_path = DATA_DIR / filename
                        new_path = DATA_DIR / f"cftc_cot_disagg_{year}.txt"
                        if new_path.exists():
                            new_path.unlink()
                        extracted_path.rename(new_path)
                        print(f"Successfully saved COT data to {new_path}")
            else:
                print(f"Failed to fetch {url} - Status Code {response.status_code}")
    except Exception as e:
        print(f"Error downloading CFTC COT data: {e}")

if __name__ == "__main__":
    download_kilian_index()
    download_cftc_cot()
    print("\nData download complete.")
