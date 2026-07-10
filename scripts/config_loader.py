"""Shared helpers for loading table configuration and common data paths."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import yaml

TABLES_YML = Path("config/tables.yml")
DATA_LATEST = Path("data/latest")


def load_tables_config() -> Mapping:
    """Load the raw tables.yml configuration as a dictionary."""
    if not TABLES_YML.exists():
        return {"tables": []}
    return yaml.safe_load(TABLES_YML.read_text())


def _normalize_tables(tables: Iterable[Mapping]) -> list[dict]:
    normalized: list[dict] = []
    for table in tables:
        item = dict(table)
        # Optional: source of the dataset. Defaults to "statcan".
        # For OMAFRA tables, set source: "omafra" and provide a download_url.
        item.setdefault("source", "statcan")
        normalized.append(item)
    return normalized


def load_tables(active_only: bool = False) -> list[dict]:
    """Load table metadata with defaults applied.

    Args:
        active_only: If True, return only entries where ``active`` is truthy.
    """
    cfg = load_tables_config()
    if isinstance(cfg, Mapping):
        raw_tables = cfg.get("tables", cfg)
    else:
        raw_tables = cfg

    if isinstance(raw_tables, Mapping):
        raw_tables = [raw_tables]

    normalized = _normalize_tables(raw_tables)
    if active_only:
        normalized = [t for t in normalized if t.get("active", True)]

    return normalized


def get_raw_data_dir() -> Path:
    """Return the directory used for raw/latest data files."""
    return DATA_LATEST
