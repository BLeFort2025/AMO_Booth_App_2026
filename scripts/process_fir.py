"""
FIR ETL Pipeline
================
Extracts key fiscal and infrastructure indicators from Ontario FIR xlsx files
and produces data/derived/fir_indicators.csv.

Usage:
    python scripts/process_fir.py                    # Process all years
    python scripts/process_fir.py --year 2024         # Single year
    python scripts/process_fir.py --year 2020 2024    # Specific years
    python scripts/process_fir.py --sample 5          # Quick test: 5 files per year

Performance:
    Uses python-calamine (Rust-based xlsx reader) for 10-50x faster parsing
    than openpyxl.  Processes ~2,134 files in minutes, not hours.
"""

import argparse
import io
import logging
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import yaml

try:
    from python_calamine import CalamineWorkbook
    HAS_CALAMINE = True
except ImportError:
    HAS_CALAMINE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIR_DIR = PROJECT_ROOT / "data" / "FIR Data"
OUTPUT_PATH = PROJECT_ROOT / "data" / "derived" / "fir_indicators.csv"
CONFIG_PATH = PROJECT_ROOT / "config" / "fir_indicators.yaml"
CROSSWALK_PATH = PROJECT_ROOT / "config" / "fir_sgc_crosswalk.csv"
YEARS = list(range(2010, 2025))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fir_etl")


# ---------------------------------------------------------------------------
# Load indicator config
# ---------------------------------------------------------------------------

def load_indicator_config() -> dict:
    """Load FIR indicator definitions from YAML config."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


# ---------------------------------------------------------------------------
# Cell extraction engine (calamine-based)
# ---------------------------------------------------------------------------

def _match_line_code(cell, line_code: str) -> bool:
    """Check if a cell value matches a FIR line code.
    
    Calamine may return line codes as str ('0010') or float (10.0).
    We normalize both to zero-padded strings for comparison.
    """
    if cell is None or cell == "":
        return False
    if isinstance(cell, (int, float)):
        # e.g. 10.0 -> "0010", 9199.0 -> "9199"
        try:
            return f"{int(cell):04d}" == line_code
        except (ValueError, OverflowError):
            return False
    return str(cell).strip() == line_code


def _get_deterministic_col_idx(schedule: str, year: int, base_col: int) -> int:
    """Apply known MMAH FIR format shifts deterministically based on year.

    Instead of probabilistic ±1 column scanning, this function encodes
    the exact known column shifts from MMAH template changes:
      - S02: shifted RIGHT by 1 between 2016 and 2022
      - S80A: shifted LEFT by 1 in 2023+
    """
    if year is None:
        return base_col
    # S02 shifted RIGHT by 1 between 2016 and 2022
    if schedule == "02" and 2016 <= year <= 2022:
        return base_col + 1
    # S80A shifted LEFT by 1 in 2023+
    if schedule == "80A" and year >= 2023:
        return max(0, base_col - 1)
    return base_col


def _extract_from_sheet_data(rows: list, line_code: str, col_idx: int,
                             schedule: str = None, year: int = None):
    """Find a value in sheet data by FIR line code and exact column index.

    Uses deterministic year-aware column targeting — no probabilistic
    fallback. The column index is adjusted by _get_deterministic_col_idx()
    BEFORE this function is called.

    Guard: rejects values where float(v) == int(line_code), which indicates
    a section header row that echoes the line number (e.g. S02 row where
    col[4]=40.0 is the line code, not real data).
    """
    # Adjust column deterministically for known MMAH template shifts
    target_col = _get_deterministic_col_idx(schedule or "", year, col_idx)

    # Parse line code as integer for false-positive detection
    try:
        line_code_int = int(line_code)
    except ValueError:
        line_code_int = None

    for row in rows:
        for cell in row[:5]:
            if _match_line_code(cell, line_code):
                if target_col < len(row):
                    v = row[target_col]
                    if v is not None and str(v).strip() != "":
                        # Guard: reject hidden header rows echoing the line code
                        if line_code_int is not None:
                            try:
                                if float(v) == line_code_int:
                                    break  # Skip this row, keep scanning
                            except (ValueError, TypeError):
                                pass
                        return v
                # Target column empty or row too short — keep scanning
                break  # Break cell loop, continue to next row
    return None


def _build_fir_col_map(rows: list) -> tuple[dict, int]:
    """Build FIR column number -> 0-based index mapping from header area.

    Calamine returns numeric cells as float/int, so we handle both
    numeric types and string representations.

    Returns (col_map, header_row_idx) where header_row_idx is 0-based.
    """
    best_match = ({}, 0)
    best_count = 0

    for row_idx, row in enumerate(rows[:25]):
        nums_found = {}
        for col_i, cell in enumerate(row):
            if cell is None or cell == "":
                continue
            # Calamine returns numbers as float/int directly
            num = None
            if isinstance(cell, (int, float)):
                if cell == int(cell) and 1 <= int(cell) <= 20:
                    num = int(cell)
            else:
                val = str(cell).strip()
                # Handle "16" or "16.0"
                try:
                    f = float(val)
                    if f == int(f) and 1 <= int(f) <= 20:
                        num = int(f)
                except ValueError:
                    pass

            if num is not None:
                nums_found[num] = col_i  # 0-based

        if len(nums_found) > best_count:
            best_count = len(nums_found)
            best_match = (nums_found, row_idx)

        if len(nums_found) >= 2:
            return nums_found, row_idx

    if best_count >= 1:
        return best_match

    return {}, 0


def _extract_fir_value(rows: list, line_code: str, fir_col: int,
                       col_map: dict, header_row: int):
    """Extract a value using FIR column mapping."""
    target_idx = col_map.get(fir_col)
    if target_idx is None:
        return None

    for row in rows[header_row + 1:]:
        for cell in row[:5]:
            if _match_line_code(cell, line_code):
                if target_idx < len(row):
                    v = row[target_idx]
                    return v if v != "" and v is not None else None
                return None
    return None


# ---------------------------------------------------------------------------
# Derived indicator computation
# ---------------------------------------------------------------------------

def _safe_div(a, b):
    if a is None or b is None:
        return None
    try:
        n, d = float(a), float(b)
        return n / d if d != 0 else None
    except (ValueError, TypeError):
        return None


# FIR-specific null sentinels found in MMAH Excel files
_FIR_NULL_SENTINELS = frozenset({
    "", "NA", "N/A", "n/a", "-", "--", "...", "NIL", "ND", "#DIV/0!",
})


def _safe_float(val):
    """Safely cast to float, returning None for non-numeric.

    Handles FIR-specific sentinel values ("-", "N/A", "NIL", etc.)
    and accounting-formatted numbers with commas ("1,234.50").
    """
    if val is None:
        return None
    if isinstance(val, str):
        v_str = val.strip().replace(",", "")
        # Handle accounting parentheses for negatives: (500.50) → -500.50
        if v_str.startswith("(") and v_str.endswith(")"):
            v_str = "-" + v_str[1:-1]
        if v_str.upper() in _FIR_NULL_SENTINELS or v_str == "":
            return None
        val = v_str
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_add(*args):
    vals = []
    for v in args:
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (ValueError, TypeError):
            pass
    return sum(vals) if vals else None


def _apply_yaml_bounds(r: dict, indicator_config: dict):
    """Apply min_val / max_val from YAML indicator config to reject artifacts.

    Red-Team Fix 3: bounds are defined per-indicator in fir_indicators.yaml
    rather than hardcoded in the Python ETL logic. This ensures new indicators
    automatically get validation without code changes.
    """
    for group_name, group_cfg in indicator_config.items():
        if group_name == "computed":
            continue
        for ind_name, ind_def in group_cfg.get("indicators", {}).items():
            val = _safe_float(r.get(ind_name))
            if val is None:
                continue
            min_val = ind_def.get("min_val")
            max_val = ind_def.get("max_val")
            if min_val is not None and val < min_val:
                log.debug("  %s=%s below min_val %s, setting to None", ind_name, val, min_val)
                r[ind_name] = None
            elif max_val is not None and val > max_val:
                log.debug("  %s=%s above max_val %s, setting to None", ind_name, val, max_val)
                r[ind_name] = None


def _compute_derived(r: dict, indicator_config: dict = None):
    """Compute derived indicators from extracted values.
    
    Tax rates and ratios are extracted directly from Schedule 22A.
    We compute aggregated/combined metrics here.
    
    Key methodology (per FIR expert review 2024-02-20):
      - Tax class share denominators use MUNICIPAL taxes only (LT+UT),
        excluding Education taxes (set uniformly by the Province).
      - operating_surplus is an accounting surplus (accrual-based), 
        not a cash budget surplus.
    """
    # Municipal tax totals (LT + UT, excludes Education)
    r["farmland_muni_taxes"] = _safe_add(r.get("farmland_lt_taxes"), r.get("farmland_ut_taxes"))
    r["residential_muni_taxes"] = _safe_add(r.get("residential_lt_taxes"), r.get("residential_ut_taxes"))
    r["commercial_muni_taxes"] = _safe_add(r.get("commercial_lt_taxes"), r.get("commercial_ut_taxes"))
    r["industrial_muni_taxes"] = _safe_add(r.get("industrial_lt_taxes"), r.get("industrial_ut_taxes"))
    r["multi_residential_muni_taxes"] = _safe_add(r.get("multi_residential_lt_taxes"), r.get("multi_residential_ut_taxes"))
    r["pipeline_muni_taxes"] = _safe_add(r.get("pipeline_lt_taxes"), r.get("pipeline_ut_taxes"))
    # Phase 2: close the pie chart
    r["managed_forest_muni_taxes"] = _safe_add(r.get("managed_forest_lt_taxes"), r.get("managed_forest_ut_taxes"))
    r["landfill_muni_taxes"] = _safe_add(r.get("landfill_lt_taxes"), r.get("landfill_ut_taxes"))
    r["total_muni_taxes"] = _safe_add(r.get("total_lt_taxes"), r.get("total_ut_taxes"))

    # Road totals
    r["total_road_km"] = _safe_add(r.get("paved_road_km"), r.get("unpaved_road_km"))

    # ── YAML-driven bounds validation ─────────────────────────────────
    # Apply min_val / max_val from indicator config to reject extraction
    # artifacts. Bounds are defined per-indicator in fir_indicators.yaml
    # rather than hardcoded here (red-team Fix 3: separation of concerns).
    if indicator_config:
        _apply_yaml_bounds(r, indicator_config)

    # Waste diversion
    div = r.get("waste_diverted_tonnes")
    col = r.get("solid_waste_tonnes")
    try:
        if div is not None and col is not None:
            total = float(div) + float(col)
            r["waste_diversion_rate"] = float(div) / total if total > 0 else None
        else:
            r["waste_diversion_rate"] = None
    except (ValueError, TypeError):
        r["waste_diversion_rate"] = None

    # Financial health
    r["ompf_dependency"] = _safe_div(r.get("ompf_grant"), r.get("total_revenue"))
    # Tax arrears ratio — uses total_taxes (incl. Education) because the
    # municipality bears 100% collection risk on all taxes, including the
    # education levy it must remit to school boards.
    # 🔴 Red-Team Fix: Coalesce None→0 for taxes_receivable — zero arrears
    #    is the best-case scenario, should display 0.0 not None.
    _arrears_num = r.get("taxes_receivable")
    r["tax_arrears_ratio"] = _safe_div(
        0 if _arrears_num is None else _arrears_num, r.get("total_taxes"))
    # A1 Audit Fix: Use _safe_float for operating surplus
    rev = _safe_float(r.get("total_revenue"))
    exp = _safe_float(r.get("total_expenses"))
    if rev is not None and exp is not None:
        r["operating_surplus"] = rev - exp
    else:
        r["operating_surplus"] = None

    # OMPF Relief Factor (expert-recommended)
    r["ompf_relief_factor"] = _safe_div(r.get("ompf_grant"), r.get("total_lt_taxes"))

    # Phase 2: Reserve Fund Health
    r["total_reserves_and_funds"] = _safe_add(r.get("total_reserves"), r.get("total_reserve_funds"))
    r["reserves_to_revenue"] = _safe_div(r.get("total_reserves_and_funds"), r.get("total_revenue"))

    # Phase 2: Capital Reinvestment
    r["capital_reinvestment_rate"] = _safe_div(r.get("capital_additions"), r.get("total_revenue"))

    # Phase 2: User Fee Reliance
    r["user_fee_reliance"] = _safe_div(r.get("user_fees_charges"), r.get("total_revenue"))

    # ── Phase 3: Consultant-Grade Commercial Metrics ──────────────────
    # MMAH Financial Indicator Review / BMA / S&P credit metrics

    # Asset Consumption Ratio ("The Rust Indicator")
    # MMAH: <50% low risk, 50-75% moderate, >75% high risk
    r["asset_consumption_ratio"] = _safe_div(
        r.get("tca_accum_amortization"), r.get("tca_historical_cost"))

    # Staffing Intensity — "Sunshine List" defense metric
    r["staffing_intensity"] = _safe_div(
        r.get("total_salaries_benefits"), r.get("total_expenses"))

    # Cash Operating Margin — adds back non-cash depreciation
    # Q4 Audit Fix: use _safe_float to prevent TypeError; add revenue floor
    rev = _safe_float(r.get("total_revenue"))
    exp = _safe_float(r.get("total_expenses"))
    amort = _safe_float(r.get("total_amortization_expense"))
    if rev is not None and exp is not None and amort is not None and abs(rev) > 1000:
        r["cash_operating_margin"] = (rev - exp + amort) / rev
    else:
        r["cash_operating_margin"] = None

    # Debt-to-Revenue — standard BMA benchmark (>50% = tight)
    # A2 Audit Fix: DO NOT coalesce None→0 for debt numerator.
    # Missing Schedule 74 means debt is UNKNOWN, not zero.
    r["debt_to_revenue"] = _safe_div(
        r.get("total_long_term_debt"), r.get("total_revenue"))

    # Average Municipal Tax per Household
    # ⚠️ Red-Team Fix: numerator must include multi-residential taxes because
    #    total_households (S02) counts ALL dwelling units including apartments.
    # Note: total_households is already sanitized by _apply_yaml_bounds() above
    #       (min_val: 1 in YAML rejects line code echo artifacts).
    _hh_raw = _safe_float(r.get("total_households"))
    _res_tax = r.get("residential_muni_taxes")
    _multi_res_tax = r.get("multi_residential_muni_taxes")
    _combined_res_tax = _safe_add(_res_tax, _multi_res_tax)
    r["avg_tax_per_household"] = _safe_div(_combined_res_tax, _hh_raw)

    # Farmland-specific
    # ⚠️ Red-Team Fix: Use farmland_muni_taxes (excludes Education) instead
    #    of farmland_total_taxes. Education rate on farmland has been slashed
    #    to near-zero by the Province — including it masks local council decisions.
    r["farmland_tax_per_hectare"] = _safe_div(r.get("farmland_muni_taxes"), r.get("ag_land_hectares"))
    r["farmland_share_of_cva"] = _safe_div(r.get("farmland_cva"), r.get("total_taxable_cva"))

    # Farmland Municipal Tax per $100k CVA (expert-recommended)
    tax_per_cva = _safe_div(r.get("farmland_muni_taxes"), r.get("farmland_cva"))
    r["farmland_tax_per_100k_cva"] = tax_per_cva * 100_000 if tax_per_cva is not None else None

    # Assessment vs Tax Burden Gap (expert-recommended)
    # Positive = farmland is shielded (pays less tax share than CVA share)
    cva_share = _safe_div(r.get("farmland_cva"), r.get("total_taxable_cva"))
    tax_share = _safe_div(r.get("farmland_muni_taxes"), r.get("total_muni_taxes"))
    if cva_share is not None and tax_share is not None:
        r["farmland_burden_gap"] = cva_share - tax_share
    else:
        r["farmland_burden_gap"] = None

    # Tax class share of MUNICIPAL taxes (LT+UT, excludes Education)
    # Expert R2: CT/IT now use subtotal lines (9120/9130) and include UT taxes
    r["farmland_share_of_taxes"] = _safe_div(r.get("farmland_muni_taxes"), r.get("total_muni_taxes"))
    r["residential_share_of_taxes"] = _safe_div(r.get("residential_muni_taxes"), r.get("total_muni_taxes"))
    r["commercial_share_of_taxes"] = _safe_div(r.get("commercial_muni_taxes"), r.get("total_muni_taxes"))
    r["industrial_share_of_taxes"] = _safe_div(r.get("industrial_muni_taxes"), r.get("total_muni_taxes"))
    # Expert R3: close share gap to ~99.5%
    r["multi_residential_share_of_taxes"] = _safe_div(r.get("multi_residential_muni_taxes"), r.get("total_muni_taxes"))
    r["pipeline_share_of_taxes"] = _safe_div(r.get("pipeline_muni_taxes"), r.get("total_muni_taxes"))
    # Phase 2: close the pie chart
    r["managed_forest_share_of_taxes"] = _safe_div(r.get("managed_forest_muni_taxes"), r.get("total_muni_taxes"))
    r["landfill_share_of_taxes"] = _safe_div(r.get("landfill_muni_taxes"), r.get("total_muni_taxes"))

    # Data quality flag: sum of all class shares should be ≤ 1.02
    # Values > 1.02 indicate data entry errors by municipal clerks
    # (e.g. County levy in wrong column, supplementary write-offs).
    # Do NOT cap at 1.0 — preserve raw math, flag for analyst filtering.
    share_keys = [
        "farmland_share_of_taxes", "residential_share_of_taxes",
        "commercial_share_of_taxes", "industrial_share_of_taxes",
        "multi_residential_share_of_taxes", "pipeline_share_of_taxes",
        "managed_forest_share_of_taxes", "landfill_share_of_taxes",
    ]
    share_vals = [r.get(k) for k in share_keys if r.get(k) is not None]
    if share_vals:
        share_sum = sum(share_vals)
        r["tax_share_sum"] = share_sum
        r["is_invalid_tax_sum"] = share_sum > 1.02
    else:
        r["tax_share_sum"] = None
        r["is_invalid_tax_sum"] = None

    # S70 Accumulated Surplus fallback: try modern line 9971, fall back to 9950
    if r.get("accumulated_surplus") is None and r.get("_accumulated_surplus_9950") is not None:
        r["accumulated_surplus"] = r.pop("_accumulated_surplus_9950")
    elif "_accumulated_surplus_9950" in r:
        r.pop("_accumulated_surplus_9950")  # Clean up temp key


# ---------------------------------------------------------------------------
# Per-municipality extraction
# ---------------------------------------------------------------------------

def extract_municipality(zip_path: Path, indicator_config: dict) -> dict | None:
    """Extract all configured indicators from a single FIR zip file."""
    fname = zip_path.name

    m = re.match(r"FI(\d{2})(\d{4})\s+(.+?)\.zip", fname)
    if not m:
        return None

    yr2, fir_code, muni_name = m.group(1), m.group(2), m.group(3)
    year = 2000 + int(yr2)

    record = {"fir_code": fir_code, "municipality_name": muni_name, "year": year}

    try:
        with zipfile.ZipFile(zip_path) as z:
            xlsx_files = [f for f in z.namelist()
                          if f.endswith(".xlsx") or f.endswith(".xls")]
            if not xlsx_files:
                return None
            xlsx_bytes = z.read(xlsx_files[0])

        wb = CalamineWorkbook.from_object(io.BytesIO(xlsx_bytes))
        available_sheets = set(wb.sheet_names)

        for group_name, group_cfg in indicator_config.items():
            if group_name == "computed":
                continue

            schedule = group_cfg.get("schedule")
            if not schedule or schedule not in available_sheets:
                for ind_name in group_cfg.get("indicators", {}):
                    record[ind_name] = None
                continue

            rows = wb.get_sheet_by_name(schedule).to_python()
            col_type = group_cfg.get("col_type", "fir")
            match_type = group_cfg.get("match_type", "line")

            if match_type == "rtc":
                # Schedule 22A: match on Realty Tax Class string (RT, FT, etc.)
                col_map, header_row = _build_fir_col_map(rows)
                for ind_name, ind_def in group_cfg.get("indicators", {}).items():
                    rtc_code = ind_def["rtc"]
                    fir_col = ind_def["col"]
                    target_idx = col_map.get(fir_col)
                    value = None
                    if target_idx is not None:
                        for row in rows[header_row + 1:]:
                            # RTC codes are in the first few columns as strings
                            for cell in row[:8]:
                                if cell is not None and str(cell).strip() == rtc_code:
                                    if target_idx < len(row):
                                        v = row[target_idx]
                                        if v is not None and v != "":
                                            try:
                                                value = float(v)
                                            except (ValueError, TypeError):
                                                pass
                                    break
                            if value is not None:
                                break
                    record[ind_name] = value

            elif col_type == "excel":
                # Direct Excel column: col value is 1-based Excel column
                # Red-Team Fix 1: pass schedule and year for deterministic
                # column targeting (replaces dangerous probabilistic fallback)
                for ind_name, ind_def in group_cfg.get("indicators", {}).items():
                    line_code = str(ind_def["line"])
                    excel_col = ind_def["col"]  # 1-based
                    value = _extract_from_sheet_data(
                        rows, line_code, excel_col - 1,
                        schedule=schedule, year=year
                    )
                    if value is not None:
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            pass
                    record[ind_name] = value
            else:
                # FIR column mapping mode
                col_map, header_row = _build_fir_col_map(rows)
                for ind_name, ind_def in group_cfg.get("indicators", {}).items():
                    line_code = str(ind_def["line"])
                    fir_col = ind_def["col"]
                    value = _extract_fir_value(rows, line_code, fir_col,
                                              col_map, header_row)
                    if value is not None:
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            pass
                    record[ind_name] = value

    except Exception as e:
        log.warning("Failed %s: %s", fname, e)
        return None

    _compute_derived(record, indicator_config)
    return record


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def process_all(years: list[int] = None, sample: int = 0) -> pd.DataFrame:
    if years is None:
        years = YEARS

    cfg = load_indicator_config()

    all_zips = []
    for year in years:
        year_dir = FIR_DIR / str(year)
        if not year_dir.exists():
            log.warning("Year directory not found: %s", year_dir)
            continue
        zips = sorted(year_dir.glob("FI*.zip"))
        if sample > 0:
            zips = zips[:sample]
        all_zips.extend(zips)
        log.info("Found %d files for year %d", len(zips), year)

    log.info("Total files to process: %d", len(all_zips))

    records = []
    failed = 0
    t0 = time.time()

    for i, zp in enumerate(all_zips, 1):
        record = extract_municipality(zp, cfg)
        if record:
            records.append(record)
        else:
            failed += 1

        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(all_zips) - i) / rate if rate > 0 else 0
            log.info(
                "  %d/%d processed (%.1f files/sec, ETA %.0fs)",
                i, len(all_zips), rate, eta,
            )

    elapsed = time.time() - t0
    log.info(
        "Extraction complete: %d records from %d files (%d failed) in %.1fs (%.1f files/sec)",
        len(records), len(all_zips), failed, elapsed, len(all_zips) / elapsed,
    )

    if not records:
        log.error("No records extracted!")
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Merge in SGC codes and tier from crosswalk
    if CROSSWALK_PATH.exists():
        xw = pd.read_csv(CROSSWALK_PATH, dtype=str)
        xw = xw[xw["sgc_code"].notna() & (xw["sgc_code"] != "")]
        xw = xw[["fir_code", "sgc_code", "tier"]].copy()
        xw["fir_code"] = xw["fir_code"].str.zfill(4)
        df["fir_code"] = df["fir_code"].astype(str).str.zfill(4)
        df = df.merge(xw, on="fir_code", how="left")
        log.info("Merged SGC codes: %d/%d rows have sgc_code (%d upper-tier)",
                 df["sgc_code"].notna().sum(), len(df),
                 (df["tier"] == "upper").sum())
        # Q15 Audit Fix: Log unmapped FIR codes for crosswalk maintenance
        unmapped = df[df["sgc_code"].isna()]
        if not unmapped.empty:
            log.warning(
                "SGC Crosswalk: %d FIR codes have no SGC mapping (will be excluded from dashboard):",
                len(unmapped),
            )
            for _, row in unmapped.head(20).iterrows():
                log.warning("  FIR %s — %s (%d)", row["fir_code"], row["municipality_name"], row["year"])
    else:
        df["sgc_code"] = None
        df["tier"] = None
        log.warning("Crosswalk not found at %s — sgc_code will be empty", CROSSWALK_PATH)

    id_cols = ["fir_code", "municipality_name", "year", "sgc_code", "tier"]
    other_cols = sorted([c for c in df.columns if c not in id_cols])
    df = df[id_cols + other_cols]
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(years: list[int] = None, sample: int = 0) -> pd.DataFrame:
    """Entry point for pipeline integration."""
    df = process_all(years=years, sample=sample)
    if df.empty:
        return df

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    log.info("Saved %d rows to %s", len(df), OUTPUT_PATH)

    print(f"\n{'='*60}")
    print(f"FIR ETL COMPLETE")
    print(f"  Records: {len(df)}")
    print(f"  Years:   {sorted(df['year'].unique())}")
    print(f"  Munis:   {df['fir_code'].nunique()}")
    print(f"  Output:  {OUTPUT_PATH}")
    print(f"{'='*60}")

    null_rates = df.isnull().mean().sort_values(ascending=False)
    high_null = null_rates[null_rates > 0.1]
    if not high_null.empty:
        print(f"\nColumns with >10% null:")
        for col, rate in high_null.items():
            print(f"  {col}: {rate:.1%} null")

    return df


def main():
    parser = argparse.ArgumentParser(description="FIR ETL Pipeline")
    parser.add_argument("--year", type=int, nargs="+",
                        help="Process specific year(s) only")
    parser.add_argument("--sample", type=int, default=0,
                        help="Process only N files per year (for testing)")
    args = parser.parse_args()
    run(years=args.year, sample=args.sample)


if __name__ == "__main__":
    main()
