"""
Fetch OMAFRA datasets defined in config/tables.yml (source: omafra)
and download the raw CSV/Excel files to the same raw data directory
pattern used by the StatCan pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Mapping

import requests
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import config_loader
from scripts.http_utils import get_robust_session

logger = logging.getLogger(__name__)


def fetch_omafra_tables(tables: Iterable[Mapping], raw_dir: Path) -> None:
    """
    Iterate over table configs with source == "omafra" and a non-empty
    download_url, download the file, and save it under raw_dir using
    the table's configured csv filename.

    This function must NOT modify any StatCan behaviour.
    """

    for table in tables:
        if table.get("source", "statcan") != "omafra":
            continue
        if not table.get("active", True):
            continue

        table_id = table.get("id", "")
        download_url = table.get("download_url")
        if not download_url:
            logger.warning("Skipping OMAFRA table %s: missing download_url", table_id)
            continue

        csv_name = table.get("csv") or f"{table_id}.csv"
        target_path = raw_dir / csv_name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            session = get_robust_session()
            resp = session.get(download_url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to download OMAFRA table %s from %s: %s", table_id, download_url, exc
            )
            continue

        try:
            target_path.write_bytes(resp.content)
            logger.info("Saved OMAFRA table %s to %s", table_id, target_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write OMAFRA table %s to disk: %s", table_id, exc)
            continue


def run() -> None:
    tables = config_loader.load_tables()
    raw_dir = config_loader.get_raw_data_dir()
    fetch_omafra_tables(tables, raw_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    run()
