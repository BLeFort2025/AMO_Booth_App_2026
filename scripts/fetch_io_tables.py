from __future__ import annotations

from typing import Iterable
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_statcan import fetch_table, persist_if_changed


IO_TABLE_IDS: list[str] = [
    "36-10-0594-01",  # Canada IO multipliers detail
    "36-10-0595-01",  # PT IO multipliers detail
    "36-10-0478-01",  # Supply-use DETAIL PT (Was Summary 0438)
]


def run(table_ids: Iterable[str] = IO_TABLE_IDS) -> None:
    changed: list[str] = []
    failed: list[str] = []

    for tid in table_ids:
        try:
            df, content_hash = fetch_table(tid)
            if persist_if_changed(tid, df, content_hash):
                changed.append(tid)
        except Exception as e:
            print(f"[ERROR] Failed to fetch/persist {tid}: {e}")
            failed.append(tid)

    print(f"Updated: {changed}" if changed else "No changes.")
    if failed:
        print(f"Failed: {failed}")


if __name__ == "__main__":
    run()