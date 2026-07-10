import requests
import zipfile
import io
import os
from pathlib import Path

# Config
STATCAN_PID = "36100113"  # Table 36-10-0113-01
DOWNLOAD_URL = f"https://www150.statcan.gc.ca/n1/tbl/csv/{STATCAN_PID}-eng.zip"
DEST_DIR = Path(__file__).parent.parent / "data" / "latest"
DEST_FILE = DEST_DIR / "36-10-0113-01.csv"

def main():
    print(f"Downloading Table {STATCAN_PID} from Statistics Canada...")
    
    # 1. Download the ZIP file into memory
    response = requests.get(DOWNLOAD_URL)
    response.raise_for_status()
    
    # 2. Extract and Save
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        # The zip usually contains a file named "36100113.csv"
        csv_name = f"{STATCAN_PID}.csv"
        if csv_name in z.namelist():
            print(f"Extracting {csv_name}...")
            # Read the CSV content from the zip
            csv_content = z.read(csv_name)
            
            # Ensure directory exists
            DEST_DIR.mkdir(parents=True, exist_ok=True)
            
            # Write to the destination with the correct name
            with open(DEST_FILE, "wb") as f:
                f.write(csv_content)
            
            print(f"✔ Success! Saved to: {DEST_FILE}")
        else:
            print(f"❌ Error: Could not find {csv_name} in the downloaded zip.")
            print(f"Files found: {z.namelist()}")

if __name__ == "__main__":
    main()