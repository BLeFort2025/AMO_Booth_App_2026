"""
Lightweight diagnostic to inspect year coverage of pipeline outputs.

Example usage:
    python scripts/debug_year_coverage.py --theme "Demographics, Labour & Technology"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_statcan import ensure_year_column

DATA_LATEST = Path("data/latest")
TABLES_YML = Path("config/tables.yml")


def summarize_years(path: Path) -> Optional[Tuple[int, Optional[int], Optional[int]]]:
    """Return (n_years, min_year, max_year) for the dataset at path.

    If the file is missing or no YEAR values are present, returns None.
    """

    if not path.exists():
        return None

    df = pd.read_csv(path, low_memory=False)
    df = ensure_year_column(df)
    if "YEAR" not in df.columns or df["YEAR"].dropna().empty:
        return (0, None, None)

    years = pd.to_numeric(df["YEAR"], errors="coerce").dropna().astype(int)
    if years.empty:
        return (0, None, None)

    return years.nunique(), int(years.min()), int(years.max())


def format_stats(stats: Optional[Tuple[int, Optional[int], Optional[int]]]) -> str:
    if stats is None:
        return "missing"
    n_years, min_year, max_year = stats
    if n_years == 0:
        return "no_years"
    if min_year is None or max_year is None:
        return f"{n_years} years"
    if min_year == max_year:
        return f"{n_years} year ({min_year})"
    return f"{n_years} years ({min_year}-{max_year})"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect year coverage of pipeline outputs.")
    parser.add_argument(
        "--theme",
        "--section",
        dest="theme",
        help="Optional theme/section filter matching the `theme` field in tables.yml.",
    )
    args = parser.parse_args()

    cfg = yaml.safe_load(TABLES_YML.read_text())
    tables = cfg.get("tables", cfg)

    for table in tables:
        if not table.get("active", True):
            continue
        if args.theme and table.get("theme") != args.theme:
            continue

        table_id = table["id"]
        dataset_id = table.get("dataset_id", table_id)
        csv_name = table.get("csv") or f"{table_id}.csv"

        final_path = DATA_LATEST / csv_name
        raw_path = DATA_LATEST / f"{table_id}.csv"

        final_stats = summarize_years(final_path)
        raw_stats = summarize_years(raw_path) if raw_path != final_path else final_stats

        print(
            f"{dataset_id}\t{table_id}\tfinal={format_stats(final_stats)}\t"
            f"raw={format_stats(raw_stats)}\tfile={csv_name}"
        )


if __name__ == "__main__":
    main()
