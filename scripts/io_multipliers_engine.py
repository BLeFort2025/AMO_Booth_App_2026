from __future__ import annotations

import sys
import yaml
from pathlib import Path
from functools import lru_cache
from typing import Literal, Optional, Union, List

# Ensure project root is on sys.path for importing app modules
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.smart_read import smart_read

GeoScope = Literal["all_provinces", "within_province", "national"]
import pandas as pd
import numpy as np

# --- CONFIGURATION ---
DATA_LATEST = Path("data/latest")
# Using .parquet for optimized memory usage and faster loads
MULT_FP = DATA_LATEST / "io_multipliers_standardized.parquet"
SU_SUBSET_FP = DATA_LATEST / "io_supply_use_subset.csv"

# --- BASKETS CONFIG PATH (ROBUST FIX) ---
# Resolve path relative to this script file to ensure stability
# Structure assumed: [root]/scripts/this_file.py -> [root]/config/io_baskets.yml
try:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BASKETS_FP = BASE_DIR / "config" / "io_baskets.yml"
except NameError:
    # Fallback for interactive/notebook environments where __file__ is undefined
    BASKETS_FP = Path("config/io_baskets.yml")

Scope = Literal["direct", "direct_indirect", "direct_indirect_induced"]

SCOPE_TO_MULT_TYPE: dict[Scope, str] = {
    "direct": "Direct multiplier",
    "direct_indirect": "Simple multiplier",
    "direct_indirect_induced": "Total multiplier",
}

def normalize_code_simple(code: str) -> str:
    """Helper to strip prefixes from YAML config to match data."""
    s = str(code).upper().strip()
    for prefix in ["BS", "GS", "NP"]:
        s = s.replace(prefix, "")
    return s.rstrip("0")

@lru_cache(maxsize=1)
def load_multipliers() -> pd.DataFrame:
    """Loads the standardized multipliers file.

    Memory optimisation: string columns are converted to ``pd.Categorical``
    because they have very few unique values (3-250) repeated across 5.2 M
    rows.  This cuts in-memory size from ~2.8 GB to ~83 MB — essential for
    Streamlit Community Cloud's ~1 GB limit.
    """
    dtypes_dict = {
        'YEAR': 'Int32',
        'GEO': 'category',
        'industry_code': 'category',
        'join_code': 'category',
        'industry_name': 'category',
        'multiplier_type': 'category',
        'variable': 'category',
        'value': 'float32'
    }

    try:
        df = smart_read(MULT_FP, dtype=dtypes_dict)
    except FileNotFoundError:
        alt_fp = MULT_FP.with_suffix("")
        if alt_fp.exists():
            df = smart_read(alt_fp, dtype=dtypes_dict)
        else:
            return pd.DataFrame()

    # --- THE GHOSTBUSTER FIX ---
    # Immediately drop rows where the value is missing (NaN).
    # This removes legacy rows (like 1114 in 2014+) so they don't trigger overlap warnings.
    if not df.empty and "value" in df.columns:
        df = df.dropna(subset=["value"])

    # --- GEO SCOPE TAGGING (replaces aggressive deduplication) ---
    # StatCan Table 36-10-0595 publishes TWO rows per provincial metric:
    #   Row 1 = "All provinces" (includes inter-provincial supply chain)
    #   Row 2 = "Within province" (impacts retained within the province)
    # We tag each row so the UI can let the user choose.
    if not df.empty:
        subset_cols = ['YEAR', 'GEO', 'join_code', 'variable', 'multiplier_type']
        existing_cols = [c for c in subset_cols if c in df.columns]

        if len(existing_cols) == 5:
            # Mark duplicates: first occurrence = all_provinces, second = within_province
            is_dup = df.duplicated(subset=existing_cols, keep='first')
            has_dup = df.duplicated(subset=existing_cols, keep=False)
            # Rows that ARE duplicated and are the first occurrence
            df['geo_scope'] = 'national'  # default for non-duplicated rows
            df.loc[has_dup & ~is_dup, 'geo_scope'] = 'all_provinces'
            df.loc[is_dup, 'geo_scope'] = 'within_province'
        else:
            df['geo_scope'] = 'national'

    # --- MEMORY OPTIMISATION ---
    # String columns have very few unique values (3-250) but 5.2M rows.
    # We now enforce 'category' dtypes directly in pd.read_csv() above, 
    # which prevents the 3GB intermediate memory spike during loading,
    # and reduces the final size to ~85 MB.
    if not df.empty and 'geo_scope' in df.columns:
        df['geo_scope'] = df['geo_scope'].astype('category')

    # Add MultiIndex for fast loc-based filtering
    if not df.empty:
        df.set_index(["GEO", "multiplier_type"], drop=False, inplace=True)
        df.sort_index(inplace=True)

    return df

@lru_cache(maxsize=1)
def load_supply_use_subset() -> pd.DataFrame:
    """Loads the historical output/supply data."""
    if not SU_SUBSET_FP.exists(): return pd.DataFrame()
    return smart_read(SU_SUBSET_FP)

@lru_cache(maxsize=1)
def _get_actual_output_lookup() -> pd.Series:
    """Pre-aggregates supply use data for O(1) lookups."""
    df = load_supply_use_subset()
    if df.empty: return pd.Series()
    # Ensure types for safe multi-index lookup
    df['GEO'] = df['GEO'].astype(str)
    df['YEAR'] = df['YEAR'].astype(int)
    df['join_code'] = df['join_code'].astype(str)
    return df.groupby(['GEO', 'YEAR', 'join_code'])['VALUE'].sum()

@lru_cache(maxsize=1)
def load_baskets_config() -> dict:
    """Loads industry baskets from YAML with fallback pathing."""
    # FIX: Added encoding="utf-8" to handle emojis (⚠️) in the config file
    # 1. Try default relative path
    if BASKETS_FP.exists():
        with open(BASKETS_FP, "r", encoding="utf-8") as f:
            return yaml.safe_load(f).get("baskets", {})
            
    # 2. Try looking one level up (common issue in Streamlit cloud vs local)
    fallback = Path("../config/io_baskets.yml")
    if fallback.exists():
        with open(fallback, "r", encoding="utf-8") as f:
            return yaml.safe_load(f).get("baskets", {})
            
    return {}


@lru_cache(maxsize=1)
def load_oag_config() -> dict:
    """Loads OAG ground-truth data config for apple/tender fruit calibration."""
    oag_fp = BASE_DIR / "config" / "oag_apple_data.yml"
    if oag_fp.exists():
        with open(oag_fp, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

# --- HELPER FUNCTIONS ---

def available_geographies() -> List[str]:
    df = load_multipliers()
    if df.empty: return []
    if "GEO" not in df.columns: return []
    return sorted(df["GEO"].unique().tolist())

def available_years(geo: Optional[str] = None) -> List[int]:
    df = load_multipliers()
    if df.empty: return []
    if "YEAR" not in df.columns: return []
    if geo:
        df = df[df["GEO"] == geo]
    return sorted(df["YEAR"].unique().astype(int).tolist())

def available_industries(geo: str, year: int) -> List[str]:
    df = load_multipliers()
    if df.empty: return []
    
    mask = (df["GEO"] == geo) & (df["YEAR"] == int(year))
    col = "join_code" if "join_code" in df.columns else "industry_code"
    
    subset = df.loc[mask, [col, "industry_name"]].drop_duplicates()
    if subset.empty: return []
    
    return sorted([f"{r['industry_name']} [{r[col]}]" for _, r in subset.iterrows()])

@lru_cache(maxsize=32)
def industries_for_basket(basket_key: str) -> pd.DataFrame:
    baskets = load_baskets_config()
    conf = baskets.get(basket_key)
    if not conf: return pd.DataFrame()

    df = load_multipliers()
    if df.empty: return pd.DataFrame()
    
    all_rows = df[["industry_name", "join_code"]].drop_duplicates()
    
    match_conf = conf.get("match", {})
    prefixes = [normalize_code_simple(p) for p in match_conf.get("any_code_prefix", [])]
    exacts = [normalize_code_simple(e) for e in match_conf.get("any_code_exact", [])]
    
    ex_conf = conf.get("exclude", {})
    ex_exacts = [normalize_code_simple(e) for e in ex_conf.get("any_code_exact", [])]
    
    matches = []
    for _, row in all_rows.iterrows():
        code = str(row["join_code"])
        
        if code in ex_exacts: continue
            
        is_match = False
        if code in exacts: is_match = True
        elif any(code.startswith(str(p)) for p in prefixes): is_match = True
            
        if is_match:
            matches.append(row)

    # --- PARENT DOMINANCE FILTER (Anti-Double-Counting) ---
    # If we have selected both "312" (Parent) and "3121" (Child),
    # we must drop the Child to avoid summing the same money twice.
    
    if matches:
        # 1. Extract just the codes
        selected_codes = set(str(row["join_code"]) for row in matches)
        final_matches = []
        
        for row in matches:
            code = str(row["join_code"])
            # Check if this code is a "child" of another code currently in our selection
            # (e.g., Drop "3121" if "312" is also in the list)
            is_child = False
            for other in selected_codes:
                if other != code and code.startswith(other):
                    is_child = True
                    break
            
            if not is_child:
                final_matches.append(row)
        
        matches = final_matches

    return pd.DataFrame(matches).sort_values("join_code")

def get_available_historical_codes(geo: str, year: int) -> List[str]:
    df = load_supply_use_subset()
    if df.empty: return []
    mask = (df["YEAR"] == int(year)) & (df["GEO"] == geo)
    return df.loc[mask, "join_code"].unique().tolist()

def get_actual_output(geo: str, year: int, join_codes: List[str]) -> float:
    lookup = _get_actual_output_lookup()
    if lookup.empty: return 0.0

    total = 0.0
    for c in join_codes:
        key = (str(geo), int(year), str(c))
        if key in lookup.index:
            total += float(lookup.loc[key])
            
    return total

def compute_impacts(shock: Union[float, dict], geo: str, year: Union[int, None], scope: Scope, join_codes: List[str], geo_scope: GeoScope = "all_provinces"):
    df = load_multipliers()
    if df.empty: return pd.DataFrame(), pd.DataFrame()

    mtype = SCOPE_TO_MULT_TYPE.get(scope, "Simple multiplier")

    # 1. Filter by Geography and Industry using Fast Index
    try:
        geo_subset = df.loc[(geo, mtype)]
        # loc can return a Series if there's only 1 row, ensure DataFrame
        if isinstance(geo_subset, pd.Series):
            geo_subset = geo_subset.to_frame().T
    except KeyError:
        return pd.DataFrame(), pd.DataFrame()

    mask = geo_subset["join_code"].isin(join_codes)
    
    # 0. Filter by geo_scope (all_provinces vs within_province)
    if geo != "Canada" and 'geo_scope' in geo_subset.columns:
        mask = mask & geo_subset['geo_scope'].isin([geo_scope, 'national'])

    broad_subset = geo_subset[mask].copy() 
    if broad_subset.empty: return pd.DataFrame(), pd.DataFrame()

    # 2. SMART ROW SELECTION (Per Industry)
    final_rows = []
    target_year = int(year) if year is not None else None
    # Q5 FIX: Collect per-code best_year BEFORE overwriting YEAR,
    # so weight lookups use the actual data vintage, not a future target.
    code_weight_year: dict[str, int] = {}

    for code in join_codes:
        ind_data = broad_subset[broad_subset["join_code"] == code]
        if ind_data.empty: continue
        
        avail_years = sorted(ind_data["YEAR"].unique())
        
        if target_year and target_year in avail_years:
            best_year = target_year
        elif avail_years:
            best_year = avail_years[-1]
        else:
            continue

        code_weight_year[code] = best_year  # Q5: remember actual vintage
        selected = ind_data[ind_data["YEAR"] == best_year].copy()
        if target_year:
            selected["YEAR"] = target_year
            
        final_rows.append(selected)
    
    if not final_rows: return pd.DataFrame(), pd.DataFrame()
    
    subset = pd.concat(final_rows)

    rows_dfs = []
    for yr, group_by_year in subset.groupby("YEAR"):
        unique_codes = group_by_year["join_code"].unique()
        n = len(unique_codes)
        if n == 0: continue
        
        # --- WEIGHTED SHOCK DISTRIBUTION ---
        val_map = {}
        if isinstance(shock, dict):
            # Manual precision (no weighting needed)
            val_map = {c: shock.get(c, 0.0) for c in unique_codes}
        else:
            # Q5 FIX: Fetch weights using each code's best_year (actual
            # data vintage), NOT the overwritten target_year.
            weights = {}
            total_basket_output = 0.0
            for c in unique_codes:
                weight_yr = code_weight_year.get(c, int(yr))
                w = get_actual_output(geo, weight_yr, [c])
                weights[c] = w
                total_basket_output += w
                
            for c in unique_codes:
                if total_basket_output > 0:
                    share = weights.get(c, 0.0) / total_basket_output
                    val_map[c] = shock * share
                else:
                    val_map[c] = shock / n
        
        # --- VECTORIZED COMPUTATION ---
        # Copy to avoid SettingWithCopyWarning
        group_by_year = group_by_year.copy()
        
        # Map shock values
        group_by_year["val_to_apply"] = group_by_year["join_code"].map(val_map)
        
        # Compute denominator
        is_jobs = group_by_year["variable"].astype(str).str.contains("Jobs", case=False, na=False)
        denom = np.where(is_jobs, 1_000_000.0, 1.0)
        
        # Calculate impact
        group_by_year["impact"] = (group_by_year["val_to_apply"] / denom) * group_by_year["value"]
        
        # Format output
        group_by_year["Year"] = int(yr)
        group_by_year["multiplier"] = group_by_year["value"]
        group_by_year["metric"] = group_by_year["variable"]
        
        if "industry_code" not in group_by_year.columns:
            group_by_year["industry_code"] = group_by_year["join_code"]
            
        needed_cols = ["Year", "industry_code", "industry_name", "metric", "multiplier", "impact"]
        
        # Cast categoricals to strings to avoid Pandas union_all bottlenecks during concat
        for col in ["industry_code", "industry_name", "metric", "multiplier"]:
            if col in group_by_year.columns and hasattr(group_by_year[col], "cat"):
                group_by_year[col] = group_by_year[col].astype(str)
                
        rows_dfs.append(group_by_year[needed_cols])

    if not rows_dfs: return pd.DataFrame(), pd.DataFrame()
    per_ind = pd.concat(rows_dfs, ignore_index=True)

    summ = per_ind.groupby(["metric", "Year"], as_index=False)["impact"].sum()
    summ.rename(columns={"impact": "impact_dollars"}, inplace=True)
    return per_ind, summ

def compute_breakdown(shock: Union[float, dict], geo: str, year: int, join_codes: List[str], geo_scope: GeoScope = "all_provinces") -> pd.DataFrame:
    df = load_multipliers()
    if df.empty: return pd.DataFrame()

    target_types = ["Direct multiplier", "Simple multiplier", "Total multiplier"]
    
    mask = (
        (df["GEO"] == geo) &
        (df["multiplier_type"].isin(target_types)) &
        (df["join_code"].isin(join_codes))
    )

    # 3. SMART ROW SELECTION (Per Industry)
    final_rows = []
    # N3 FIX: Port the code_weight_year pattern from compute_impacts().
    # Collect per-code best_year BEFORE overwriting YEAR, so weight
    # lookups use the actual data vintage, not a future target.
    code_weight_year: dict[str, int] = {}
    
    # We loop through requested codes and find best match for each
    broad_subset = df[mask].copy()
    if broad_subset.empty: return pd.DataFrame()

    for code in join_codes:
        ind_data = broad_subset[broad_subset["join_code"] == code]
        if ind_data.empty: continue
        
        avail_years = sorted(ind_data["YEAR"].unique())
        
        if year in avail_years:
            best_year = year
        elif avail_years:
            best_year = avail_years[-1]
        else:
            continue

        code_weight_year[code] = best_year  # N3: remember actual vintage
        selected = ind_data[ind_data["YEAR"] == best_year].copy()
        selected["YEAR"] = year  # Align to target year for UI
        final_rows.append(selected)
        
    if not final_rows: return pd.DataFrame()
    
    subset = pd.concat(final_rows)
    # ---------------------------

    unique_codes = subset["join_code"].unique()
    if len(unique_codes) == 0: return pd.DataFrame()
    
    # --- WEIGHTED SHOCK DISTRIBUTION ---
    if isinstance(shock, dict):
        is_precision = True
        weights = {}
        total_basket_output = 0.0
    else:
        is_precision = False
        weights = {}
        total_basket_output = 0.0
        for c in unique_codes:
            # N3 FIX: use vintage year for weight lookup
            weight_yr = code_weight_year.get(c, int(year))
            w = get_actual_output(geo, weight_yr, [c])
            weights[c] = w
            total_basket_output += w
    # --------------------------------------------
    
    rows_dfs = []
    
    # Pre-compute shock values per jcode
    val_map = {}
    if is_precision:
        val_map = {c: shock.get(c, 0.0) for c in unique_codes}
    else:
        for c in unique_codes:
            if total_basket_output > 0:
                share = weights.get(c, 0.0) / total_basket_output
                val_map[c] = shock * share
            else:
                val_map[c] = shock / len(unique_codes)

    # We need to compute Direct, Indirect, Induced for each join_code & variable.
    # Pivot to make multiplier types columns
    subset = subset.reset_index(drop=True)
    pivot_df = subset.pivot_table(
        index=["join_code", "variable"], 
        columns="multiplier_type", 
        values="value", 
        aggfunc='sum', 
        fill_value=0
    ).reset_index()
    
    for col in ["Direct multiplier", "Simple multiplier", "Total multiplier"]:
        if col not in pivot_df.columns:
            pivot_df[col] = 0.0

    pivot_df["Direct"] = pivot_df["Direct multiplier"]
    
    # N2 FIX: Guard against missing/suppressed Simple multiplier.
    pivot_df["Indirect"] = np.where(
        (pivot_df["Simple multiplier"] == 0) & (pivot_df["Total multiplier"] > 0),
        np.maximum(0, pivot_df["Total multiplier"] - pivot_df["Direct multiplier"]),
        np.maximum(0, pivot_df["Simple multiplier"] - pivot_df["Direct multiplier"])
    )
    
    pivot_df["Induced"] = np.where(
        (pivot_df["Simple multiplier"] == 0) & (pivot_df["Total multiplier"] > 0),
        0.0,
        np.maximum(0, pivot_df["Total multiplier"] - pivot_df["Simple multiplier"])
    )
    
    pivot_df["val_to_apply"] = pivot_df["join_code"].map(val_map)
    is_jobs = pivot_df["variable"].astype(str).str.contains("Jobs", case=False, na=False)
    pivot_df["denom"] = np.where(is_jobs, 1_000_000.0, 1.0)
    
    for t in ["Direct", "Indirect", "Induced"]:
        temp = pivot_df[["variable", t, "val_to_apply", "denom"]].copy()
        temp["Type"] = t
        temp["impact"] = (temp["val_to_apply"] / temp["denom"]) * temp[t]
        temp = temp.rename(columns={"variable": "metric"})
        rows_dfs.append(temp[["metric", "Type", "impact"]])
        
    return pd.concat(rows_dfs, ignore_index=True)


def compute_hlrf_breakdown(
    shock: float,
    geo: str,
    year: int,
    join_codes: List[str],
    hlrf_overrides: dict,
    geo_scope: GeoScope = "all_provinces",
) -> pd.DataFrame:
    """Compute D/I/I breakdown with HLRF (Hybrid Labor-Force Replacement) calibration.

    The HLRF approach replaces model-estimated Direct values with ground-truth
    actuals (e.g., OAG employment data), then scales Induced impacts by the
    wage ratio to correctly propagate the localized wage structure through
    household-spending channels.

    Parameters
    ----------
    shock : float
        The output shock in dollars (e.g., Farm Gate Value).
    geo, year, join_codes, geo_scope
        Standard engine parameters (see compute_breakdown).
    hlrf_overrides : dict
        Mapping of metric keywords to override values.
        Example: {'Jobs': 3924, 'Wages and salaries': 159_800_000}
        The keys are matched against the 'metric' column using substring search.

    Returns
    -------
    pd.DataFrame
        Same schema as compute_breakdown() output (metric, Type, impact),
        but with Direct values replaced and Induced values scaled by wage ratio.
    """
    # 1. Get the uncalibrated breakdown
    bd = compute_breakdown(shock, geo, year, join_codes, geo_scope=geo_scope)
    if bd.empty:
        return bd

    bd = bd.copy()

    # 2. Identify the wage metric row for ratio calculation
    wage_key = None
    for k in hlrf_overrides:
        if 'wage' in k.lower() or 'salaries' in k.lower():
            wage_key = k
            break

    # 3. Compute wage ratio (OAG actual / IO model direct)
    wage_ratio = 1.0
    if wage_key is not None:
        wage_mask = bd['metric'].astype(str).str.contains('wages', case=False, na=False) | \
                    bd['metric'].astype(str).str.contains('salaries', case=False, na=False)
        direct_wage_rows = bd[wage_mask & (bd['Type'] == 'Direct')]
        if not direct_wage_rows.empty:
            model_direct_wages = direct_wage_rows['impact'].sum()
            if model_direct_wages > 0:
                wage_ratio = hlrf_overrides[wage_key] / model_direct_wages

    # 4. Apply overrides to Direct values and scale Induced by wage ratio
    for override_key, override_val in hlrf_overrides.items():
        # Find matching metric rows
        key_lower = override_key.lower()
        if 'job' in key_lower:
            match_mask = bd['metric'].astype(str).str.contains('Jobs', case=False, na=False)
        elif 'wage' in key_lower or 'salaries' in key_lower:
            match_mask = bd['metric'].astype(str).str.contains('wages', case=False, na=False) | \
                         bd['metric'].astype(str).str.contains('salaries', case=False, na=False)
        else:
            match_mask = bd['metric'].astype(str).str.contains(override_key, case=False, na=False)

        # Replace Direct values with override
        direct_mask = match_mask & (bd['Type'] == 'Direct')
        if direct_mask.any():
            bd.loc[direct_mask, 'impact'] = override_val

    # 5. Scale ALL Induced impacts by wage ratio
    induced_mask = bd['Type'] == 'Induced'
    bd.loc[induced_mask, 'impact'] = bd.loc[induced_mask, 'impact'] * wage_ratio

    return bd


def compute_subsidy_impact(
    subsidy_dollars: float,
    geo: str,
    year: int,
    join_codes: List[str],
    geo_scope: GeoScope = "all_provinces",
) -> pd.DataFrame:
    """Compute Induced-only impact of government subsidy payments.

    Government transfers (Production Insurance, SDRM, AgriStability) do not
    generate supply-chain (Indirect) impacts — they are income transfers that
    farmers spend in their communities. This function isolates only the
    Induced (household spending) channel.

    Parameters
    ----------
    subsidy_dollars : float
        Total government transfer amount in dollars.
    geo, year, join_codes, geo_scope
        Standard engine parameters.

    Returns
    -------
    pd.DataFrame
        Same schema as compute_breakdown(), but Direct and Indirect are
        zeroed out. Only Induced impacts are non-zero.
    """
    bd = compute_breakdown(subsidy_dollars, geo, year, join_codes, geo_scope=geo_scope)
    if bd.empty:
        return bd

    bd = bd.copy()

    # Zero out Direct and Indirect — subsidies only flow through Induced
    non_induced_mask = bd['Type'].isin(['Direct', 'Indirect'])
    bd.loc[non_induced_mask, 'impact'] = 0.0

    return bd


# ==============================================================================
# COUNTY-LEVEL IMPACT ESTIMATION (Ontario Only)
# ==============================================================================
# Methodology: Apportion provincial IO impacts by county Farm Cash Receipt (FCR)
# share. FCR is used as a proxy for Output at the sub-provincial level.
# Source: OMAFRA Ontario Farm Cash Receipts by County & Commodity
# ==============================================================================

_COUNTY_FCR_FP = BASE_DIR / "data" / "latest" / "omafra_county_fcr.csv"

@lru_cache(maxsize=1)
def load_county_fcr() -> pd.DataFrame:
    """Load processed OMAFRA county-level farm cash receipt data."""
    if not _COUNTY_FCR_FP.exists():
        return pd.DataFrame()
    df = smart_read(_COUNTY_FCR_FP)
    return df


def available_county_years() -> list[int]:
    """Return years with county FCR data."""
    df = load_county_fcr()
    if df.empty:
        return []
    return sorted(df["year"].unique().astype(int).tolist())


def available_counties(year: Optional[int] = None) -> list[dict]:
    """Return list of counties with display names for a given year.
    
    Returns list of dicts: [{"slug": "huron", "display": "Huron County", "region": "Western Ontario"}, ...]
    """
    df = load_county_fcr()
    if df.empty:
        return []
    if year:
        df = df[df["year"] == year]
    totals = df[df["commodity"] == "Total"].drop_duplicates(subset=["county"])
    return [
        {"slug": r["county"], "display": r["county_display"], "region": r["region"]}
        for _, r in totals.sort_values("county_display").iterrows()
    ]


def compute_county_impacts(
    year: int,
    scope: Scope,
    geo_scope: GeoScope = "all_provinces",
) -> pd.DataFrame:
    """Estimate county-level economic impacts for Ontario Primary Agriculture.
    
    Methodology:
    1. Compute provincial Ontario impacts for primary_agriculture basket
    2. Load county FCR shares for the given year
    3. Apportion each provincial metric by county share
    
    Returns DataFrame with columns:
        county, county_display, region, year, metric,
        provincial_impact, county_share, county_impact
    """
    # Step 1: Get the provincial primary agriculture impacts
    baskets = load_baskets_config()
    prim_ag = baskets.get("primary_agriculture", {})
    if not prim_ag:
        return pd.DataFrame()
    
    # Get primary agriculture codes
    basket_df = industries_for_basket("primary_agriculture")
    if basket_df.empty:
        return pd.DataFrame()
    codes = basket_df["join_code"].tolist()
    
    # Build per-code shock dict using actual historical output
    shock_dict = {}
    for c in codes:
        shock_dict[c] = get_actual_output("Ontario", year, [c])
    
    # Compute provincial impacts
    _, prov_sum = compute_impacts(shock_dict, "Ontario", year, scope, codes, geo_scope=geo_scope)
    if prov_sum is None or prov_sum.empty:
        return pd.DataFrame()
    
    # Step 2: Load county FCR shares
    fcr = load_county_fcr()
    if fcr.empty:
        return pd.DataFrame()
    
    county_totals = fcr[(fcr["year"] == year) & (fcr["commodity"] == "Total")]
    if county_totals.empty:
        # Try nearest year
        avail = sorted(fcr["year"].unique())
        if not avail:
            return pd.DataFrame()
        nearest = min(avail, key=lambda y: abs(y - year))
        county_totals = fcr[(fcr["year"] == nearest) & (fcr["commodity"] == "Total")]
    
    # Step 3: Apportion
    rows = []
    for _, county_row in county_totals.iterrows():
        county_share = county_row["share_of_province"]
        for _, metric_row in prov_sum.iterrows():
            rows.append({
                "county": county_row["county"],
                "county_display": county_row["county_display"],
                "region": county_row["region"],
                "year": year,
                "metric": metric_row["metric"],
                "provincial_impact": metric_row["impact_dollars"],
                "county_share": county_share,
                "county_impact": metric_row["impact_dollars"] * county_share,
                "fcr_millions": county_row["value_millions"],
            })
    
    return pd.DataFrame(rows)


def get_county_commodity_breakdown(county_slug: str, year: int) -> pd.DataFrame:
    """Get commodity-level FCR breakdown for a specific county.
    
    Returns DataFrame with columns: commodity, value_millions, share_of_county_total
    """
    fcr = load_county_fcr()
    if fcr.empty:
        return pd.DataFrame()
    
    county_data = fcr[(fcr["county"] == county_slug) & (fcr["year"] == year)]
    if county_data.empty:
        return pd.DataFrame()
    
    # Get total and individual commodities
    total_row = county_data[county_data["commodity"] == "Total"]
    items = county_data[county_data["commodity"] != "Total"].copy()
    
    if total_row.empty or items.empty:
        return pd.DataFrame()
    
    total_val = total_row["value_millions"].values[0]
    items = items[items["value_millions"] > 0].copy()
    items["share_of_county_total"] = items["value_millions"] / total_val if total_val > 0 else 0
    items = items[["commodity", "value_millions", "share_of_county_total"]].sort_values(
        "value_millions", ascending=False
    )
    
    return items