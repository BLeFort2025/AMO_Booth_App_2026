import pandas as pd
from pathlib import Path
import yaml
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def get_active_csvs():
    tables_yaml_path = Path("config/tables.yml")
    if not tables_yaml_path.exists():
        logger.warning("config/tables.yml not found.")
        return set()
    
    with open(tables_yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    active_csvs = set()
    for table in config.get("tables", []):
        if table.get("active", True):
            csv_name = table.get("csv", f"{table['id']}.csv")
            active_csvs.add(csv_name)
    return active_csvs

def convert_large_csvs(data_dir: Path, size_limit_mb: int = 30):
    active_csvs = get_active_csvs()
    
    csv_files = list(data_dir.rglob("*.csv"))
    for csv_path in csv_files:
        if csv_path.name not in active_csvs:
            # We only convert active CSVs to save space and time.
            continue
            
        size_mb = csv_path.stat().st_size / (1024 * 1024)
        if size_mb > size_limit_mb:
            parquet_path = csv_path.with_suffix(".parquet")
            if not parquet_path.exists() or parquet_path.stat().st_mtime < csv_path.stat().st_mtime:
                logger.info(f"Converting {csv_path.name} ({size_mb:.1f} MB) to Parquet...")
                try:
                    # Some tables might have mixed types, use low_memory=False to let pandas figure it out
                    df = pd.read_csv(csv_path, low_memory=False)
                    # Convert all columns to string if there are mixed type issues, or let pyarrow handle it
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            df[col] = df[col].astype(str)
                    df.to_parquet(parquet_path, engine="pyarrow", compression="snappy")
                    logger.info(f"  -> Saved {parquet_path.name} ({parquet_path.stat().st_size / (1024 * 1024):.1f} MB)")
                except Exception as e:
                    logger.error(f"  -> Failed to convert {csv_path.name}: {e}")
            else:
                logger.info(f"Parquet already exists and is up to date: {parquet_path.name}")

if __name__ == "__main__":
    latest_dir = Path("data/latest")
    if latest_dir.exists():
        convert_large_csvs(latest_dir)
    else:
        logger.error(f"Data directory {latest_dir} not found.")
