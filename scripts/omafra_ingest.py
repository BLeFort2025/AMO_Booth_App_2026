"""Ingestion utilities for OMAFRA commodity price datasets."""
from __future__ import annotations

import argparse
import io
import re
from pathlib import Path
from typing import Iterable, Mapping, Optional

import pandas as pd
import requests


DEFAULT_DOWNLOAD_URL = (
    "https://data.ontario.ca/dataset/a33275b4-5ac4-4347-a39c-62adc2b0d510/resource/"
    "73072c55-4db4-4287-b467-c217798acfa7/download/weeklycornprice_en.xlsx"
)

# TODO: Replace with the official OMAFRA soybean download URL when available.
DEFAULT_SOYBEAN_DOWNLOAD_URL = "https://data.ontario.ca/dataset/TODO-soybean-weekly-price.xlsx"

# TODO: Replace with the official OMAFRA wheat download URL when available.
DEFAULT_WHEAT_DOWNLOAD_URL = "https://data.ontario.ca/dataset/TODO-wheat-weekly-price.xlsx"


class IngestionError(RuntimeError):
    """Raised when ingestion cannot proceed due to missing inputs or parsing issues."""


def _load_workbook(
    *, download_url: str | None, xlsx_path: Optional[Path], context: str
) -> pd.ExcelFile:
    """Load an Excel workbook from a URL or local path."""

    try:
        if xlsx_path is not None:
            return pd.ExcelFile(xlsx_path)

        if download_url:
            response = requests.get(download_url, timeout=30)
            response.raise_for_status()
            return pd.ExcelFile(io.BytesIO(response.content))
    except Exception as exc:  # pragma: no cover - network behavior
        target = xlsx_path if xlsx_path is not None else download_url
        raise IngestionError(
            f"Failed to load {context} workbook from {target}: {exc}"
        ) from exc

    raise IngestionError(f"No download URL or local path provided for {context}.")


def _find_header_row(df: pd.DataFrame) -> int | None:
    """Return the row index that likely contains headers."""

    for idx, row in df.iterrows():
        non_null = [val for val in row.tolist() if pd.notna(val)]
        if len(non_null) < 2:
            continue
        labels = [str(val).strip().lower() for val in non_null]
        if any(re.search(r"week|date|ref", label) for label in labels):
            return idx

    # Fallback to first non-empty row
    non_empty_rows = df.dropna(how="all").index
    if len(non_empty_rows) == 0:
        return None
    return int(non_empty_rows[0])


def _identify_date_column(df: pd.DataFrame) -> str | None:
    """Identify the date column using header hints and parseability."""

    candidate_cols: list[str] = []
    for col in df.columns:
        if isinstance(col, str) and re.search(r"date|week|ending|ref", col, re.IGNORECASE):
            candidate_cols.append(col)
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().sum() >= max(1, len(df) * 0.2):
            candidate_cols.append(col)

    if not candidate_cols:
        return None

    # Prefer string-labelled candidates first
    string_candidates = [c for c in candidate_cols if isinstance(c, str)]
    return string_candidates[0] if string_candidates else candidate_cols[0]


def _identify_price_columns(
    df: pd.DataFrame,
    date_col: str | None = None,
    *,
    min_numeric_fraction: float = 0.0,
    preferred_keywords: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[str]:
    """Identify price columns, tolerating string-typed numeric data."""

    keywords = tuple(
        preferred_keywords
        if preferred_keywords is not None
        else ("price", "corn", "avg", "average", "$", "c$/t", "tonne")
    )
    candidates: list[tuple[float, str]] = []
    fallback_cols: list[str] = []

    for col in df.columns:
        normalized = str(col).strip().lower() if isinstance(col, str) else ""

        if normalized.startswith("unnamed"):
            continue

        if col in {"DATE", "YEAR"} or normalized in {"year", "week", "date"}:
            continue

        if date_col is not None and col == date_col:
            continue

        numeric = pd.to_numeric(df[col], errors="coerce")
        frac = numeric.notna().mean()

        if frac < min_numeric_fraction:
            continue

        fallback_cols.append(col)

        name = str(col).lower() if isinstance(col, str) else ""
        score = frac
        if any(kw in name for kw in keywords):
            score += 0.5

        candidates.append((score, col))

    if not candidates:
        return fallback_cols[: (limit or None)]

    candidates.sort(key=lambda item: item[0], reverse=True)
    ranked = [c for _, c in candidates]
    return ranked[:limit] if limit else ranked


def _extract_unit(price_columns: Iterable[str]) -> str:
    """Attempt to extract a unit from column names."""

    for col in price_columns:
        if not isinstance(col, str):
            continue
        match = re.search(r"\(([^)]+)\)", col)
        if match:
            return match.group(1).strip()
    return "$/tonne"


def _normalize_weekly_price_workbook(
    *, xls: pd.ExcelFile, sheet_name: str, context: str
) -> pd.DataFrame:
    """Normalize a workbook sheet with Year/Week price data using best-effort detection."""

    try:
        preview_df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
    except Exception as exc:
        raise IngestionError(f"Failed to preview '{sheet_name}' sheet for {context}") from exc

    header_row = _find_header_row(preview_df)
    if header_row is None:
        raise IngestionError(f"Could not identify header row for {context} sheet '{sheet_name}'.")

    print(f"[INFO] Using sheet '{sheet_name}' for {context}")

    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    price_cols = _identify_price_columns(
        df,
        min_numeric_fraction=0.2,
        preferred_keywords=(
            "price",
            "$",
            "market",
            "/cwt",
            "/100kg",
            "hog",
            "swine",
            "steer",
            "heifer",
            "cattle",
        ),
        limit=3,
    )
    if not price_cols:
        raise IngestionError(
            f"Could not identify any price columns in {context} sheet '{sheet_name}'."
        )

    print(f"[INFO] Selected price columns for {context}: {price_cols}")

    unit = _extract_unit(price_cols)

    return _normalize_weekly_price_sheet(
        xls=xls,
        sheet_name=sheet_name,
        price_cols=price_cols,
        unit=unit,
        geo="Ontario",
        source="OMAFRA",
        header_row=header_row,
    )


def _normalize_weekly_price_sheet(
    *,
    xls: pd.ExcelFile,
    sheet_name: str,
    price_cols: list[str],
    unit: str,
    geo: str = "Ontario",
    source: str = "OMAFRA",
    price_col_labels: Mapping[str, str] | None = None,
    header_row: int = 2,
    rename_columns: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """
    Read ``sheet_name`` from ``xls`` and normalize Year/Week price data.

    Returns a tidy DataFrame with columns: DATE, YEAR, GEO, SERIES, VALUE, UNIT, SOURCE.
    """
    active_header = header_row
    try:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=active_header)
    except Exception as exc:
        raise IngestionError(f"Failed to read '{sheet_name}' sheet from workbook") from exc

    df.columns = [str(c).strip() for c in df.columns]

    if rename_columns:
        df = df.rename(columns=rename_columns)

    def _scan_for_header() -> int | None:
        preview = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=15)
        for idx, row in preview.iterrows():
            values = [str(v).strip().lower() for v in row.tolist() if pd.notna(v)]
            if not values:
                continue
            if any("year" in v for v in values) and any("week" in v for v in values):
                return int(idx)
        return None

    def _identify_year_week_columns(frame: pd.DataFrame) -> tuple[str, str]:
        year_col = next(
            (col for col in frame.columns if str(col).strip().lower() == "year"),
            None,
        )
        week_col = next(
            (col for col in frame.columns if str(col).strip().lower() == "week"),
            None,
        )

        if year_col is None:
            if "Unnamed: 0" in frame.columns:
                year_col = "Unnamed: 0"
            elif len(frame.columns) > 0:
                year_col = frame.columns[0]

        if week_col is None:
            if "Unnamed: 1" in frame.columns:
                week_col = "Unnamed: 1"
            elif len(frame.columns) > 1:
                week_col = frame.columns[1]

        if year_col is None or week_col is None:
            raise IngestionError(
                f"Expected Year/Week columns in '{sheet_name}' sheet but could not find them."
            )

        return str(year_col), str(week_col)

    try:
        year_col, week_col = _identify_year_week_columns(df)
    except IngestionError:
        fallback_header = _scan_for_header()
        if fallback_header is not None and fallback_header != header_row:
            active_header = fallback_header
            df = pd.read_excel(xls, sheet_name=sheet_name, header=active_header)
            df.columns = [str(c).strip() for c in df.columns]
            if rename_columns:
                df = df.rename(columns=rename_columns)
            year_col, week_col = _identify_year_week_columns(df)
        else:
            raise

    print(f"[INFO] Normalizing sheet '{sheet_name}' using header row {active_header}")

    df = df.rename(columns={year_col: "Year", week_col: "Week"})
    try:
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
        df["Week"] = pd.to_numeric(df["Week"], errors="coerce")
        df = df.dropna(subset=["Year", "Week"]).copy()
        df["Year"] = df["Year"].astype(int)
        df["Week"] = df["Week"].astype(int)
    except Exception as exc:
        raise IngestionError("Failed to convert Year/Week columns to integers") from exc

    print(f"[INFO] Detected Year column '{year_col}', Week column '{week_col}' in sheet '{sheet_name}'")

    df["DATE"] = pd.to_datetime(
        df["Year"].astype(str) + "-" + df["Week"].astype(str) + "-1",
        format="%Y-%W-%w",
        errors="coerce",
    )
    df = df.dropna(subset=["DATE"]).copy()
    df["YEAR"] = df["Year"].astype(int)

    missing = [c for c in price_cols if c not in df.columns]
    if missing:
        raise IngestionError(
            f"Expected price columns {missing!r} not found in '{sheet_name}' sheet."
        )

    print(f"[INFO] Normalizing price columns from sheet '{sheet_name}': {price_cols}")

    if price_col_labels:
        df = df.rename(columns=price_col_labels)
        price_cols = [price_col_labels.get(c, c) for c in price_cols]

    long_df = df.melt(
        id_vars=["DATE", "YEAR"],
        value_vars=price_cols,
        var_name="SERIES",
        value_name="VALUE",
    )

    long_df["VALUE"] = (
        long_df["VALUE"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
    )
    long_df["VALUE"] = pd.to_numeric(long_df["VALUE"], errors="coerce")
    long_df = long_df.dropna(subset=["VALUE"]).copy()

    long_df["GEO"] = geo
    long_df["UNIT"] = unit
    long_df["SOURCE"] = source

    long_df = long_df.sort_values(["SERIES", "DATE"]).reset_index(drop=True)

    return long_df


def _write_output(
    df: pd.DataFrame, output_path: Path, *, dry_run: bool, label: str
) -> None:
    """Write output DataFrame or print a preview when in dry-run mode."""

    if dry_run:
        print(f"[DRY RUN] Normalized {label} data (first 5 rows):")
        print(df.head())
        return

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"[INFO] Wrote normalized {label} data to {output_path} ({len(df)} rows)")


def ingest_average_weekly_corn_prices(
    download_url: str,
    output_path: Path,
    dry_run: bool = False,
    xlsx_path: Path | None = None,
) -> None:
    """
    Download and normalize OMAFRA's 'Average Weekly Corn Prices' dataset
    into a tidy CSV with columns:
        DATE (YYYY-MM-DD)
        YEAR (int)
        GEO ('Ontario')
        SERIES (e.g., 'Corn – old crop', 'Corn – new crop')
        VALUE (numeric price)
        UNIT (e.g., '$/tonne')
        SOURCE ('OMAFRA')
    """
    xls = _load_workbook(
        download_url=download_url, xlsx_path=xlsx_path, context="corn prices"
    )

    long_df = _normalize_weekly_price_sheet(
        xls=xls,
        sheet_name="Corn Prices",
        price_cols=["Old Crop Weekly Cash Price", "New Crop Cash Price"],
        unit="$/bushel",
        geo="Ontario",
        source="OMAFRA",
        rename_columns={"Unnamed: 0": "Year", "Unnamed: 1": "Week"},
    )

    _write_output(long_df, output_path, dry_run=dry_run, label="corn")


def ingest_average_weekly_soybean_prices(
    download_url: str,
    output_path: Path,
    dry_run: bool = False,
    xlsx_path: Path | None = None,
) -> None:
    """
    Normalize OMAFRA weekly soybean prices into the standard schema.
    """
    xls = _load_workbook(
        download_url=download_url, xlsx_path=xlsx_path, context="soybean prices"
    )

    long_df = _normalize_weekly_price_sheet(
        xls=xls,
        sheet_name="Soybean Prices",
        price_cols=["Old Crop Weekly Cash Price", "New Crop Cash Price"],
        unit="$/bushel",
        geo="Ontario",
        source="OMAFRA",
    )

    _write_output(long_df, output_path, dry_run=dry_run, label="soybean")


def ingest_average_weekly_wheat_prices(
    download_url: str,
    output_path: Path,
    dry_run: bool = False,
    xlsx_path: Path | None = None,
) -> None:
    """
    Normalize OMAFRA weekly wheat prices into the standard schema.
    """
    xls = _load_workbook(
        download_url=download_url, xlsx_path=xlsx_path, context="wheat prices"
    )

    preferred_sheet = "Winter Wheat Prices"
    sheet_name = preferred_sheet
    if preferred_sheet not in xls.sheet_names:
        fallback_sheets = [
            name
            for name in xls.sheet_names
            if re.search("wheat", name, re.IGNORECASE)
            and not re.search("definitions|averages", name, re.IGNORECASE)
        ]
        if not fallback_sheets:
            raise IngestionError(
                "Could not find a wheat price sheet; expected 'Winter Wheat Prices' or any sheet containing 'wheat'."
            )
        sheet_name = fallback_sheets[0]

    long_df = _normalize_weekly_price_sheet(
        xls=xls,
        sheet_name=sheet_name,
        price_cols=["Old Crop Weekly Cash Price", "New Crop Cash Price"],
        unit="$/bushel",  # Update if workbook indicates a different unit.
        geo="Ontario",
        source="OMAFRA",
    )

    _write_output(long_df, output_path, dry_run=dry_run, label="wheat")


def ingest_average_weekly_hog_prices(
    *,
    output_path: Path,
    dry_run: bool = False,
    xlsx_path: Optional[Path] = None,
) -> None:
    """
    Normalize OMAFRA *Average Weekly Hog Prices* from a local workbook.

    The resulting CSV has columns:
        DATE, YEAR, GEO, SERIES, VALUE, UNIT, SOURCE
    Where SERIES is e.g. 'Market Hog Price ($/100kg)' and UNIT is '$/100kg'.
    """

    xls = _load_workbook(
        download_url=None, xlsx_path=xlsx_path, context="hog prices"
    )
    long_df = _normalize_weekly_price_workbook(
        xls=xls, sheet_name="Swine Prices", context="hog prices"
    )

    if dry_run:
        print("[DRY RUN] Normalized hog prices (first 5 rows):")
        print(long_df.head())
        return

    _write_output(long_df, output_path, dry_run=dry_run, label="hog")


def ingest_average_weekly_cattle_prices(
    *,
    output_path: Path,
    dry_run: bool = False,
    xlsx_path: Optional[Path] = None,
) -> None:
    """
    Normalize OMAFRA *Average Weekly Cattle Prices* from a local workbook.

    The resulting CSV has columns:
        DATE, YEAR, GEO, SERIES, VALUE, UNIT, SOURCE
    Where SERIES is e.g. 'Steer Price ($/cwt)' and UNIT is '$/cwt'.
    """

    xls = _load_workbook(
        download_url=None, xlsx_path=xlsx_path, context="cattle prices"
    )
    long_df = _normalize_weekly_price_workbook(
        xls=xls, sheet_name="Market Price", context="cattle prices"
    )

    if dry_run:
        print("[DRY RUN] Normalized cattle prices (first 5 rows):")
        print(long_df.head())
        return

    _write_output(long_df, output_path, dry_run=dry_run, label="cattle")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-path",
        default="data/latest/omafra/commodity_prices/average_weekly_corn_prices.csv",
    )
    parser.add_argument(
        "--download-url",
        default=DEFAULT_DOWNLOAD_URL,
    )
    parser.add_argument(
        "--xlsx-path",
        help=(
            "Optional local path to an Excel workbook for the selected commodity. "
            "When provided, overrides --download-url."
        ),
    )
    parser.add_argument(
        "--soybean-xlsx-path",
        help="Optional local path to the Average Weekly Soybean Prices Excel workbook.",
    )
    parser.add_argument(
        "--wheat-xlsx-path",
        help="Optional local path to the Average Weekly Wheat Prices Excel workbook.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse but do not write output.",
    )
    parser.add_argument(
        "--only",
        choices=["corn", "soybeans", "wheat", "hogs", "cattle", "all"],
        default="all",
        help="Which OMAFRA commodity to ingest (default: all).",
    )
    parser.add_argument(
        "--hog-xlsx-path",
        help="Optional local path to the Average Weekly Hog Prices Excel workbook (weeklyswineprice_en.xlsx).",
    )
    parser.add_argument(
        "--cattle-xlsx-path",
        help="Optional local path to the Average Weekly Cattle Prices Excel workbook (weeklycattleprice_en.xlsx).",
    )
    args = parser.parse_args()

    if args.xlsx_path and args.only == "all":
        parser.error("--xlsx-path can only be used with a single commodity (--only <name>)")

    base_dir = Path(args.output_path).parent
    corn_output = Path(args.output_path)
    soybean_output = base_dir / "average_weekly_soybean_prices.csv"
    wheat_output = base_dir / "average_weekly_wheat_prices.csv"
    hog_output = base_dir / "average_weekly_hog_prices.csv"
    cattle_output = base_dir / "average_weekly_cattle_prices.csv"

    def _xlsx_for(commodity: str, legacy_path: str | None = None) -> Path | None:
        if args.xlsx_path and args.only == commodity:
            return Path(args.xlsx_path)
        if legacy_path:
            return Path(legacy_path)
        return None

    if args.only in ("corn", "all"):
        ingest_average_weekly_corn_prices(
            download_url=args.download_url,
            output_path=corn_output,
            dry_run=args.dry_run,
            xlsx_path=_xlsx_for("corn"),
        )

    if args.only in ("soybeans", "all"):
        ingest_average_weekly_soybean_prices(
            download_url=(
                DEFAULT_SOYBEAN_DOWNLOAD_URL
                if args.download_url == DEFAULT_DOWNLOAD_URL
                else args.download_url
            ),
            output_path=soybean_output,
            dry_run=args.dry_run,
            xlsx_path=_xlsx_for("soybeans", args.soybean_xlsx_path),
        )

    if args.only in ("wheat", "all"):
        ingest_average_weekly_wheat_prices(
            download_url=(
                DEFAULT_WHEAT_DOWNLOAD_URL
                if args.download_url == DEFAULT_DOWNLOAD_URL
                else args.download_url
            ),
            output_path=wheat_output,
            dry_run=args.dry_run,
            xlsx_path=_xlsx_for("wheat", args.wheat_xlsx_path),
        )

    if args.only in ("hogs", "all"):
        hog_xlsx = _xlsx_for("hogs", args.hog_xlsx_path)
        if hog_xlsx:
            ingest_average_weekly_hog_prices(
                output_path=hog_output,
                dry_run=args.dry_run,
                xlsx_path=hog_xlsx,
            )
        else:
            print(
                "[INFO] Skipping hog ingestion – no hog workbook path was provided "
                "(--xlsx-path or --hog-xlsx-path)."
            )

    if args.only in ("cattle", "all"):
        cattle_xlsx = _xlsx_for("cattle", args.cattle_xlsx_path)
        if cattle_xlsx:
            ingest_average_weekly_cattle_prices(
                output_path=cattle_output,
                dry_run=args.dry_run,
                xlsx_path=cattle_xlsx,
            )
        else:
            print(
                "[INFO] Skipping cattle ingestion – no cattle workbook path was provided "
                "(--xlsx-path or --cattle-xlsx-path)."
            )


if __name__ == "__main__":
    main()
