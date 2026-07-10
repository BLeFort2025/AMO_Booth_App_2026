import sys
from pathlib import Path

# Ensure project root is on sys.path (needed for Streamlit Cloud page loading)
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
import pandas as pd
from app.smart_read import smart_read
import altair as alt
import re
from app.smart_read import smart_read

# Import Engine
from scripts.io_multipliers_engine import (
    available_geographies,
    available_years,
    available_industries,
    industries_for_basket,
    get_actual_output,
    get_available_historical_codes,
    compute_impacts,
    compute_breakdown,
    load_baskets_config,  # Added for share coefficient
    load_multipliers,     # Added for Methodology & Audit tab
    Scope,
    # County-level estimation (Ontario only)
    available_county_years,
    available_counties,
    compute_county_impacts,
    get_county_commodity_breakdown,
    load_county_fcr,
)

# Imports for Inflation Logic
from scripts.fetch_statcan import fetch_table
from app.cpi_utils import load_cpi_deflators

# Report Generator is lazy-imported inside the Report tab to avoid
# loading matplotlib, python-docx, and python-pptx on every page load
# (~50-80 MB baseline memory savings on Streamlit Cloud).

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Economic Impact Multipliers",
    page_icon="📈",
    layout="wide"
)

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()


# --- CUSTOM CSS ---
st.markdown("""
<style>
    /* Page layout */
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    
    /* Metric cards */
    div[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; color: var(--text-color); }
    div[data-testid="stMetricLabel"] { font-size: 0.85rem; color: var(--text-color); opacity: 0.85; font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }
    div[data-testid="stMetricDelta"] { font-size: 0.8rem; }
    
    /* KPI section containers */
    .kpi-section {
        background: var(--secondary-background-color);
        border-radius: 12px;
        padding: 1rem 1.2rem 0.8rem;
        border: 1px solid rgba(128, 128, 128, 0.2);
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        margin-bottom: 0.5rem;
    }
    .kpi-section h5 { margin-top: 0 !important; color: var(--text-color); }
    
    /* Accent borders for KPI sections */
    .kpi-economic { border-left: 4px solid #2563eb; }
    .kpi-labour { border-left: 4px solid #059669; }
    .kpi-trade { border-left: 4px solid #7c3aed; }
    .kpi-capex { border-left: 4px solid #d97706; }
    
    /* Styled narrative box */
    .narrative-box {
        background: var(--secondary-background-color);
        padding: 1.5rem 1.8rem;
        border-radius: 12px;
        border-left: 5px solid #059669;
        border: 1px solid rgba(128, 128, 128, 0.2);
        margin: 1rem 0 1.5rem;
        line-height: 1.7;
        color: var(--text-color);
    }
    .narrative-box h3 { color: var(--text-color); margin-bottom: 0.8rem; }
    .narrative-box ul { margin-bottom: 0.5rem; }
    .narrative-box li { margin-bottom: 0.3rem; }
    
    /* Context banner */
    .context-banner {
        background: var(--primary-color);
        color: white;
        padding: 0.6rem 1.2rem;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 2rem;
        margin-bottom: 1.2rem;
        font-size: 0.9rem;
    }
    .context-banner .badge {
        background: rgba(255,255,255,0.15);
        padding: 0.25rem 0.7rem;
        border-radius: 20px;
        font-weight: 600;
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text-color);
        margin: 1.5rem 0 0.8rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(128, 128, 128, 0.2);
    }
    
    /* Data source caption */
    .source-note {
        font-size: 0.75rem;
        color: var(--text-color);
        opacity: 0.7;
        font-style: italic;
        margin-top: -0.3rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 Economic Impact Multipliers")
st.markdown("""
**Policy Context:** Quantify the ripple effects of agricultural investments using Statistics Canada Input-Output multipliers.
""")

# ── Phase 4C: Session-State Scenario Memory ──────────────────────────
if "saved_scenarios" not in st.session_state:
    st.session_state["saved_scenarios"] = []

# ==============================================================================
# 🏗️ LOGIC & HELPER FUNCTIONS
# ==============================================================================

def render_scenario_sidebar(key_suffix, label, show_header=True):
    if show_header:
        st.sidebar.markdown(f"### {label}")
    
    geos = available_geographies()
    idx = geos.index("Ontario") if "Ontario" in geos else 0
    geo = st.sidebar.selectbox(f"Geography ({label})", geos, index=idx, key=f"geo_{key_suffix}")

    basket_mode = st.sidebar.radio(
        f"Select Economic Sector ({label})", 
        ["Economic Sector Grouping", "Single Industry"], 
        key=f"mode_{key_suffix}"
    )

    selected_codes = []
    basket_name = ""
    b_key = None  # Initialize for share coefficient lookup

    if basket_mode == "Economic Sector Grouping":
        # UPDATE: Aligned with new Granular Config (Feb 2026)
        baskets = {
            "total_food_system": "Entire Food System",
            "aafc_food_system": "🇨🇦 Food System",
            "cfa_food_system": "Agri-Food Production (Core)",
            "primary_agriculture": "Primary Agriculture",
            "food_beverage_manufacturing": "Food & Beverage Manufacturing",
            "foodservice": "Foodservice",
            # Wholesale & Retail
            "agri_wholesale_retail": "Wholesale & Retail (Food Stores)",
            "agri_food_wholesale": "Food & Bev Wholesalers",
            # Input Sectors
            "agri_inputs_fertilizer": "Agri-Inputs (Fertilizer/Chem)",
            "agri_inputs_machinery": "Agri-Inputs (Machinery)",
            # Transport Sectors
            "agri_transport_rail": "Rail Transportation (Ag-Share)",
            "agri_transport_truck": "Truck Transportation (Ag-Share)",
        }
        b_key = st.sidebar.selectbox(
            f"Economic Sector ({label})", 
            options=list(baskets.keys()), 
            format_func=lambda x: baskets[x],
            key=f"basket_select_{key_suffix}"
        )
        if b_key:
            _b_cfg = load_baskets_config().get(b_key, {})
            if _b_cfg.get("weight_type") == "composite":
                # Composite basket: collect codes from all component baskets
                _comp_frames = []
                for comp_key in _b_cfg.get("components", []):
                    comp_df = industries_for_basket(comp_key)
                    if not comp_df.empty:
                        _comp_frames.append(comp_df)
                if _comp_frames:
                    basket_df = pd.concat(_comp_frames).drop_duplicates(subset="join_code")
                    selected_codes = basket_df["join_code"].tolist()
                    basket_name = baskets[b_key]
                    with st.sidebar.expander(f"View Components ({len(_b_cfg.get('components', []))} sectors)"):
                        for comp_key in _b_cfg.get("components", []):
                            comp_cfg = load_baskets_config().get(comp_key, {})
                            comp_label = comp_cfg.get("label", comp_key)
                            comp_share = comp_cfg.get("calculated_share", 1.0)
                            share_tag = f" (Ag-Share: {comp_share:.1%})" if comp_share < 1.0 else ""
                            st.markdown(f"- **{comp_label}**{share_tag}")
            else:
                basket_df = industries_for_basket(b_key)
                if not basket_df.empty:
                    selected_codes = basket_df["join_code"].tolist()
                    basket_name = baskets[b_key]
                    with st.sidebar.expander(f"View Sector Components ({len(selected_codes)} industries)"):
                        st.dataframe(basket_df[["join_code", "industry_name"]], hide_index=True)

    else:
        years_avail = available_years(geo)
        ref_year = years_avail[-1] if years_avail else 2020
        inds = available_industries(geo, ref_year)
        ind_str = st.sidebar.selectbox(f"Industry ({label})", inds, key=f"ind_select_{key_suffix}")
        
        if ind_str:
            match = re.search(r"\[(.*?)\]", ind_str)
            if match:
                selected_codes = [match.group(1)]
                basket_name = ind_str.split(" [")[0]

    return {
        "geo": geo, "codes": selected_codes, "name": basket_name, "basket_mode": basket_mode,
        "basket_key": b_key  # For share coefficient lookup
    }

def run_scenario(scen_data, year_target, shock_val, geo_scope="all_provinces"):
    if not scen_data["codes"]: return None, None
    
    if use_hist:
        if analysis_mode == "Single Year":
            shock_dict = {}
            for c in scen_data["codes"]:
                val = get_actual_output(scen_data["geo"], year_target, [c])
                shock_dict[c] = val
            return compute_impacts(
                shock_dict, scen_data["geo"], year_target, scope_map[scope_label], scen_data["codes"], geo_scope=geo_scope
            )
        else:
            all_years = available_years(scen_data["geo"])
            results = []
            for y in all_years:
                shock_dict = {}
                total_check = 0
                for c in scen_data["codes"]:
                    val = get_actual_output(scen_data["geo"], y, [c])
                    shock_dict[c] = val
                    total_check += val
                
                if total_check == 0: continue
                
                df, summ = compute_impacts(
                    shock_dict, scen_data["geo"], y, scope_map[scope_label], scen_data["codes"], geo_scope=geo_scope
                )
                if not summ.empty:
                    summ["Year"] = y
                    results.append(summ)
            
            if results: return None, pd.concat(results)
            return None, pd.DataFrame()
            
    else:
        return compute_impacts(
            shock_val, scen_data["geo"], year_target, scope_map[scope_label], scen_data["codes"], geo_scope=geo_scope
        )

def enforce_strict_definitions(df):
    if df is None or df.empty: return df
    gdp_mask = df["metric"].astype(str).str.contains("Gross domestic", case=False, na=False)
    basic_mask = df["metric"].astype(str).str.contains("basic prices", case=False, na=False)
    drop_mask = gdp_mask & (~basic_mask)
    df = df[~drop_mask].copy()
    return df

def apply_inflation(df):
    if df.empty or not adjust_inflation: return df
    if "Year" not in df.columns: return df
    
    try:
        cpi_df = load_cpi_deflators(geo="Canada", _load_table_fn=fetch_table)
        if cpi_df.empty: return df
        if "GEO" in cpi_df.columns:
             cpi_df = cpi_df[cpi_df["GEO"] == "Canada"]
        
        cpi_map = dict(zip(cpi_df["YEAR"], cpi_df["cpi"]))
        if not cpi_map: return df
        
        base_yr = 2022
        base_cpi = cpi_map.get(base_yr)
        if not base_cpi:
            base_yr = max(cpi_map.keys())
            base_cpi = cpi_map.get(base_yr)
        
        def adjust(row):
            y = row.get("Year")
            val = row.get("impact_dollars", 0)
            # Q4 FIX: Physical metrics (Jobs, Hours) are headcounts, not dollars.
            # Applying monetary CPI scaling to them is economically meaningless.
            metric_str = str(row.get("metric", "")).lower()
            if any(k in metric_str for k in ["jobs", "hours", "fte", "employment"]):
                return val  # Physical count — do not inflate
            cpi_y = cpi_map.get(y)
            if cpi_y and cpi_y > 0:
                return val * (base_cpi / cpi_y)
            return val
            
        df["impact_dollars"] = df.apply(adjust, axis=1)
    except: pass
    return df

def get_metric(df, m): 
    if df.empty: return 0.0
    subset = df[df["metric"].astype(str).str.contains(m, case=False, na=False)]
    if "gross domestic" in m.lower():
        subset = subset[subset["metric"].astype(str).str.contains("basic prices", case=False, na=False)]
    return subset["impact_dollars"].sum()

def get_job_quality(df):
    if df.empty: return 0.0
    wages = get_metric(df, "Wages")
    if wages == 0: wages = get_metric(df, "Labour") 
    jobs = get_metric(df, "Jobs")
    return wages / jobs if jobs else 0.0

# ---------------------------------------------------------
# FIX: ROBUST KEYWORD FETCHER (Catches Varied Variable Names)
# ---------------------------------------------------------
def sum_by_keywords(df, keywords, col="metric", val_col="impact_dollars"):
    """Sum values where column contains ANY of the keywords (Case Insensitive)."""
    if df.empty: return 0.0
    keywords_lower = [k.lower() for k in keywords]
    mask = df[col].astype(str).str.lower().apply(lambda x: any(k in x for k in keywords_lower))
    return df.loc[mask, val_col].sum()

# -----------------------------------------------------------------------------
# N4 FIX: Deterministic crosswalk for StatCan alphanumeric IO codes.
# These codes use letter suffixes to denote semantic sub-sector boundaries.
# Blind regex stripping causes billion-dollar attribution errors (e.g.,
# 111CL → 111 captures all crops instead of just Cannabis).
# Standard numeric codes fall through to the regex-numeric path safely.
# -----------------------------------------------------------------------------
_STATCAN_CROSSWALK: dict[str, list[str]] = {
    # N5 FIX: Enumerate 1119 sub-codes explicitly to exclude cannabis
    # (111993/111994). Using "1119" as prefix would subsume cannabis.
    "111A":  [
        "1111", "1112", "1113",                     # Oilseed/grain, Vegetable, Fruit
        "11191", "11192", "11193", "11194",          # Tobacco, Cotton, Sugarcane, Hay
        "111991", "111992", "111999",                # Sugar beet, Peanut, All Other (excl Cannabis)
    ],
    "1114A": ["1114"],                                # Greenhouse & nursery
    "111CL": ["111993", "111994"],                    # Licensed Cannabis (cover + open)
    "111CU": ["111993", "111994"],                    # Unlicensed Cannabis (same NAICS)
    # N6 FIX: 112A = "Animal production except aquaculture" in StatCan IO.
    # Simplified to parent "112" for capex compatibility (capex data only has
    # 3-digit codes). Aquaculture (1125) is included at the capex level due
    # to data granularity limits — this is a known trade-off, not an error.
    "112A":  ["112"],                                 # Animal production (capex-safe)
    "115A":  ["1151", "1152"],                        # Ag support (excl 1153 Forestry)
    "312A":  ["3121"],                                # Beverage mfg (excl 3122 Tobacco)
    "3121A": ["3121"],                                # Beverage sub-aggregate
}

def _io_to_trade_prefixes(io_codes: list) -> set:
    """Convert IO join_codes to trade/capex NAICS prefixes using crosswalk."""
    prefixes = set()
    for c in io_codes:
        clean = str(c).replace("BS", "").replace("GS", "")
        # 1. Check crosswalk for known alphanumeric codes first
        if clean in _STATCAN_CROSSWALK:
            for p in _STATCAN_CROSSWALK[clean]:
                prefixes.add(p)
            continue
        # 2. Safe fallback: strip alphabetic chars for standard numeric codes
        # N7 FIX: Preserve full numeric length (no truncation) so user
        # granularity (e.g., 31211 Beverage sub-sector) is not destroyed.
        numeric_only = re.sub(r'[^0-9]', '', clean)
        if numeric_only:
            prefixes.add(numeric_only)
    return prefixes

# -----------------------------------------------------------------------------
# STRICT GEO EXPORT FETCHER (Parent Dominance + Strict Geo)
# -----------------------------------------------------------------------------
@st.cache_data(max_entries=3, ttl=1800)
def get_export_value(geo, year, io_codes):
    """Fetches Export value with Parent Dominance + Strict Geography filter."""
    try:
        p = Path("data/latest/trade_subset.csv")
        if not p.exists(): return 0.0
        df = smart_read(p)
        
        # 1. STRICT Geography Filter
        # If we want a Province, we must find that exact Province.
        # If missing, return 0.0 (Do NOT fallback to Canada).
        df = df[df["Year"] == int(year)]
        
        if geo == "Canada":
            if "Canada" in df["GEO"].unique():
                df = df[df["GEO"] == "Canada"]
        else:
            # Provincial Request
            if geo in df["GEO"].unique():
                df = df[df["GEO"] == geo]
            else:
                return 0.0  # Data unavailable for this province -> Return 0
        
        # N4 FIX: Use deterministic crosswalk for alphanumeric IO codes,
        # with regex fallback for standard numeric codes.
        target_prefixes = _io_to_trade_prefixes(io_codes)
        
        if not target_prefixes: return 0.0
        
        # 3. Find All Potential Matches
        df["str_code"] = df["naics_code"].astype(str)
        mask_broad = df["str_code"].apply(lambda x: any(x.startswith(p) for p in target_prefixes))
        potential_matches = df[mask_broad].copy()
        
        if potential_matches.empty: return 0.0
        
        # 4. PARENT DOMINANCE FILTER (Prevent Double Counting)
        unique_codes = potential_matches["str_code"].unique()
        final_codes = set()
        for c in unique_codes:
            # Only keep 'c' if it is NOT a child of another code in the list
            is_child = any(c != p and c.startswith(p) for p in unique_codes)
            if not is_child:
                final_codes.add(c)
        
        return potential_matches[potential_matches["str_code"].isin(final_codes)]["VALUE"].sum()
    except Exception:
        return 0.0

# -----------------------------------------------------------------------------
# STRICT GEO INVESTMENT FETCHER (Strict Geo)
# -----------------------------------------------------------------------------
@st.cache_data(max_entries=3, ttl=1800)
def get_investment_value(geo, year, io_codes):
    """Fetches CAPEX with Strict Geography filter."""
    try:
        p = Path("data/latest/capex_subset.csv")
        if not p.exists(): return 0.0
        df = smart_read(p)
        
        # 1. STRICT Geography Filter
        df = df[df["Year"] == int(year)]
        
        if geo == "Canada":
            if "GEO" in df.columns and "Canada" in df["GEO"].unique():
                df = df[df["GEO"] == "Canada"]
        else:
            if "GEO" in df.columns and geo in df["GEO"].unique():
                df = df[df["GEO"] == geo]
            else:
                return 0.0  # Return 0 if provincial data missing
        
        # N4 FIX: Use deterministic crosswalk (same as exports)
        prefixes = _io_to_trade_prefixes(io_codes)
        mask = df["naics_code"].astype(str).apply(lambda x: any(str(x).startswith(p) for p in prefixes))
        
        return df[mask]["VALUE"].sum() * 1_000_000
    except Exception:
        return 0.0

def truncate_label(text, limit=15):
    if len(text) > limit: return text[:limit] + "..."
    return text

def format_compact(val):
    if val >= 1_000_000_000: return f"${val/1_000_000_000:.1f}B"
    if val >= 1_000_000: return f"${val/1_000_000:.1f}M"
    if val >= 1_000: return f"${val/1_000:.0f}k"
    return f"${val:,.0f}"

# ==============================================================================
# 🎛️ SIDEBAR CONTROLS
# ==============================================================================

st.sidebar.header("⚙️ Simulation Settings")

analysis_mode = st.sidebar.radio("Analysis Mode", ["Single Year", "Over Time"], horizontal=True)
compare_mode = st.sidebar.checkbox("Compare Scenarios?", value=False)

st.sidebar.markdown("---")
scen_a = render_scenario_sidebar("A", "Scenario A", show_header=True)

scen_b = None
if compare_mode:
    st.sidebar.markdown("---")
    scen_b = render_scenario_sidebar("B", "Scenario B", show_header=True)

# Parameters
st.sidebar.markdown("### 🎚️ Parameters")

target_year_a = None
target_year_b = None
date_range = None

if analysis_mode == "Single Year":
    years_a = available_years(scen_a["geo"])
    min_y, max_y = (min(years_a), max(years_a)) if years_a else (2010, 2022)
    target_year_a = st.sidebar.slider("Year (Scenario A)", min_y, max_y, max_y, key="slider_a")
    
    if compare_mode and scen_b:
        years_b = available_years(scen_b["geo"])
        min_yb, max_yb = (min(years_b), max(years_b)) if years_b else (2010, 2022)
        target_year_b = st.sidebar.slider("Year (Scenario B)", min_yb, max_yb, max_yb, key="slider_b")
    else:
        target_year_b = target_year_a

else:
    years_a = available_years(scen_a["geo"])
    if not years_a: years_a = [2010, 2022]
    min_y, max_y = int(min(years_a)), int(max(years_a))
    date_range = st.sidebar.slider("Date Range", min_y, max_y, (min_y, max_y), key="date_range_slider")

use_hist = st.sidebar.checkbox("Use Actual Historical Output?", value=True)
shock_input = 1_000_000.0

if not use_hist:
    shock_input = st.sidebar.number_input("Shock Amount ($)", value=1_000_000.0, step=100_000.0)

adjust_inflation = st.sidebar.checkbox("Adjust for Inflation (2022 Dollars)?", value=False)

scope_label = st.sidebar.radio("Impact Scope", ["Direct", "Direct + Indirect", "Direct + Indirect + Induced"], index=1)
scope_map = {
    "Direct": "direct", "Direct + Indirect": "direct_indirect", "Direct + Indirect + Induced": "direct_indirect_induced"
}

# --- SCOPE LOCK: Composite economic sectors force Direct scope to prevent IO double-counting ---
_active_basket_cfg = {}
if scen_a.get("basket_key"):
    _active_basket_cfg = load_baskets_config().get(scen_a["basket_key"], {})
    if _active_basket_cfg.get("scope_lock") == "direct":
        scope_label = "Direct"
        st.sidebar.info(
            "🔒 **Scope locked to Direct** for the Entire Food System basket. "
            "This prevents double-counting across overlapping supply chains."
        )

# Provincial multiplier scope toggle (only for provinces, not Canada)
prov_scope_key = "all_provinces"  # default
if scen_a["geo"] != "Canada":
    _prov_scope_label = st.sidebar.radio(
        "Provincial Multiplier Scope",
        ["All Provinces", "Within Province"],
        index=0,
        help=(
            "'All Provinces' includes inter-provincial supply chain effects "
            "(e.g., Ontario farms buying Saskatchewan inputs). "
            "'Within Province' restricts to impacts retained within the selected province."
        )
    )
    prov_scope_key = "all_provinces" if _prov_scope_label == "All Provinces" else "within_province"

# ── Phase 4C: Scenario Save/Recall UI ────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown("### 💾 Scenario Memory")

# Save current scenario
_save_name = st.sidebar.text_input(
    "Scenario Name", value="", placeholder="e.g. Ontario Crops 2022",
    key="_scenario_save_name", max_chars=40
)
if st.sidebar.button("💾 Save Current Scenario", key="_save_btn"):
    if _save_name.strip():
        _snapshot = {
            "name": _save_name.strip(),
            "geo": scen_a["geo"],
            "industry": scen_a["name"],
            "basket_mode": scen_a.get("basket_mode", "N/A"),
            "year": target_year_a,
            "scope": scope_label,
            "use_hist": use_hist,
            "shock": shock_input if not use_hist else "Historical",
            "inflation_adj": adjust_inflation,
        }
        # Cap at 5 — evict oldest
        saved = st.session_state["saved_scenarios"]
        saved.append(_snapshot)
        if len(saved) > 5:
            saved.pop(0)
        st.sidebar.success(f"Saved: {_save_name}")
    else:
        st.sidebar.warning("Enter a name first.")

# Display saved scenarios
if st.session_state["saved_scenarios"]:
    with st.sidebar.expander(f"📂 Saved Scenarios ({len(st.session_state['saved_scenarios'])})", expanded=False):
        for i, snap in enumerate(st.session_state["saved_scenarios"]):
            _yr = snap.get('year', 'N/A')
            _shock_display = snap.get('shock', 'N/A')
            if isinstance(_shock_display, (int, float)):
                _shock_display = f"${_shock_display:,.0f}"
            st.markdown(
                f"**{i+1}. {snap['name']}**  \n"
                f"📍 {snap['geo']} · 🏭 {snap['industry']}  \n"
                f"📅 {_yr} · 🔬 {snap['scope']}  \n"
                f"💰 Shock: {_shock_display} · 📊 Inflation: {'Yes' if snap.get('inflation_adj') else 'No'}"
            )
            st.markdown("---")
        if st.button("🗑️ Clear All", key="_clear_saved"):
            st.session_state["saved_scenarios"] = []
            st.rerun()

# ==============================================================================
# 🚀 EXECUTION & RESULTS
# ==============================================================================

# --- COMPOSITE BASKET: Sum Direct impacts of each component basket ---
def _run_composite(scen_data, year_target, geo_scope):
    """Run each component basket at Direct scope, apply its ag-share, and sum."""
    comp_keys = _active_basket_cfg.get("components", [])
    all_sum_parts = []
    all_res_parts = []
    for comp_key in comp_keys:
        comp_cfg = load_baskets_config().get(comp_key, {})
        comp_codes = industries_for_basket(comp_key)["join_code"].tolist()
        if not comp_codes:
            continue
        share = comp_cfg.get("calculated_share", 1.0)
        # Build per-code shock dict using actual historical output
        shock_dict = {}
        for c in comp_codes:
            shock_dict[c] = get_actual_output(scen_data["geo"], year_target, [c])
        comp_res, comp_sum = compute_impacts(
            shock_dict, scen_data["geo"], year_target, "direct", comp_codes, geo_scope=geo_scope
        )
        if comp_sum is not None and not comp_sum.empty:
            # Apply basket-level ag-share coefficient
            if share != 1.0:
                comp_sum["impact_dollars"] *= share
            all_sum_parts.append(comp_sum)
        if comp_res is not None and not comp_res.empty:
            if share != 1.0:
                comp_res["impact"] *= share
            all_res_parts.append(comp_res)
    if all_sum_parts:
        combined_sum = pd.concat(all_sum_parts)
        combined_sum = combined_sum.groupby(["metric"], as_index=False)["impact_dollars"].sum()
        combined_sum["Year"] = year_target
        combined_res = pd.concat(all_res_parts) if all_res_parts else pd.DataFrame()
        return combined_res, combined_sum
    return pd.DataFrame(), pd.DataFrame()

_is_composite = _active_basket_cfg.get("weight_type") == "composite"

if _is_composite:
    res_a, sum_a = _run_composite(scen_a, target_year_a, prov_scope_key)
else:
    res_a, sum_a = run_scenario(scen_a, target_year_a, shock_input, geo_scope=prov_scope_key)

sum_b = pd.DataFrame()
if compare_mode and scen_b:
    _, sum_b = run_scenario(scen_b, target_year_b, shock_input, geo_scope=prov_scope_key)

sum_a = enforce_strict_definitions(sum_a)
if not sum_b.empty: sum_b = enforce_strict_definitions(sum_b)

if sum_a is None or sum_a.empty:
    st.info("👈 Please select an industry or basket in the sidebar to view results.")
    st.stop()

sum_a = apply_inflation(sum_a)
if not sum_b.empty and scen_b: sum_b = apply_inflation(sum_b)

if analysis_mode == "Over Time" and date_range:
    sum_a = sum_a[(sum_a["Year"] >= date_range[0]) & (sum_a["Year"] <= date_range[1])]
    if not sum_b.empty:
        sum_b = sum_b[(sum_b["Year"] >= date_range[0]) & (sum_b["Year"] <= date_range[1])]
    # Q7 FIX: For KPI metrics, scope to the latest year only.
    # Summing overlapping annual snapshots into one cumulative figure is misleading.
    if not sum_a.empty and "Year" in sum_a.columns:
        _latest_yr = sum_a["Year"].max()
        sum_a_latest = sum_a[sum_a["Year"] == _latest_yr]
    else:
        sum_a_latest = sum_a

# ==============================================================================
# 🎨 VISUALIZATION LAYER
# ==============================================================================

_CLEAN_THEME_CONFIG = {
    "config": {
        "view": {"stroke": "transparent"},
        "axis": {
            "labelFontSize": 11, "titleFontSize": 12, "titlePadding": 15,
            "labelLimit": 150, "gridColor": "#f0f0f0", "domainColor": "#ccc",
            "tickColor": "#ddd"
        },
        "legend": {"titleFontSize": 11, "labelFontSize": 11, "symbolSize": 100},
        "bar": {"cornerRadiusTopRight": 4, "cornerRadiusBottomRight": 4},
        "title": {"fontSize": 14, "fontWeight": 600}
    }
}

# Altair 5.6+ replaced alt.themes (plural) with alt.theme (singular).
# Use new API if available, fall back to legacy for older installs.
try:
    @alt.theme.register("clean", enable=True)
    def theme_clean():
        return _CLEAN_THEME_CONFIG
except AttributeError:
    def theme_clean():
        return _CLEAN_THEME_CONFIG
    alt.themes.register("clean", theme_clean)
    alt.themes.enable("clean")

if analysis_mode == "Single Year":
    
    # 1. PRE-CALCULATE BREAKDOWN
    if _is_composite:
        # Composite basket: all impact is Direct (scope-locked), so build breakdown from sum_a
        bd_a = pd.DataFrame()
        if sum_a is not None and not sum_a.empty:
            rows = []
            for _, r in sum_a.iterrows():
                rows.append({
                    "metric": r["metric"],
                    "Type": "Direct",
                    "impact_dollars": r["impact_dollars"],
                    "impact": r["impact_dollars"],  # Alias for chart compatibility
                    "Year": r.get("Year", target_year_a)
                })
            bd_a = pd.DataFrame(rows)
    else:
        final_shock_a = shock_input
        if use_hist:
                final_shock_a = {}
                for c in scen_a["codes"]:
                    final_shock_a[c] = get_actual_output(scen_a["geo"], target_year_a, [c])

        bd_a = compute_breakdown(final_shock_a, scen_a["geo"], target_year_a, scen_a["codes"], geo_scope=prov_scope_key)
    
    if adjust_inflation and not bd_a.empty:
        try:
            cpi_df = load_cpi_deflators(geo="Canada", _load_table_fn=fetch_table)
            cpi_map = dict(zip(cpi_df["YEAR"], cpi_df["cpi"]))
            base = cpi_map.get(2022)
            curr = cpi_map.get(target_year_a)
            if base and curr: bd_a["impact"] = bd_a["impact"] * (base/curr)
        except: pass
    
    bd_b = pd.DataFrame()
    if compare_mode and scen_b:
        final_shock_b = shock_input
        if use_hist:
            final_shock_b = {}
            for c in scen_b["codes"]:
                final_shock_b[c] = get_actual_output(scen_b["geo"], target_year_b, [c])
        
        bd_b = compute_breakdown(final_shock_b, scen_b["geo"], target_year_b, scen_b["codes"], geo_scope=prov_scope_key)
        if adjust_inflation and not bd_b.empty:
            try:
                cpi_df = load_cpi_deflators(geo="Canada", _load_table_fn=fetch_table)
                cpi_map = dict(zip(cpi_df["YEAR"], cpi_df["cpi"]))
                base = cpi_map.get(2022)
                curr = cpi_map.get(target_year_b)
                if base and curr: bd_b["impact"] = bd_b["impact"] * (base/curr)
            except: pass

    # 2. METRICS ENGINE
    # --- SHARE COEFFICIENT: Apply basket weighting for Ag-Share sectors ---
    share_coef_a = 1.0
    share_badge_a = ""
    if scen_a.get("basket_key"):
        basket_cfg = load_baskets_config().get(scen_a["basket_key"], {})
        share_coef_a = basket_cfg.get("calculated_share", 1.0)
        if share_coef_a < 1.0:
            share_badge_a = f"ℹ️ Values adjusted by Ag-Share: {share_coef_a:.1%}"
    
    share_coef_b = 1.0
    if compare_mode and not sum_b.empty:
        if scen_b.get("basket_key"):
            basket_cfg_b = load_baskets_config().get(scen_b["basket_key"], {})
            share_coef_b = basket_cfg_b.get("calculated_share", 1.0)

    # --- CRITICAL FIX: APPLY SHARES TO DATAFRAME ROOTS ---
    # This ensures Charts, CSVs, and Metrics all tell the same story.
    if share_coef_a != 1.0:
        sum_a["impact_dollars"] *= share_coef_a
        if "impact" in sum_a.columns:
            sum_a["impact"] *= share_coef_a
        
        # [NEW] Sync the Narrative/Breakdown Dataframe
        if not bd_a.empty:
            bd_a["impact"] *= share_coef_a

    if compare_mode and not sum_b.empty and share_coef_b != 1.0:
        sum_b["impact_dollars"] *= share_coef_b
        if "impact" in sum_b.columns:
            sum_b["impact"] *= share_coef_b
        
        # [NEW] Sync the Narrative/Breakdown Dataframe
        if not bd_b.empty:
            bd_b["impact"] *= share_coef_b

    out_a = get_metric(sum_a, "Output")
    gdp_a = get_metric(sum_a, "Gross domestic")
    jobs_a = get_metric(sum_a, "Jobs")
    qual_a = get_job_quality(sum_a)
    
    out_b, gdp_b, jobs_b, qual_b = 0, 0, 0, 0
    if compare_mode and not sum_b.empty:
        out_b = get_metric(sum_b, "Output")
        gdp_b = get_metric(sum_b, "Gross domestic")
        jobs_b = get_metric(sum_b, "Jobs")
        qual_b = get_job_quality(sum_b)

    # 3. EXECUTIVE DASHBOARD
    # Context banner
    _banner_year = target_year_a if target_year_a else ""
    _banner_scope = scope_label
    st.markdown(
        f'<div class="context-banner">'
        f'<span>📍 <span class="badge">{scen_a["geo"]}</span></span>'
        f'<span>🏭 <span class="badge">{scen_a["name"] or "Select an industry"}</span></span>'
        f'<span>📅 <span class="badge">{_banner_year}</span></span>'
        f'<span>🔬 <span class="badge">{_banner_scope}</span></span>'
        f'</div>',
        unsafe_allow_html=True
    )
    
    st.markdown('<p class="section-header">Executive Summary</p>', unsafe_allow_html=True)
    if share_badge_a:
        st.caption(share_badge_a)

    col1, col2 = st.columns([1, 1]) 
    
    with col1:
        with st.container(border=True):
            st.markdown("##### 💰 Economic Activity")
            c1, c2 = st.columns(2)
            if not compare_mode:
                c1.metric("Total Output", format_compact(out_a), help="Total value of goods produced")
                c2.metric("GDP Contribution", format_compact(gdp_a), help="Value added at basic prices")
            else:
                delta_out = out_a - out_b
                delta_gdp = gdp_a - gdp_b
                c1.metric("Total Output (A)", format_compact(out_a), delta=f"{format_compact(delta_out)} vs B")
                c2.metric("GDP Contrib (A)", format_compact(gdp_a), delta=f"{format_compact(delta_gdp)} vs B")

    with col2:
        with st.container(border=True):
            st.markdown("##### 👷 Labour Market")
            c3, c4 = st.columns(2)
            if not compare_mode:
                c3.metric("Jobs Supported", f"{jobs_a:,.0f}", help="Total employment supported")
                c4.metric("Avg Annual Wage", f"${qual_a:,.0f}", help="Wages & salaries per job")
            else:
                delta_jobs = jobs_a - jobs_b
                delta_qual = qual_a - qual_b
                c3.metric("Jobs (A)", f"{jobs_a:,.0f}", delta=f"{delta_jobs:,.0f} vs B")
                c4.metric("Avg Wage (A)", format_compact(qual_a), delta=f"{format_compact(delta_qual)} vs B")

    # --- NEW: TRADE & INVESTMENT ROW ---
    st.markdown("---")
    col3, col4 = st.columns([1, 1])
    
    # --- FIX: TRUST ONLY DIRECT TRADE DATA (Parent Dominance Filter) ---
    exports_a = get_export_value(scen_a["geo"], target_year_a, scen_a["codes"])
    imports_a = sum_by_keywords(sum_a, ["international import", "imports from", "from non-residents"])
    trade_balance = exports_a - imports_a
    capex_a = get_investment_value(scen_a["geo"], target_year_a, scen_a["codes"])

    with col3:
        with st.container(border=True):
            st.markdown("##### 🚢 Trade Performance")
            c1, c2 = st.columns(2)
            
            # --- DATA AVAILABILITY CHECK ---
            # If we are looking at a Province (not Canada) and have 0 exports, 
            # it implies missing data, not zero activity.
            is_provincial_missing = (scen_a["geo"] != "Canada") and (exports_a == 0)
            
            if is_provincial_missing:
                c1.metric("International Exports", "N/A*", help="Data unavailable for provinces")
                c2.metric("Trade Balance", "N/A*", help="Data unavailable for provinces")
                st.caption("⚠️ *Trade & Investment data is currently available at the National level only.")
            else:
                # Standard Display for Canada or if data exists
                c1.metric("International Exports", format_compact(exports_a), help="Value of goods sold internationally")
                c2.metric("Trade Balance", format_compact(trade_balance), 
                          delta="Surplus" if trade_balance > 0 else "Deficit",
                          delta_color="normal")

    with col4:
        with st.container(border=True):
            st.markdown("##### 🏗️ Future Capacity")
            
            # Same check for CapEx
            is_capex_missing = (scen_a["geo"] != "Canada") and (capex_a == 0)
            
            if is_capex_missing:
                st.metric("Capital Investment (CapEx)", "N/A*", help="Data unavailable for provinces")
                if not is_provincial_missing:  # Avoid duplicate caption if already shown
                    st.caption("⚠️ *National data only.")
            else:
                st.metric("Capital Investment (CapEx)", format_compact(capex_a), 
                          help="Investment in construction, machinery, and equipment")

    # ── Phase 4B: "What Changed?" Diff Summary Card ────────────────────
    if compare_mode and not sum_b.empty:
        st.markdown("---")
        st.markdown('<p class="section-header">⚡ What Changed? — Scenario A vs B</p>', unsafe_allow_html=True)

        _diff_rows = [
            {"Metric": "Total Output",     "A": out_a,  "B": out_b},
            {"Metric": "GDP Contribution",  "A": gdp_a,  "B": gdp_b},
            {"Metric": "Jobs Supported",    "A": jobs_a, "B": jobs_b},
            {"Metric": "Avg Annual Wage",   "A": qual_a, "B": qual_b},
        ]
        # Add trade/capex if available
        if 'exports_a' in dir() and exports_a > 0:
            exports_b = get_export_value(scen_b["geo"], target_year_b, scen_b["codes"]) if scen_b else 0
            _diff_rows.append({"Metric": "International Exports", "A": exports_a, "B": exports_b})
        if 'capex_a' in dir() and capex_a > 0:
            capex_b = get_investment_value(scen_b["geo"], target_year_b, scen_b["codes"]) if scen_b else 0
            _diff_rows.append({"Metric": "Capital Investment", "A": capex_a, "B": capex_b})

        _diff_df = pd.DataFrame(_diff_rows)
        _diff_df["Δ Absolute"] = _diff_df["A"] - _diff_df["B"]
        _diff_df["Δ %"] = _diff_df.apply(
            lambda r: (r["A"] - r["B"]) / r["B"] * 100 if r["B"] != 0 else 0, axis=1
        )

        # Sort by absolute delta magnitude (largest first)
        _diff_df["_abs_delta"] = _diff_df["Δ Absolute"].abs()
        _diff_df = _diff_df.sort_values("_abs_delta", ascending=False).drop(columns=["_abs_delta"])

        def _fmt_diff_val(val, metric):
            if "Jobs" in metric:
                return f"{val:,.0f}"
            return format_compact(val)

        def _arrow(val):
            if val > 0: return "▲"
            if val < 0: return "▼"
            return "—"

        def _color_delta(val):
            if val > 0: return "color: #059669; font-weight: bold"
            if val < 0: return "color: #dc2626; font-weight: bold"
            return "color: #666"

        _styled = _diff_df[["Metric", "A", "B", "Δ Absolute", "Δ %"]].copy()
        _styled["Direction"] = _styled["Δ Absolute"].apply(_arrow)

        # Format for display
        for idx, row in _styled.iterrows():
            _styled.at[idx, "A"] = _fmt_diff_val(row["A"], row["Metric"])
            _styled.at[idx, "B"] = _fmt_diff_val(row["B"], row["Metric"])
            _styled.at[idx, "Δ Absolute"] = _fmt_diff_val(row["Δ Absolute"], row["Metric"])

        _styled["Δ %"] = _styled["Δ %"].apply(lambda v: f"{v:+.1f}%")
        _styled = _styled[["Metric", "A", "B", "Direction", "Δ Absolute", "Δ %"]]
        _styled.columns = ["Metric", "Scenario A", "Scenario B", "", "Δ ($)", "Δ (%)"]

        st.dataframe(_styled, hide_index=True, use_container_width=True)
        st.caption("Sorted by largest absolute difference. ▲ = A exceeds B, ▼ = B exceeds A.")

    # --- NARRATIVE ---
    if not bd_a.empty:
        try:
            total_output = get_metric(sum_a, "Output")
            total_gdp    = get_metric(sum_a, "Gross domestic")

            val_output_direct = bd_a[(bd_a["metric"] == "Output") & (bd_a["Type"] == "Direct")]["impact"].sum()
            
            val_gdp_direct = bd_a[
                (bd_a["metric"].astype(str).str.contains("Gross domestic", case=False, na=False)) & 
                (bd_a["metric"].astype(str).str.contains("basic prices", case=False, na=False)) & 
                (bd_a["Type"] == "Direct")
            ]["impact"].sum()

            # Q6 FIX: Removed hardcoded 0.65/0.56 ratio fallbacks.
            # If decomposition data is unavailable (suppressed by StatCan),
            # show a simplified narrative instead of fabricating ratios.
            has_decomp = (val_output_direct > 0) and (val_gdp_direct > 0)

            leakage = sum_a[sum_a["metric"].astype(str).str.contains("International imports", case=False, na=False)]["impact_dollars"].sum()
            leak_pct = (leakage / total_output * 100) if total_output > 0 else 0.0
            
            is_national = (scen_a["geo"] == "Canada")
            geo_scope = "nation" if is_national else "province"
            geo_outside = "abroad" if is_national else "outside the province"

            if has_decomp:
                val_output_indirect = total_output - val_output_direct
                val_gdp_indirect    = total_gdp - val_gdp_direct
                
                # Scope-aware narrative: hide Supply Chain line when scope is Direct-only
                is_direct_only = (scope_label == "Direct")
                
                if is_direct_only:
                    narrative = (
                        "### 📖 Direct Economic Footprint\n\n"
                        f"* **Direct Output:** The sector generates **{format_compact(val_output_direct)}** in direct revenue.\n"
                        f"* **Direct GDP:** Of that, **{format_compact(val_gdp_direct)}** is retained directly within the sector as GDP.\n\n"
                        "**👷 Employment Impact:**\n"
                        f"This sector directly supports a workforce of **{jobs_a:,.0f}** across the {geo_scope}, paying an average annual wage of **{format_compact(qual_a)}**.\n\n"
                        "📉 **Leakage Note:**\n"
                        f"Roughly **{leak_pct:.1f}%** of spending flows {geo_outside} to pay for imports.\n\n"
                        "_ℹ️ Select 'Direct + Indirect' or 'Direct + Indirect + Induced' to see the full supply chain ripple effects._"
                    )
                else:
                    narrative = (
                        "### 📖 The Story of Value Creation\n\n"
                        f"* **Direct Sales:** The sector generates **{format_compact(val_output_direct)}** in direct revenue.\n"
                        f"* **Value Add:** Of that, **{format_compact(val_gdp_direct)}** is retained directly within the sector as GDP.\n"
                        f"* **Supply Chain:** Suppliers generate another **{format_compact(val_output_indirect)}** in output and **{format_compact(val_gdp_indirect)}** in GDP.\n"
                        f"* **Combined Impact:** Together, they contribute **{format_compact(total_gdp)}** to the {geo_scope}'s GDP.\n\n"
                        "**👷 Employment Impact:**\n"
                        f"This sector supports a total workforce of **{jobs_a:,.0f}** across the {geo_scope}, paying an average annual wage of **{format_compact(qual_a)}**.\n\n"
                        "📉 **Leakage Note:**\n"
                        f"Roughly **{leak_pct:.1f}%** of spending flows {geo_outside} to pay for imports."
                    )
            else:
                narrative = (
                    "### 📖 Economic Impact Summary\n\n"
                    f"* **Total Output:** The sector generates **{format_compact(total_output)}** in total economic output.\n"
                    f"* **GDP Contribution:** **{format_compact(total_gdp)}** contributed to the {geo_scope}'s GDP.\n\n"
                    "**👷 Employment Impact:**\n"
                    f"This sector supports a total workforce of **{jobs_a:,.0f}** across the {geo_scope}, paying an average annual wage of **{format_compact(qual_a)}**.\n\n"
                    "📉 **Leakage Note:**\n"
                    f"Roughly **{leak_pct:.1f}%** of spending flows {geo_outside} to pay for imports.\n\n"
                    "_ℹ️ Direct/Indirect decomposition not available for this scope. "
                    "Statistics Canada may suppress individual multiplier levels for confidentiality._"
                )
            
            with st.container(border=True):
                st.markdown(narrative)
            
        except Exception as e:
            st.caption("Detailed narrative unavailable for this selection.")

    st.markdown("---")

    # --- 4. VISUAL TABS ---
    tab_vis, tab_data, tab_method, tab_report, tab_county = st.tabs([
        "📊 Visual Analysis", "📋 Detailed Data & Export",
        "🔬 Methodology & Audit", "📄 Report Generator",
        "🗺️ Ontario County Estimates"
    ])

    with tab_vis:
        col_chart1, col_chart2 = st.columns(2)
        
        viz_df_a = sum_a.copy()
        viz_df_a["Scenario"] = f"Scenario A ({scen_a['geo']})"
        
        if compare_mode and not sum_b.empty:
            viz_df_b = sum_b.copy()
            viz_df_b["Scenario"] = f"Scenario B ({scen_b['geo']})"
            viz_combined = pd.concat([viz_df_a, viz_df_b])
        else:
            viz_combined = viz_df_a

        with col_chart1:
            st.markdown("#### 🏦 Value Retention")
            leak_metrics = ["Gross domestic product", "International imports", "International exports"]
            leak_data = viz_combined[viz_combined["metric"].astype(str).str.contains("|".join(leak_metrics), case=False, na=False)].copy()
            
            def get_cat(x):
                if "import" in x.lower(): return "Leakage (Imports)"
                if "export" in x.lower(): return "Trade (Exports)"
                return "Value Added (GDP)"
            
            leak_data["Category"] = leak_data["metric"].apply(get_cat)
            
            max_val = leak_data["impact_dollars"].max()
            domain_max = max_val * 1.35 

            base = alt.Chart(leak_data).encode(
                x=alt.X('impact_dollars', title="Amount ($)", scale=alt.Scale(domain=[0, domain_max]), 
                        axis=alt.Axis(format='$.2s', labelExpr="replace(datum.label, 'G', 'B')")),
                y=alt.Y('Category', axis=alt.Axis(title=None, labels=True)),
            )

            if not compare_mode:
                # Pre-format labels to show B (billion) instead of Altair's SI "G" (giga)
                leak_data["bar_label"] = leak_data["impact_dollars"].apply(format_compact)
                
                bars = base.mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6).encode(
                    color=alt.Color('Category', scale=alt.Scale(
                        domain=['Value Added (GDP)', 'Leakage (Imports)', 'Trade (Exports)'],
                        range=['#059669', '#dc2626', '#2563eb']
                    ), legend=None),
                    tooltip=['metric', alt.Tooltip('impact_dollars', format='$,.0f')]
                )
                text = base.mark_text(align='left', dx=5, fontWeight='bold', fontSize=12).encode(
                    text='bar_label:N',
                    color=alt.value('#333')
                )
                st.altair_chart((bars + text).properties(height=220), use_container_width=True)
            else:
                st.altair_chart(base.mark_bar().encode(yOffset='Scenario', color='Scenario').properties(height=250), use_container_width=True)

        with col_chart2:
            st.markdown("#### 🌊 The Ripple Effect")
            
            bd_a["Scenario"] = f"Scenario A ({scen_a['geo']})"
            bd_combined = bd_a
            if compare_mode and not bd_b.empty:
                bd_b["Scenario"] = f"Scenario B ({scen_b['geo']})"
                bd_combined = pd.concat([bd_a, bd_b])

            if not bd_combined.empty:
                def clean_met(x):
                    x_lower = str(x).lower()
                    if "gross domestic" in x_lower and "basic prices" in x_lower: return "GDP"
                    if "taxes" in x_lower: return "Gov Revenue"
                    if x_lower.strip() == "output": return "Output"
                    return None

                bd_data = bd_combined.copy()
                bd_data["Metric Short"] = bd_data["metric"].apply(clean_met)
                bd_data = bd_data.dropna(subset=["Metric Short"])
                bd_data = bd_data[bd_data["Metric Short"].isin(["Output", "GDP", "Gov Revenue"])]
                
                bd_agg = bd_data.groupby(["Scenario", "Metric Short", "Type"], as_index=False)["impact"].sum()
                
                # Sort metrics in logical order: Output → GDP → Gov Revenue
                metric_order = ["Output", "GDP", "Gov Revenue"]

                final_chart2 = alt.Chart(bd_agg).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                    x=alt.X('impact', title="Impact ($)", axis=alt.Axis(format='$.2s',
                            labelExpr="replace(datum.label, 'G', 'B')")),
                    y=alt.Y('Metric Short', title=None, sort=metric_order),
                    color=alt.Color('Type', scale=alt.Scale(
                        domain=['Direct', 'Indirect', 'Induced'],
                        range=['#0d9488', '#f59e0b', '#ef4444']
                    ), legend=alt.Legend(orient='bottom', direction='horizontal')),
                    tooltip=['Metric Short', 'Type', alt.Tooltip('impact', format='$,.0f')]
                ).properties(height=250)
                
                st.altair_chart(final_chart2, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🥧 Contributions by Sub-Sector")
        
        def get_sector_label(row):
            # Q11 FIX: Strip StatCan prefixes before NAICS comparison
            code = str(row['industry_code']).replace('BS', '').replace('GS', '')
            if code.startswith('3253'): return "Fertilizer & Inputs"
            if code.startswith('3331'): return "Ag Machinery"
            if code.startswith('31') or code.startswith('32'): return "Food & Beverage Processing"
            if code.startswith('11'): return "Primary Agriculture"
            if code.startswith('41'): return "Wholesale"
            if code.startswith('44') or code.startswith('45'): return "Retail"
            if code.startswith('48') or code.startswith('49'): return "Transportation"
            if code.startswith('722'): return "Food Services"
            return "Other"

        if res_a is not None and not res_a.empty:
            breakdown_df = res_a[res_a['metric'] == 'Output'].copy()
            breakdown_df['Sector'] = breakdown_df.apply(get_sector_label, axis=1)
            sector_agg = breakdown_df.groupby(['Sector'], as_index=False)['impact'].sum()
            
            # Calculate percentage for cleaner display
            total_impact = sector_agg['impact'].sum()
            if total_impact > 0:
                sector_agg['pct'] = (sector_agg['impact'] / total_impact * 100).round(1)
                sector_agg['label'] = sector_agg.apply(
                    lambda r: f"{r['Sector']} ({r['pct']:.0f}%)", axis=1
                )
            else:
                sector_agg['pct'] = 0.0
                sector_agg['label'] = sector_agg['Sector']
            
            # Clean donut chart with side legend (no overlapping text)
            breakdown_chart = alt.Chart(sector_agg).mark_arc(innerRadius=60, outerRadius=120).encode(
                theta=alt.Theta(field="impact", type="quantitative", stack=True),
                color=alt.Color(
                    field="label", type="nominal",
                    scale=alt.Scale(scheme='tableau10'),
                    legend=alt.Legend(title="Sector", orient="right", labelLimit=200)
                ),
                tooltip=[
                    alt.Tooltip('Sector', title='Sector'),
                    alt.Tooltip('impact', format='$,.0f', title='Output'),
                    alt.Tooltip('pct', format='.1f', title='Share (%)')
                ]
            ).properties(height=350, title=f"{scope_label} Output Contribution by Sector")
            
            st.altair_chart(breakdown_chart, use_container_width=True)

    with tab_data:
        st.markdown("### Raw Data Table")
        st.dataframe(sum_a, use_container_width=True)
        csv = sum_a.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results as CSV", csv, "impact_results.csv", "text/csv")

    with tab_method:
        st.markdown("### 🔬 Methodology & Audit Trail")
        st.caption("This tab explains exactly how every number on this page is calculated. "
                   "Use it to learn how IO multipliers work, or to verify the raw data.")

        # ── SECTION 1: HOW IO MULTIPLIERS WORK ──────────────────────────
        with st.expander("📖 How We Calculate Economic Impact", expanded=False):
            st.markdown("""
**Input-Output (IO) multipliers** measure the ripple effects of economic activity through supply chains.
When a farm produces $1 of output, it buys fuel, fertilizer, feed, and services from other businesses.
Those businesses in turn buy from *their* suppliers, creating a chain reaction of spending.

**Three Layers of Impact:**

| Layer | What It Measures | Example |
|-------|------------------|---------|
| **Direct** | The activity within the sector itself | A farm's own output, wages, and jobs |
| **Indirect** | Supply chain spending triggered by the sector | Fertilizer plants, trucking companies, grain elevators |
| **Induced** | Household spending by workers in Direct + Indirect sectors | Workers buying groceries, housing, healthcare |

**How Multipliers Work:**

A multiplier is a ratio. If the Direct GDP multiplier is **0.45**, it means that for every **$1 of output** the sector produces,
**$0.45** of value added is generated, while the remainder pays for intermediate inputs, taxes, and imports.
Simple and Total multipliers trace those intermediate purchases through the supply chain to capture the
economy-wide accumulation of GDP before spending eventually leaks out via imports and taxes.

- **Direct multiplier** = impact within the sector only
- **Simple multiplier** = Direct + Indirect (supply chain)
- **Total multiplier** = Direct + Indirect + Induced (full economy)

**Data Source:** Statistics Canada Supply-Use IO Tables (Table 36-10-0594 for national, Table 36-10-0595 for provincial/territorial).
Multiplier values are published by StatCan and are **not estimated by this dashboard** — we apply them as-is.

**Provincial Multiplier Scope:**
For provincial selections, StatCan publishes **two variants** of each multiplier:
- **All Provinces**: Captures the full supply chain impact, including spending that flows to suppliers in other provinces. Use this for a complete picture of an industry's total economic footprint.
- **Within Province**: Restricts impacts to those retained within the selected province's own economy. Use this for provincial policy analysis focused on local economic retention.

Direct multipliers are typically identical between the two variants (activity within the industry itself is always local),
but Simple and Total multipliers differ because inter-provincial supply chain purchases are treated as leakage
under the "Within Province" framework.
            """)

        # ── SECTION 2: CURRENT SELECTION ────────────────────────────────
        with st.expander("⚙️ Your Current Selection", expanded=True):
            _is_basket = scen_a.get("basket_mode") == "Economic Sector Grouping"
            _shock_source = "Historical StatCan Output" if use_hist else f"Custom Shock (${shock_input:,.0f})"

            _sel_cols = st.columns(3)
            with _sel_cols[0]:
                st.markdown(f"**Geography:** {scen_a['geo']}")
                st.markdown(f"**Year:** {target_year_a}")
            with _sel_cols[1]:
                st.markdown(f"**Industry/Basket:** {scen_a['name']}")
                st.markdown(f"**Selection Mode:** {'Basket' if _is_basket else 'Single Industry'}")
            with _sel_cols[2]:
                st.markdown(f"**Impact Scope:** {scope_label}")
                st.markdown(f"**Shock Source:** {_shock_source}")
                if scen_a["geo"] != "Canada":
                    _prov_label = "All Provinces" if prov_scope_key == "all_provinces" else "Within Province"
                    st.markdown(f"**Multiplier Scope:** {_prov_label}")

            if _is_basket:
                st.info(f"📦 This basket contains **{len(scen_a['codes'])}** NAICS industry codes. "
                        f"Each code's contribution is weighted by its actual output — larger industries "
                        f"carry proportionally more weight in the final numbers.")
                if share_coef_a < 1.0:
                    st.warning(f"⚖️ **Ag-Share Adjustment Active:** This basket's values are scaled by "
                               f"**{share_coef_a:.1%}** because only a portion of the basket's output "
                               f"is attributable to agriculture (e.g., trucking serves many sectors).")

        # ── SECTION 3: RAW MULTIPLIER VALUES ───────────────────────────
        with st.expander("📊 Raw Multiplier Values (from StatCan)", expanded=False):
            _is_national = (scen_a["geo"] == "Canada")
            _table_id = "3610059401" if _is_national else "3610059501"
            _table_label = "36-10-0594" if _is_national else "36-10-0595"
            st.markdown(
                "The table below shows the **actual multiplier values** used in the calculations. "
                "These are published by Statistics Canada and can be cross-referenced against "
                f"[Table {_table_label}](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={_table_id})."
            )

            try:
                _raw_mult = load_multipliers()
                # Filter by provincial scope so displayed values match the toggle
                if not _raw_mult.empty and 'geo_scope' in _raw_mult.columns and scen_a["geo"] != "Canada":
                    _raw_mult = _raw_mult[_raw_mult['geo_scope'].isin([prov_scope_key, 'national'])]
                if not _raw_mult.empty:
                    _mask = (
                        (_raw_mult["GEO"] == scen_a["geo"]) &
                        (_raw_mult["join_code"].isin(scen_a["codes"]))
                    )
                    _yr_filter = _raw_mult[_mask]
                    if target_year_a:
                        _yr_data = _yr_filter[_yr_filter["YEAR"] == target_year_a]
                        if _yr_data.empty:
                            _avail = sorted(_yr_filter["YEAR"].unique())
                            if _avail:
                                _yr_data = _yr_filter[_yr_filter["YEAR"] == _avail[-1]]
                                st.caption(f"ℹ️ Exact year {target_year_a} not available; showing {_avail[-1]} data.")
                    else:
                        _yr_data = _yr_filter

                    if not _yr_data.empty:
                        # Pivot: rows = (code, industry, metric), cols = (Direct, Simple, Total)
                        _pivot = _yr_data.pivot_table(
                            index=["join_code", "industry_name", "variable"],
                            columns="multiplier_type",
                            values="value",
                            aggfunc="first",
                            observed=False,
                        ).reset_index()

                        # Rename columns for readability
                        _col_rename = {
                            "join_code": "NAICS Code",
                            "industry_name": "Industry",
                            "variable": "Metric",
                            "Direct multiplier": "Direct",
                            "Simple multiplier": "Direct+Indirect",
                            "Total multiplier": "Direct+Indirect+Induced",
                        }
                        _pivot.rename(columns=_col_rename, inplace=True)

                        # Highlight the column matching user's scope
                        _scope_col_map = {
                            "Direct": "Direct",
                            "Direct + Indirect": "Direct+Indirect",
                            "Direct + Indirect + Induced": "Direct+Indirect+Induced",
                        }
                        _active_col = _scope_col_map.get(scope_label, "")

                        st.markdown(f"**Your selected scope ({scope_label})** uses the "
                                    f"**{_active_col}** column below.")

                        _display_cols = ["NAICS Code", "Industry", "Metric"]
                        for c in ["Direct", "Direct+Indirect", "Direct+Indirect+Induced"]:
                            if c in _pivot.columns:
                                _display_cols.append(c)

                        st.dataframe(
                            _pivot[_display_cols].sort_values(["NAICS Code", "Metric"]),
                            use_container_width=True, hide_index=True
                        )

                        st.caption(
                            "💡 **Reading the table:** A GDP multiplier of 0.45 means $1 of industry output "
                            "generates $0.45 in GDP. A Jobs multiplier of 5.2 means $1M of output supports 5.2 jobs."
                        )
                    else:
                        st.info("No multiplier data available for this selection.")
                else:
                    st.info("Multiplier data not loaded.")
            except Exception as e:
                st.warning(f"Could not load raw multipliers: {e}")

        # ── SECTION 4: BASKET WEIGHTING MATH ───────────────────────────
        if _is_basket and len(scen_a["codes"]) > 1:
            with st.expander("⚖️ Basket Weighting: How Individual Industries Are Combined", expanded=False):
                st.markdown(
                    "When you select a **basket** (group of industries), individual industry impacts are "
                    "**weighted by their actual economic output**, not simply averaged. Larger industries "
                    "carry proportionally more influence on the final numbers."
                )

                # Build the weighting table
                _weight_rows = []
                _total_basket = 0.0
                for _wc in scen_a["codes"]:
                    _wval = get_actual_output(scen_a["geo"], target_year_a, [_wc])
                    _weight_rows.append({"NAICS Code": _wc, "Output ($)": _wval})
                    _total_basket += _wval

                _wdf = pd.DataFrame(_weight_rows)
                if _total_basket > 0:
                    _wdf["Weight (%)"] = (_wdf["Output ($)"] / _total_basket * 100).round(2)
                else:
                    _wdf["Weight (%)"] = 0.0

                # Add industry names from multiplier data if available
                try:
                    _nm = load_multipliers()
                    _name_map = dict(zip(_nm["join_code"], _nm["industry_name"]))
                    _wdf["Industry"] = _wdf["NAICS Code"].map(_name_map).fillna("Unknown")
                    _wdf = _wdf[["NAICS Code", "Industry", "Output ($)", "Weight (%)"]]
                except Exception:
                    pass

                _wdf = _wdf.sort_values("Output ($)", ascending=False)

                st.dataframe(
                    _wdf.style.format({"Output ($)": "${:,.0f}", "Weight (%)": "{:.2f}%"}),
                    use_container_width=True, hide_index=True
                )

                st.markdown(f"**Total Basket Output:** ${_total_basket:,.0f}")

                if share_coef_a < 1.0:
                    st.markdown(
                        f"\n**Ag-Share Adjustment:** After weighting, all values are multiplied by "
                        f"**{share_coef_a:.1%}** to reflect agriculture's share of this sector's activity."
                    )

                if use_hist:
                    st.markdown("""
**Formula (Historical Output mode):**
```
impact_i = actual_output_i × multiplier_i
total_impact = Σ impact_i
```
Each industry's actual StatCan output serves as its shock input.""")
                else:
                    st.markdown(f"""
**Formula (Custom Shock mode — ${shock_input:,.0f}):**
```
weight_i = actual_output_i / total_basket_output
impact_i = (Custom_Shock × weight_i) × multiplier_i
total_impact = Σ impact_i
```
The custom shock is distributed proportionally by each industry's economic output.""")

        # ── SECTION 5: STEP-BY-STEP WALKTHROUGH ────────────────────────
        with st.expander("🧮 Step-by-Step Calculation Walkthrough", expanded=False):
            st.markdown("Below is the exact arithmetic behind the headline numbers shown above.")

            _out_val = get_metric(sum_a, "Output")
            _gdp_val = get_metric(sum_a, "Gross domestic")
            _jobs_val = get_metric(sum_a, "Jobs")

            st.markdown("#### Step 1: Determine the Shock (Input)")
            if use_hist:
                _total_shock = sum(get_actual_output(scen_a["geo"], target_year_a, [c]) for c in scen_a["codes"])
                st.markdown(
                    f"Using **Historical Output** mode: the actual StatCan output for this selection "
                    f"in {target_year_a} is **${_total_shock:,.0f}**.\n\n"
                    f"This value becomes the 'shock' — it represents the real economic activity that occurred."
                )
            else:
                _total_shock = shock_input
                st.markdown(
                    f"Using **Custom Shock** mode: you entered **${shock_input:,.0f}** as the hypothetical "
                    f"investment or spending change."
                )

            st.markdown("#### Step 2: Apply Multipliers")
            _mult_label = "Effective Multiplier" if _is_basket else "Multiplier"
            _ag_str = f" × {share_coef_a:.1%} (Ag-Share)" if share_coef_a < 1.0 else ""
            st.markdown(
                f"The **{scope_label}** multiplier is applied to the shock to compute each metric:\n\n"
                f"| Metric | Formula | Result |\n"
                f"|--------|---------|--------|\n"
                f"| **Output** | Shock × Output {_mult_label}{_ag_str} | **${_out_val:,.0f}** |\n"
                f"| **GDP** | Shock × GDP {_mult_label}{_ag_str} | **${_gdp_val:,.0f}** |\n"
                f"| **Jobs** | (Shock / $1M) × Jobs {_mult_label}{_ag_str} | **{_jobs_val:,.0f}** |\n"
            )

            # Derive implied multipliers for verification
            if _total_shock != 0:
                _impl_out = _out_val / _total_shock
                _impl_gdp = _gdp_val / _total_shock
                _impl_jobs = _jobs_val / (_total_shock / 1_000_000) if _total_shock != 0 else 0

                st.markdown("#### Step 3: Effective Multipliers (for verification)")
                _mult_note = ("For basket views, these are the **output-weighted averages** across all industries. "
                              "For single-industry views, these match the exact StatCan values shown above.")
                st.markdown(
                    f"Dividing the results by the input shock gives the **effective multipliers** applied to this selection. "
                    f"{_mult_note}\n\n"
                    f"| Metric | Effective Multiplier | Interpretation |\n"
                    f"|--------|---------------------|----------------|\n"
                    f"| **Output** | {_impl_out:.4f} | $1 of activity → ${_impl_out:.2f} total output |\n"
                    f"| **GDP** | {_impl_gdp:.4f} | $1 of activity → ${_impl_gdp:.2f} GDP |\n"
                    f"| **Jobs** | {_impl_jobs:.4f} | $1M of activity → {_impl_jobs:.1f} jobs |\n"
                )

                if 0.0 < share_coef_a < 1.0:
                    st.markdown(
                        f"\n⚖️ **Note:** These implied multipliers already include the "
                        f"Ag-Share adjustment ({share_coef_a:.1%}). The raw StatCan multipliers "
                        f"(shown in the table above) are higher by a factor of "
                        f"{1/share_coef_a:.2f}x before adjustment."
                    )

            st.markdown("---")
            st.markdown(
                "**🔍 Verification Tip:** Compare the *Effective Multipliers* above with the "
                "*Raw Multiplier Values* table. For single-industry views (where no Ag-Share adjustment applies), "
                "they should match the exact StatCan value. If an Ag-Share is active, the implied multiplier equals "
                "the raw multiplier scaled by the Ag-Share coefficient. "
                "For basket views, they represent the output-weighted average across all industries in the basket."
            )


    # ── TAB 4: REPORT GENERATOR ──────────────────────────────────────────────
    with tab_report:
        st.markdown("### 📄 Report Generator")
        st.markdown(
            "Generate professional documents from your current analysis. "
            "All three outputs reflect the exact parameters selected in the sidebar."
        )

        # Preview of what will be generated
        with st.container(border=True):
            _rpt_cols = st.columns(3)
            with _rpt_cols[0]:
                st.markdown(f"**Geography:** {scen_a['geo']}")
                st.markdown(f"**Industry/Basket:** {scen_a['name']}")
            with _rpt_cols[1]:
                st.markdown(f"**Year:** {target_year_a}")
                st.markdown(f"**Impact Scope:** {scope_label}")
            with _rpt_cols[2]:
                _rpt_shock = "Historical StatCan Output" if use_hist else f"Custom (${shock_input:,.0f})"
                st.markdown(f"**Shock Source:** {_rpt_shock}")
                if scen_a['geo'] != 'Canada':
                    _rpt_prov = 'All Provinces' if prov_scope_key == 'all_provinces' else 'Within Province'
                    st.markdown(f"**Multiplier Scope:** {_rpt_prov}")

        st.markdown("---")

        # Common report params
        _rpt_prov_label = 'All Provinces' if prov_scope_key == 'all_provinces' else 'Within Province'
        if scen_a['geo'] == 'Canada':
            _rpt_prov_label = 'National'
        _rpt_shock_source = "Historical StatCan Output" if use_hist else f"Custom Shock (${shock_input:,.0f})"
        _is_basket_rpt = scen_a.get('basket_mode') == 'Economic Sector Grouping'

        # Load raw multipliers for the full report
        _rpt_raw_mult = pd.DataFrame()
        try:
            _rpt_raw = load_multipliers()
            if not _rpt_raw.empty:
                if 'geo_scope' in _rpt_raw.columns and scen_a['geo'] != 'Canada':
                    _rpt_raw = _rpt_raw[_rpt_raw['geo_scope'].isin([prov_scope_key, 'national'])]
                
                _rpt_mask = (
                    (_rpt_raw['GEO'] == scen_a['geo']) &
                    (_rpt_raw['join_code'].isin(scen_a['codes']))
                )
                _rpt_raw_mult = _rpt_raw[_rpt_mask]
                if target_year_a:
                    _yr = _rpt_raw_mult[_rpt_raw_mult['YEAR'] == target_year_a]
                    if not _yr.empty:
                        _rpt_raw_mult = _yr
        except Exception:
            pass

        # Three download columns — lazy-import report generator only when tab is active
        from scripts.report_generator import (
            generate_full_report, generate_slide_deck, generate_one_pager,
        )
        dl_col1, dl_col2, dl_col3 = st.columns(3)

        with dl_col1:
            with st.container(border=True):
                st.markdown("#### 📑 Full Report")
                st.markdown(
                    "A **detailed economic impact report** (~6-8 pages). "
                    "Includes methodology, charts, "
                    "sector decomposition, and raw multiplier tables."
                )
                try:
                    _report_buf = generate_full_report(
                        geo=scen_a['geo'], basket_name=scen_a['name'],
                        year=target_year_a or 2022, scope_label=scope_label,
                        prov_scope_label=_rpt_prov_label,
                        sum_df=sum_a, bd_df=bd_a, res_df=res_a,
                        raw_mult_df=_rpt_raw_mult,
                        jobs=jobs_a, avg_wage=qual_a,
                        get_sector_label_fn=get_sector_label if _is_basket_rpt else None,
                        basket_codes=scen_a['codes'],
                        is_basket=_is_basket_rpt,
                        shock_source=_rpt_shock_source,
                        basket_config=_active_basket_cfg,
                    )
                    _fname = f"Economic_Impact_{scen_a['name'].replace(' ', '_')}_{scen_a['geo']}_{target_year_a or 2022}.docx"
                    st.download_button(
                        "📥 Download Full Report (.docx)",
                        data=_report_buf,
                        file_name=_fname,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                except Exception as _e:
                    st.error(f"Report generation failed: {_e}")

        with dl_col2:
            with st.container(border=True):
                st.markdown("#### 📊 Slide Deck")
                st.markdown(
                    "A **PowerPoint presentation** (~6 slides) with key metrics, charts, "
                    "and talking points. Ready to present alongside the full report."
                )
                try:
                    _ppt_buf = generate_slide_deck(
                        geo=scen_a['geo'], basket_name=scen_a['name'],
                        year=target_year_a or 2022, scope_label=scope_label,
                        prov_scope_label=_rpt_prov_label,
                        sum_df=sum_a, bd_df=bd_a, res_df=res_a,
                        jobs=jobs_a, avg_wage=qual_a,
                        get_sector_label_fn=get_sector_label if _is_basket_rpt else None,
                        shock_source=_rpt_shock_source,
                    )
                    _fname_ppt = f"Impact_Slides_{scen_a['name'].replace(' ', '_')}_{scen_a['geo']}_{target_year_a or 2022}.pptx"
                    st.download_button(
                        "📥 Download Slide Deck (.pptx)",
                        data=_ppt_buf,
                        file_name=_fname_ppt,
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )
                except Exception as _e:
                    st.error(f"Slide deck generation failed: {_e}")

        with dl_col3:
            with st.container(border=True):
                st.markdown("#### 📋 One-Pager")
                st.markdown(
                    "A **single-page briefing document** with headline KPIs, the key chart, "
                    "and talking points. Designed as a leave-behind for meetings with "
                    "politicians or stakeholders."
                )
                try:
                    _onep_buf = generate_one_pager(
                        geo=scen_a['geo'], basket_name=scen_a['name'],
                        year=target_year_a or 2022, scope_label=scope_label,
                        prov_scope_label=_rpt_prov_label,
                        sum_df=sum_a, bd_df=bd_a,
                        jobs=jobs_a, avg_wage=qual_a,
                        shock_source=_rpt_shock_source,
                    )
                    _fname_1p = f"Impact_OnePager_{scen_a['name'].replace(' ', '_')}_{scen_a['geo']}_{target_year_a or 2022}.docx"
                    st.download_button(
                        "📥 Download One-Pager (.docx)",
                        data=_onep_buf,
                        file_name=_fname_1p,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                except Exception as _e:
                    st.error(f"One-pager generation failed: {_e}")

        st.markdown("---")
        st.caption(
            "📌 All reports use the exact data currently displayed in the dashboard. "
            "Charts are rendered at print quality (200 DPI). "
            "Source: Statistics Canada Input-Output Tables."
        )

    # ── TAB 5: ONTARIO COUNTY ESTIMATES ─────────────────────────────────────────
    with tab_county:
        st.markdown("### 🗺️ Ontario County-Level Economic Impact Estimates")

        # Check data availability
        _county_years = available_county_years()
        _fcr_data = load_county_fcr()
        _data_available = len(_county_years) > 0 and not _fcr_data.empty

        if not _data_available:
            st.error(
                "⚠️ **County-level data not available.** "
                "Please run `python scripts/fetch_omafra_county_fcr.py` to download and process "
                "the OMAFRA Ontario Farm Cash Receipts by County dataset."
            )
        else:
            # ── Methodology Banner ───────────────────────────────────────
            with st.expander("📖 Methodology & Caveats — Read Before Using", expanded=False):
                st.markdown("""
**What This Tab Does:**

This tab estimates the **relative contribution** of each Ontario county to the province's 
overall agricultural economic impact. It does this by apportioning the provincial IO model 
results using each county's share of **Farm Cash Receipts (FCR)** as a proxy for output.

**How It Works:**
1. The provincial economic impact for **Primary Agriculture** is computed using 
   Statistics Canada IO multipliers (same engine as the main analysis)
2. Each county's share of Ontario's total Farm Cash Receipts (from OMAFRA data) is calculated
3. The provincial impact is distributed proportionally — if County X has 10% of Ontario's FCR, 
   it is attributed 10% of the provincial output, GDP, jobs, etc.

---

**⚠️ Important Caveats:**

| Assumption | Implication |
|-----------|-------------|
| **Proportional Output** | Assumes each county's share of provincial output equals its share of FCR. This is standard practice but not exact. |
| **Uniform Multipliers** | Provincial IO multipliers are applied uniformly — a dollar of output in Huron County has the same ripple effect as in Essex. In reality, rural counties with thinner supply chains may have lower multipliers (more "leakage"). |
| **Primary Agriculture Only** | This proxy is valid for primary agriculture only. Manufacturing, wholesale, and transport impacts cannot be meaningfully allocated by FCR share. |

**Data Source:** [OMAFRA Ontario Farm Cash Receipts by County and Commodity](https://data.ontario.ca/dataset/ontario-farm-cash-receipts-by-county-and-crop) 
(Open Government Licence – Ontario), combined with Statistics Canada IO Tables.
                """)

            st.markdown("---")

            # ── County Controls ──────────────────────────────────────────
            ctrl_cols = st.columns([1, 1, 2])

            with ctrl_cols[0]:
                # Year selector — constrained to years where BOTH IO data and OMAFRA data overlap
                _io_years = available_years("Ontario")
                _overlap_years = sorted(set(_county_years) & set(_io_years), reverse=True)
                if not _overlap_years:
                    st.warning("No overlapping years between IO tables and OMAFRA county data.")
                    st.stop()
                _county_year = st.selectbox(
                    "📅 Year",
                    options=_overlap_years,
                    index=0,
                    key="county_year_select",
                    help="Select the year for county-level estimation"
                )

            with ctrl_cols[1]:
                _county_scope_options = {
                    "Direct": "direct",
                    "Direct + Indirect": "direct_indirect",
                    "Direct + Indirect + Induced": "direct_indirect_induced",
                }
                _county_scope_label = st.selectbox(
                    "🔬 Impact Scope",
                    options=list(_county_scope_options.keys()),
                    index=2,  # Default to total
                    key="county_scope_select",
                )
                _county_scope = _county_scope_options[_county_scope_label]

            with ctrl_cols[2]:
                _all_counties = available_counties(_county_year)
                _county_names = [c["display"] for c in _all_counties]
                _county_slug_map = {c["display"]: c["slug"] for c in _all_counties}

                _selected_county_names = st.multiselect(
                    "🏘️ Select Counties (leave empty for all)",
                    options=_county_names,
                    default=[],
                    key="county_multiselect",
                    help="Select specific counties to highlight, or leave empty to show all"
                )

            # ── Compute County Impacts ───────────────────────────────────
            with st.spinner("Computing county-level estimates..."):
                _county_impacts = compute_county_impacts(
                    year=_county_year,
                    scope=_county_scope,
                    geo_scope="all_provinces",
                )

            if _county_impacts.empty:
                st.warning(
                    f"Could not compute county-level estimates for {_county_year}. "
                    "This usually means IO multiplier data is not available for this year."
                )
            else:
                # ── KPI Cards ────────────────────────────────────────────
                # Provincial totals
                _prov_output = _county_impacts[_county_impacts["metric"].astype(str).str.contains("Output", case=False, na=False)]["provincial_impact"].iloc[0] if not _county_impacts[_county_impacts["metric"].astype(str).str.contains("Output", case=False, na=False)].empty else 0
                _prov_gdp = _county_impacts[_county_impacts["metric"].astype(str).str.contains("Gross domestic", case=False, na=False)]["provincial_impact"].iloc[0] if not _county_impacts[_county_impacts["metric"].astype(str).str.contains("Gross domestic", case=False, na=False)].empty else 0
                _prov_jobs = _county_impacts[_county_impacts["metric"].astype(str).str.contains("Jobs", case=False, na=False)]["provincial_impact"].iloc[0] if not _county_impacts[_county_impacts["metric"].astype(str).str.contains("Jobs", case=False, na=False)].empty else 0

                n_counties = _county_impacts["county"].nunique()

                kpi_cols = st.columns(4)
                with kpi_cols[0]:
                    st.metric("Ontario Counties", f"{n_counties}", help="Number of counties with OMAFRA FCR data")
                with kpi_cols[1]:
                    st.metric("Provincial Output", f"${_prov_output/1e9:,.2f}B", help="Total Primary Agriculture output for Ontario")
                with kpi_cols[2]:
                    st.metric("Provincial GDP", f"${_prov_gdp/1e9:,.2f}B", help="Total Primary Agriculture GDP contribution")
                with kpi_cols[3]:
                    st.metric("Provincial Jobs", f"{_prov_jobs:,.0f}", help="Total Primary Agriculture jobs supported")

                st.markdown("---")

                # ── Ranked Bar Chart ─────────────────────────────────────
                st.markdown("#### 📊 County Rankings by Estimated Economic Impact")

                _metric_options = sorted(_county_impacts["metric"].unique())
                _default_metric = next((m for m in _metric_options if "Output" in m), _metric_options[0])
                _chart_metric = st.selectbox(
                    "Metric to display",
                    options=_metric_options,
                    index=_metric_options.index(_default_metric),
                    key="county_chart_metric",
                )

                _chart_data = _county_impacts[_county_impacts["metric"] == _chart_metric].copy()
                _chart_data = _chart_data.sort_values("county_impact", ascending=True)

                # Highlight selected counties
                _selected_slugs = [_county_slug_map[n] for n in _selected_county_names] if _selected_county_names else []
                _chart_data["highlighted"] = _chart_data["county"].isin(_selected_slugs) if _selected_slugs else True

                # Determine formatting
                _is_jobs = "Jobs" in _chart_metric
                _fmt = ",.0f" if _is_jobs else "$,.0f"
                _axis_fmt = ",.0f" if _is_jobs else "$.2s"

                # Color based on selection
                if _selected_slugs:
                    _color_condition = alt.condition(
                        alt.datum.highlighted,
                        alt.value("#059669"),
                        alt.value("#d1d5db")
                    )
                else:
                    _color_condition = alt.Color(
                        "region:N",
                        scale=alt.Scale(
                            domain=["Southern Ontario", "Western Ontario", "Central Ontario", "Eastern Ontario", "Northern Ontario"],
                            range=["#059669", "#2563eb", "#d97706", "#7c3aed", "#dc2626"]
                        ),
                        legend=alt.Legend(orient="bottom", direction="horizontal", title="Region")
                    )

                _bar_chart = alt.Chart(_chart_data).mark_bar(
                    cornerRadiusEnd=4
                ).encode(
                    y=alt.Y("county_display:N", sort="-x", title=None,
                            axis=alt.Axis(labelLimit=200)),
                    x=alt.X("county_impact:Q", title=_chart_metric,
                            axis=alt.Axis(format=_axis_fmt,
                                          labelExpr="replace(datum.label, 'G', 'B')")),
                    color=_color_condition,
                    tooltip=[
                        alt.Tooltip("county_display:N", title="County"),
                        alt.Tooltip("region:N", title="Region"),
                        alt.Tooltip("county_impact:Q", format=_fmt, title=_chart_metric),
                        alt.Tooltip("county_share:Q", format=".1%", title="Share of Province"),
                        alt.Tooltip("fcr_millions:Q", format="$,.1f", title="FCR ($M)"),
                    ]
                ).properties(
                    height=max(400, n_counties * 18),
                    title=alt.Title(
                        f"Estimated {_chart_metric} by Ontario County ({_county_year})",
                        subtitle=f"Scope: {_county_scope_label} | Apportioned by Farm Cash Receipt share"
                    )
                )

                st.altair_chart(_bar_chart, use_container_width=True)

                st.markdown("---")

                # ── Choropleth Map ───────────────────────────────────────
                st.markdown("#### 🗺️ Geographic Distribution")

                _BOUNDARY_FILE = Path("data/latest/wellbeing") / "ontario_csd_boundaries.geojson"
                try:
                    import pydeck as pdk
                    _HAS_PYDECK = True
                except ImportError:
                    _HAS_PYDECK = False

                if _BOUNDARY_FILE.exists() and _HAS_PYDECK:
                    import geopandas as gpd

                    try:
                        _county_gdf = _load_county_boundaries(_BOUNDARY_FILE)

                        # Load geo file for county name mapping
                        _GEO_FILE = Path("data/latest/wellbeing") / "dim_geography.csv"
                        _county_code_to_name = {}
                        if _GEO_FILE.exists():
                            _geo_df = smart_read(_GEO_FILE)
                            if "sgc_code" in _geo_df.columns and "county" in _geo_df.columns:
                                _geo_df["sgc_code"] = _geo_df["sgc_code"].astype(str).str.zfill(7)
                                _geo_df["county_code"] = _geo_df["sgc_code"].str[:4]
                                _county_code_to_name = dict(
                                    _geo_df.drop_duplicates("county_code")[["county_code", "county"]].dropna().values
                                )

                        # Map county display names to OMAFRA data
                        # Build a mapping from geo county name -> OMAFRA slug
                        from scripts.fetch_omafra_county_fcr import COUNTY_DISPLAY_NAMES
                        _display_to_slug = {v.lower(): k for k, v in COUNTY_DISPLAY_NAMES.items()}

                        # Get impact data for map metric
                        _map_data = _chart_data.copy()  # Uses same metric as bar chart

                        _county_gdf["geo_county_name"] = _county_gdf["county_code"].map(_county_code_to_name).fillna("Unknown")

                        # Try to join on county name fuzzy match
                        def _match_county(geo_name):
                            """Match geo county name to OMAFRA slug."""
                            if pd.isna(geo_name) or geo_name == "Unknown":
                                return None
                            name_lower = geo_name.lower().strip()
                            # Direct match attempts
                            for display, slug in _display_to_slug.items():
                                if name_lower in display or display in name_lower:
                                    return slug
                                # Try partial
                                geo_words = set(name_lower.replace("county", "").replace("region", "").replace("district", "").split())
                                disp_words = set(display.replace("county", "").replace("region", "").replace("district", "").split())
                                if geo_words and disp_words and geo_words & disp_words:
                                    return slug
                            return None

                        _county_gdf["omafra_slug"] = _county_gdf["geo_county_name"].apply(_match_county)

                        # Merge impact data
                        _impact_lookup = dict(zip(_map_data["county"], _map_data["county_impact"]))
                        _share_lookup = dict(zip(_map_data["county"], _map_data["county_share"]))
                        _display_lookup = dict(zip(_map_data["county"], _map_data["county_display"]))

                        _county_gdf["impact"] = _county_gdf["omafra_slug"].map(_impact_lookup).fillna(0)
                        _county_gdf["share"] = _county_gdf["omafra_slug"].map(_share_lookup).fillna(0)
                        _county_gdf["display_name"] = _county_gdf["omafra_slug"].map(_display_lookup).fillna(
                            _county_gdf["geo_county_name"]
                        )

                        # Format for tooltip
                        if _is_jobs:
                            _county_gdf["impact_label"] = _county_gdf["impact"].apply(lambda x: f"{x:,.0f} jobs" if x > 0 else "N/A")
                        else:
                            _county_gdf["impact_label"] = _county_gdf["impact"].apply(
                                lambda x: f"${x/1e6:,.1f}M" if x > 0 else "N/A"
                            )
                        _county_gdf["share_label"] = _county_gdf["share"].apply(lambda x: f"{x:.1%}" if x > 0 else "N/A")

                        # Color scale based on impact value
                        max_impact = _county_gdf["impact"].max() if _county_gdf["impact"].max() > 0 else 1
                        def _impact_color(val):
                            if val <= 0:
                                return [220, 220, 220, 100]
                            intensity = min(val / max_impact, 1.0)
                            # Green gradient: light -> dark
                            r = int(220 - intensity * 185)
                            g = int(240 - intensity * 100)
                            b = int(220 - intensity * 185)
                            return [r, g, b, 180]

                        _county_gdf["fill_color"] = _county_gdf["impact"].apply(_impact_color)
                        _county_gdf["line_color"] = [[80, 80, 80, 120]] * len(_county_gdf)

                        # Trim for serialization
                        _map_cols = ["geometry", "display_name", "impact_label", "share_label", "fill_color", "line_color"]
                        _map_gdf = _county_gdf[[c for c in _map_cols if c in _county_gdf.columns]]
                        _geojson = _map_gdf.__geo_interface__

                        _view = pdk.ViewState(latitude=44.0, longitude=-80.0, zoom=5.5, pitch=0)
                        _layer = pdk.Layer(
                            "GeoJsonLayer",
                            data=_geojson,
                            pickable=True,
                            stroked=True,
                            filled=True,
                            get_fill_color="properties.fill_color",
                            get_line_color="properties.line_color",
                            get_line_width=1,
                            line_width_min_pixels=1,
                            auto_highlight=True,
                            highlight_color=[255, 200, 0, 100],
                        )
                        _tooltip = {
                            "html": "<b>{display_name}</b><br/>Impact: {impact_label}<br/>Share: {share_label}",
                            "style": {
                                "backgroundColor": "#1b5e20",
                                "color": "white",
                                "fontSize": "13px",
                                "padding": "8px 12px",
                                "borderRadius": "6px",
                            },
                        }
                        _deck = pdk.Deck(layers=[_layer], initial_view_state=_view, tooltip=_tooltip, map_style="mapbox://styles/mapbox/light-v11")
                        st.pydeck_chart(_deck, height=500)

                        # Legend
                        st.markdown(
                            '<div style="display:flex; align-items:center; gap:8px; font-size:0.85rem; color:#555; margin:4px 0;">'
                            '<span style="display:inline-block; width:16px; height:16px; background:#23A035; border-radius:2px;"></span> High impact'
                            '<span style="display:inline-block; width:16px; height:16px; background:#8CC98F; border-radius:2px; margin-left:12px;"></span> Moderate'
                            '<span style="display:inline-block; width:16px; height:16px; background:#DCECDC; border-radius:2px; margin-left:12px;"></span> Low'
                            '<span style="display:inline-block; width:16px; height:16px; background:#DCDCDC; border-radius:2px; margin-left:12px;"></span> No data'
                            '</div>',
                            unsafe_allow_html=True,
                        )

                    except Exception as _map_err:
                        st.info(f"Map visualization unavailable: {_map_err}")
                else:
                    st.info("Map visualization requires boundary data and pydeck. Charts and tables are shown below.")

                st.markdown("---")

                # ── County Detail / Commodity Breakdown ──────────────────
                if _selected_county_names:
                    st.markdown("#### 🔍 Selected County Detail")

                    for _sel_name in _selected_county_names:
                        _sel_slug = _county_slug_map[_sel_name]
                        _sel_data = _county_impacts[_county_impacts["county"] == _sel_slug]

                        if _sel_data.empty:
                            continue

                        with st.expander(f"📍 {_sel_name}", expanded=True):
                            # KPIs for this county
                            _sel_output = _sel_data[_sel_data["metric"].astype(str).str.contains("Output", case=False, na=False)]["county_impact"].sum()
                            _sel_gdp = _sel_data[_sel_data["metric"].astype(str).str.contains("Gross domestic", case=False, na=False)]["county_impact"].sum()
                            _sel_jobs = _sel_data[_sel_data["metric"].astype(str).str.contains("Jobs", case=False, na=False)]["county_impact"].sum()
                            _sel_share = _sel_data["county_share"].iloc[0] if not _sel_data.empty else 0
                            _sel_fcr = _sel_data["fcr_millions"].iloc[0] if not _sel_data.empty else 0

                            _det_cols = st.columns(5)
                            with _det_cols[0]:
                                st.metric("FCR Share", f"{_sel_share:.1%}")
                            with _det_cols[1]:
                                st.metric("FCR ($M)", f"${_sel_fcr:,.1f}")
                            with _det_cols[2]:
                                st.metric("Est. Output", f"${_sel_output/1e6:,.1f}M")
                            with _det_cols[3]:
                                st.metric("Est. GDP", f"${_sel_gdp/1e6:,.1f}M")
                            with _det_cols[4]:
                                st.metric("Est. Jobs", f"{_sel_jobs:,.0f}")

                            # Commodity breakdown
                            _comm_df = get_county_commodity_breakdown(_sel_slug, _county_year)
                            if not _comm_df.empty:
                                st.markdown("**Commodity Breakdown (Farm Cash Receipts)**")

                                _comm_chart_cols = st.columns([2, 1])
                                with _comm_chart_cols[0]:
                                    _top_commodities = _comm_df.head(10)
                                    _comm_bar = alt.Chart(_top_commodities).mark_bar(
                                        cornerRadiusEnd=4, color="#059669"
                                    ).encode(
                                        y=alt.Y("commodity:N", sort="-x", title=None),
                                        x=alt.X("value_millions:Q", title="Farm Cash Receipts ($M)"),
                                        tooltip=[
                                            alt.Tooltip("commodity:N", title="Commodity"),
                                            alt.Tooltip("value_millions:Q", format="$,.1f", title="FCR ($M)"),
                                            alt.Tooltip("share_of_county_total:Q", format=".1%", title="Share of County"),
                                        ]
                                    ).properties(height=300, title=f"Top Commodities — {_sel_name}")
                                    st.altair_chart(_comm_bar, use_container_width=True)

                                with _comm_chart_cols[1]:
                                    # Pie chart of top commodities
                                    _pie_data = _comm_df.head(6).copy()
                                    _other_val = _comm_df.iloc[6:]["value_millions"].sum() if len(_comm_df) > 6 else 0
                                    if _other_val > 0:
                                        _pie_data = pd.concat([_pie_data, pd.DataFrame([{
                                            "commodity": "Other",
                                            "value_millions": _other_val,
                                            "share_of_county_total": _other_val / _comm_df["value_millions"].sum()
                                        }])], ignore_index=True)

                                    _pie = alt.Chart(_pie_data).mark_arc(innerRadius=40).encode(
                                        theta=alt.Theta("value_millions:Q"),
                                        color=alt.Color("commodity:N",
                                            scale=alt.Scale(scheme="tableau10"),
                                            legend=alt.Legend(orient="bottom", columns=2, title=None)),
                                        tooltip=[
                                            alt.Tooltip("commodity:N"),
                                            alt.Tooltip("value_millions:Q", format="$,.1f", title="$M"),
                                        ]
                                    ).properties(height=300, title="Mix")
                                    st.altair_chart(_pie, use_container_width=True)

                    st.markdown("---")

                # ── Comparison Table ─────────────────────────────────────
                st.markdown("#### 📋 Full County Comparison Table")

                # Pivot the data for a clean table
                _pivot = _county_impacts.pivot_table(
                    index=["county_display", "region", "county_share", "fcr_millions"],
                    columns="metric",
                    values="county_impact",
                    aggfunc="first"
                ).reset_index()

                _pivot = _pivot.rename(columns={"county_display": "County", "region": "Region",
                                                "county_share": "FCR Share", "fcr_millions": "FCR ($M)"})
                _pivot = _pivot.sort_values("FCR Share", ascending=False)

                # Format the dataframe
                _format_dict = {"FCR Share": "{:.1%}", "FCR ($M)": "${:,.1f}"}
                for col in _pivot.columns:
                    if col not in ["County", "Region", "FCR Share", "FCR ($M)"]:
                        if "Jobs" in col:
                            _format_dict[col] = "{:,.0f}"
                        else:
                            _format_dict[col] = "${:,.0f}"

                # Used for page metrics and debugging
                key_metrics = {
                    "Output ($)": "Output",
                    "Employment (Jobs)": "Employment", 
                    "Labor Income ($)": "Income",
                    "Value Added (GDP) ($)": "GDP",
                    "Taxes on Subsidies ($)": "Taxes"
                }

                @st.cache_data(max_entries=1, ttl=3600)
                def _load_county_boundaries(boundary_file: Path):
                    """Load Ontario CSD boundaries, dissolve to county level, and simplify to speed up map rendering."""
                    import geopandas as gpd
                    gdf = gpd.read_file(boundary_file)
                    gdf["sgc_code"] = gdf["sgc_code"].astype(str).str.zfill(7)
                    # Extract county code (first 4 digits of 7-digit SGC)
                    gdf["county_code"] = gdf["sgc_code"].str[:4]
                    # Dissolve to county level
                    county_gdf = gdf.dissolve(by="county_code", as_index=False)
                    # Simplify geometry drastically to speed up PyDeck JSON serialization
                    county_gdf["geometry"] = county_gdf["geometry"].simplify(0.01, preserve_topology=True)
                    return county_gdf

                st.dataframe(
                    _pivot.style.format(_format_dict, na_rep="—"),
                    use_container_width=True,
                    hide_index=True,
                    height=600,
                )

                # Validation note
                _table_total = _pivot["FCR Share"].sum()
                st.caption(
                    f"**Validation:** County shares sum to **{_table_total:.1%}** of provincial total. "
                    f"Year: {_county_year} | Scope: {_county_scope_label} | "
                    f"Counties: {n_counties}"
                )

                # CSV Export
                _csv = _pivot.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Download County Estimates (CSV)",
                    data=_csv,
                    file_name=f"ontario_county_impacts_{_county_year}_{_county_scope}.csv",
                    mime="text/csv",
                    key="county_csv_download",
                )

else:
    # OVER TIME ANALYSIS — Styled Altair chart
    st.markdown('<p class="section-header">📈 Historical Trends Analysis</p>', unsafe_allow_html=True)
    
    # Context banner for Over Time mode
    st.markdown(
        f'<div class="context-banner">'
        f'<span>📍 <span class="badge">{scen_a["geo"]}</span></span>'
        f'<span>🏭 <span class="badge">{scen_a["name"] or "Select an industry"}</span></span>'
        f'<span>📅 <span class="badge">{date_range[0]}–{date_range[1]}</span></span>'
        f'<span>🔬 <span class="badge">{scope_label}</span></span>'
        f'</div>',
        unsafe_allow_html=True
    )
    
    # Filter to key metrics for a clean chart
    key_metrics = {
        "Output": "Output",
        "Gross domestic product (GDP) at basic prices": "GDP at Basic Prices",
        "Jobs": "Jobs",
        "Labour income": "Labour Income",
        "Wages and salaries": "Wages & Salaries",
    }
    
    if "Year" in sum_a.columns and not sum_a.empty:
        trend_data = sum_a.copy()
        # Map to clean names, keep only key metrics
        trend_data["Metric"] = trend_data["metric"].map(key_metrics)
        trend_data = trend_data.dropna(subset=["Metric"])
        
        if not trend_data.empty:
            # Separate monetary and physical metrics
            monetary = trend_data[trend_data["Metric"] != "Jobs"]
            physical = trend_data[trend_data["Metric"] == "Jobs"]
            
            col_t1, col_t2 = st.columns([2, 1])
            
            with col_t1:
                st.markdown("#### 💰 Economic Indicators")
                if not monetary.empty:
                    chart_money = alt.Chart(monetary).mark_line(
                        strokeWidth=3, point=alt.OverlayMarkDef(size=40)
                    ).encode(
                        x=alt.X('Year:O', title='Year'),
                        y=alt.Y('impact_dollars:Q', title='Impact ($)',
                                axis=alt.Axis(format='$.2s',
                                              labelExpr="replace(datum.label, 'G', 'B')")),
                        color=alt.Color('Metric:N', scale=alt.Scale(
                            domain=['Output', 'GDP at Basic Prices', 'Labour Income', 'Wages & Salaries'],
                            range=['#2563eb', '#059669', '#d97706', '#7c3aed']
                        ), legend=alt.Legend(orient='bottom', direction='horizontal', columns=2)),
                        tooltip=[
                            alt.Tooltip('Year:O'),
                            alt.Tooltip('Metric:N'),
                            alt.Tooltip('impact_dollars:Q', format='$,.0f', title='Value')
                        ]
                    ).properties(height=350)
                    st.altair_chart(chart_money, use_container_width=True)
            
            with col_t2:
                st.markdown("#### 👷 Employment")
                if not physical.empty:
                    chart_jobs = alt.Chart(physical).mark_area(
                        line=True, opacity=0.3,
                        color='#059669'
                    ).encode(
                        x=alt.X('Year:O', title='Year'),
                        y=alt.Y('impact_dollars:Q', title='Jobs',
                                axis=alt.Axis(format=',.0f')),
                        tooltip=[
                            alt.Tooltip('Year:O'),
                            alt.Tooltip('impact_dollars:Q', format=',.0f', title='Jobs')
                        ]
                    ).properties(height=350)
                    st.altair_chart(chart_jobs, use_container_width=True)
            
            # Data export
            with st.expander("📋 View Raw Data"):
                st.dataframe(sum_a, use_container_width=True)
                csv = sum_a.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Results as CSV", csv, "impact_trends.csv", "text/csv")
        else:
            st.info("No data available for the selected parameters.")
    else:
        st.info("👈 Please select parameters in the sidebar to view historical trends.")
from app.utils import global_footer
global_footer()
