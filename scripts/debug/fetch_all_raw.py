import requests, zipfile, io
from pathlib import Path
import shutil

# Config
DATA_DIR = Path("data/latest")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Map Table ID -> Expected Filename
TABLES = {
    "36-10-0594-01": "3610059401.csv", # National Multipliers
    "36-10-0595-01": "3610059501.csv", # Provincial Multipliers
    "36-10-0478-01": "3610047801.csv", # Detailed History
}

def download_and_save(table_id, target_filename):
    # Logic: ID "36-10-0594-01" -> PID "36100594" -> URL ".../36100594-eng.zip"
    pid = table_id.replace("-", "")[:8]
    url = f"https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip"
    
    print(f"⬇️  Downloading {table_id} from {url}...")
    try:
        r = requests.get(url)
        r.raise_for_status()
        
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            # The CSV inside is usually just the PID.csv (e.g. 36100594.csv)
            # But sometimes it varies, so we find the largest CSV
            csv_files = [f for f in z.namelist() if f.endswith(".csv") and "meta" not in f.lower()]
            source_csv = csv_files[0]
            
            target_path = DATA_DIR / target_filename
            print(f"   Extracting {source_csv} -> {target_path}...")
            
            with z.open(source_csv) as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
                
        print("   ✅ Success.")
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")

if __name__ == "__main__":
    print("--- FETCHING RAW DATA FOR PIPELINE ---")
    for tid, fname in TABLES.items():
        download_and_save(tid, fname)
    print("\nDone. You can now run the transform script.")