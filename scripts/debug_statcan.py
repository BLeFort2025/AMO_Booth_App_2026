import sys
from pathlib import Path
import traceback

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_statcan import fetch_table, ensure_year_column
from scripts.http_utils import get_robust_session

failed_tables = [
    # "32-10-0136-01",  # Skip large table
    "32-10-0051-01",
    "32-10-0078-01",
    "32-10-0157-01",
    "32-10-0163-01",
    "18-10-0004-01",
    "32-10-0237-01",
    "38-10-0241-01",
    "38-10-0246-01",
    "38-10-0249-01",
    "32-10-0130-01",
    "32-10-0126-01",
    "32-10-0216-01",
    "32-10-0218-01",
    "32-10-0379-01",
    "18-10-0281-01",
    "23-10-0271-01",
    "32-10-0103-01",
    "32-10-0236-01",
    "32-10-0381-01"
]

session = get_robust_session()
for tid in failed_tables[:5]:  # Test first 5 to see
    try:
        print(f"Testing {tid}...")
        df, h = fetch_table(tid, session)
        df = ensure_year_column(df)
        print(f"  Success for {tid}. Rows: {len(df)}")
    except Exception as e:
        print(f"  Failed for {tid}: {type(e).__name__}: {e}")
