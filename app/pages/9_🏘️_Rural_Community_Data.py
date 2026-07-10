"""
Rural Ontario Community Data Dashboard
======================================
Census Profile data across 4 Census years (2006-2021) for ~600 Ontario communities.
Interactive community comparison with demographics, labour & income, housing, and social indicators.
Includes choropleth map, Chart|Data tabs, and CSV export.
"""

import io
import sys
from pathlib import Path

# --- PROJECT SETUP --- must run BEFORE any app.* imports
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]          # app/pages/ → app/ → project root
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json

from app.smart_read import smart_read

# Shared similarity engine (Red Team remediation — unified math for UI + PDF)
from app.similarity_engine import (
    get_peer_communities,
    SIMILARITY_WEIGHTS as SIM_WEIGHTS,
    INVERSE_INDICATORS as SIM_INVERSE,
)



try:
    import pydeck as pdk
    HAS_PYDECK = True
except ImportError:
    HAS_PYDECK = False

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Rural Ontario Community Data",
    page_icon="🏘️",
    layout="wide",
)

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness(
    table_ids=["18-10-0005-01", "35-10-0188-01"],
    source_labels={
        "18-10-0005-01": "Consumer Price Index",
        "35-10-0188-01": "Building Permits",
    },
)


# Custom CSS for premium look
st.markdown("""
<style>
    .community-data-header {
        background: linear-gradient(135deg, #1a5276 0%, #2e86c1 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .community-data-header h1 { color: white; margin: 0; font-size: 1.8rem; }
    .community-data-header p { color: #d5e8f0; margin: 0.3rem 0 0 0; font-size: 0.95rem; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 20px;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 2. DATA LOADING
# -----------------------------------------------------------------------------
WELLBEING_DIR = Path("data/latest/wellbeing")
INDICATORS_FILE = WELLBEING_DIR / "census_indicators.csv"
GEO_FILE = WELLBEING_DIR / "dim_geography.csv"
BOUNDARY_FILE = WELLBEING_DIR / "ontario_csd_boundaries.geojson"

# Tier 2 data source files
DERIVED_DIR = Path("data/derived")
CLIMATE_FILE = WELLBEING_DIR / "climate_normals.csv"
ARTS_FILE = WELLBEING_DIR / "arts_facility_counts.csv"
BROADBAND_FILE = DERIVED_DIR / "broadband_coverage.csv"
HEALTH_FILE = WELLBEING_DIR / "health_facility_counts.csv"
VINTAGE_FILE = WELLBEING_DIR / "amenities_vintage.json"  # Rec 2 audit fix

# Tier 3: Municipal finance (FIR)
FIR_FILE = DERIVED_DIR / "fir_indicators.csv"

# FIR indicators to include (mapped from FIR wide-format column → indicator slug)
FIR_INDICATOR_COLS = [
    # Municipal Finance
    "total_revenue", "total_expenses", "own_purpose_tax_rev",
    "total_taxable_cva", "accumulated_surplus", "net_financial_assets",
    "total_road_km", "paved_road_km", "res_building_permits_count",
    "operating_surplus", "ompf_grant", "ompf_dependency",
    "debt_interest", "tax_arrears_ratio", "ompf_relief_factor",
    "total_building_permits_count", "total_building_permits_value",
    # Data quality
    "tax_share_sum", "is_invalid_tax_sum",
    # Phase 2: Reserve Fund Health
    "total_reserves", "total_reserve_funds",
    "total_reserves_and_funds", "reserves_to_revenue",
    # Phase 2: Capital Reinvestment
    "capital_additions", "capital_reinvestment_rate",
    # Phase 2: User Fees
    "user_fees_charges", "user_fee_reliance",
    # Phase 3: Infrastructure Decay ("The Rust Indicator")
    "tca_historical_cost", "tca_accum_amortization",
    "asset_consumption_ratio",
    # Phase 3: Payroll & Cash Margin
    "total_salaries_benefits", "total_amortization_expense",
    "staffing_intensity", "cash_operating_margin",
    # Phase 3: Municipal Data (denominators)
    "total_households", "total_population",
    "avg_tax_per_household",
    # Phase 3: Debt
    "total_long_term_debt", "debt_to_revenue",
]


def _load_fir_as_long():
    """Convert wide-format FIR data to long-format census-compatible indicators.

    Returns DataFrame with columns: sgc_code, census_year, indicator, value
    """
    fir = smart_read(FIR_FILE)

    # Only use rows with valid SGC codes (lower-tier CSDs)
    if "sgc_code" not in fir.columns:
        return None
    fir["sgc_code"] = pd.to_numeric(fir["sgc_code"], errors="coerce")
    fir = fir.dropna(subset=["sgc_code"])
    fir["sgc_code"] = fir["sgc_code"].astype(int).astype(str).str.zfill(7)
    fir = fir[fir["sgc_code"].str.startswith("35")].copy()

    if len(fir) == 0:
        return None

    # Melt from wide to long
    available = [c for c in FIR_INDICATOR_COLS if c in fir.columns]
    long = fir.melt(
        id_vars=["sgc_code", "year"],
        value_vars=available,
        var_name="indicator",
        value_name="value",
    )
    # TODO (Tech Debt — Q14): The column is named "census_year" for compatibility
    # with the shared generic tab renderer, but this is FIR fiscal-year data,
    # not Census data. Refactor to "reporting_year" in next major version.
    long = long.rename(columns={"year": "census_year"})
    long = long.dropna(subset=["value"])
    long = long[["census_year", "sgc_code", "indicator", "value"]]

    return long


@st.cache_data(max_entries=1, ttl=1800)
def load_data():
    """Load census indicators, geography, and Tier 2 data sources."""
    if not INDICATORS_FILE.exists():
        return None, None
    indicators = smart_read(INDICATORS_FILE)
    indicators["sgc_code"] = indicators["sgc_code"].astype(str).str.zfill(7)
    geo = smart_read(GEO_FILE)
    geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)

    # Merge Tier 2 LONG-format data sources into indicators (broadband)
    # Note: Climate, Health, and Arts are WIDE-format and loaded separately by their display sections
    # Broadband data is ATEMPORAL — we replicate it across ALL census years
    # so it appears regardless of the year filter selected.
    tier2_long_files = [BROADBAND_FILE]
    for fpath in tier2_long_files:
        if fpath.exists():
            t2 = smart_read(fpath)
            # Robust SGC normalization: handle float strings (e.g. "3523043.0"),
            # NaN values, and ensure 7-digit zero-padded string
            t2["sgc_code"] = pd.to_numeric(t2["sgc_code"], errors="coerce")
            t2 = t2.dropna(subset=["sgc_code"])
            t2["sgc_code"] = t2["sgc_code"].astype(int).astype(str).str.zfill(7)
            # Keep only Ontario CSDs (SGC codes starting with 35)
            t2 = t2[t2["sgc_code"].str.startswith("35")].copy()
            # Replicate broadband data for ALL census years so it appears
            # regardless of the year filter.  Broadband data is atemporal.
            if "census_year" not in t2.columns:
                all_years = sorted(indicators["census_year"].unique())
                year_dfs = []
                for yr in all_years:
                    yr_df = t2.copy()
                    yr_df["census_year"] = yr
                    year_dfs.append(yr_df)
                t2 = pd.concat(year_dfs, ignore_index=True)
            indicators = pd.concat([indicators, t2], ignore_index=True)

    return indicators, geo


@st.cache_data(max_entries=1, ttl=1800)
def load_fir_indicators():
    """Load FIR data as long-format indicators (separate from Census to avoid year pollution)."""
    if not FIR_FILE.exists():
        return pd.DataFrame(columns=["census_year", "sgc_code", "indicator", "value"])
    fir_long = _load_fir_as_long()
    if fir_long is None or len(fir_long) == 0:
        return pd.DataFrame(columns=["census_year", "sgc_code", "indicator", "value"])
    return fir_long




# Q7 Fix: Remove underscore prefix from cache function arguments.
# Streamlit's @st.cache_data ignores arguments starting with '_' when
# computing the cache key, which could produce stale results if the
# underlying dataframe changes.
# Income indicators where $0 from StatCan suppression should be excluded from
# percentile rankings to avoid distorting the distribution. (Verification audit, 2026-03-09)
_INCOME_INDICATORS = {
    "median_hh_income", "median_hh_income_at", "avg_dwelling_value",
    "shelter_cost_owned_med", "shelter_cost_rented_med",
    "shelter_cost_owned_avg", "shelter_cost_rented_avg",
}

@st.cache_data(max_entries=1, ttl=1800)
def compute_percentile_ranks(indicators_df_input):
    """For each (indicator, year), compute the percentile rank of every community.
    Returns a dict: (indicator, year, sgc_code) -> percentile (0-100, 100=best).
    """
    result = {}
    for (ind, yr), grp in indicators_df_input.groupby(["indicator", "census_year"]):
        vals = grp.dropna(subset=["value"])
        if vals.empty:
            continue
        # FIX V2: Exclude $0 suppressed income values from percentile rankings
        if ind in _INCOME_INDICATORS:
            vals = vals[vals["value"] > 0]
            if vals.empty:
                continue
        # pct_rank: 0 = lowest, 1 = highest value
        pct_series = vals["value"].rank(pct=True, method="average") * 100
        # Vectorized dict build — avoids slow iterrows() loop
        for code, pct in zip(vals["sgc_code"].values, pct_series.values):
            result[(ind, yr, code)] = pct
    return result


@st.cache_data(max_entries=1, ttl=1800)
def compute_ontario_averages(indicators_df_input):
    """Pre-compute Ontario-wide median for each indicator x year."""
    return (
        indicators_df_input
        .groupby(["census_year", "indicator"])["value"]
        .median()
        .reset_index()
        .rename(columns={"value": "ont_median"})
    )


@st.cache_data(max_entries=1, ttl=1800)
def load_boundaries():
    """Load Ontario CSD boundary GeoJSON for the map."""
    if not BOUNDARY_FILE.exists():
        return None
    import geopandas as gpd
    gdf = gpd.read_file(BOUNDARY_FILE)
    gdf["sgc_code"] = gdf["sgc_code"].astype(str).str.zfill(7)
    return gdf


@st.cache_data(max_entries=1, ttl=1800)
def load_health_data():
    """Load health facility counts per CSD."""
    if not HEALTH_FILE.exists():
        return None
    hf = smart_read(HEALTH_FILE)
    # Robust SGC normalization (health file has float strings like "3523043.0")
    hf["sgc_code"] = pd.to_numeric(hf["sgc_code"], errors="coerce")
    hf = hf.dropna(subset=["sgc_code"])
    hf["sgc_code"] = hf["sgc_code"].astype(int).astype(str).str.zfill(7)
    hf = hf[hf["sgc_code"].str.startswith("35")].copy()
    return hf


indicators_df, geo_df = load_data()

if indicators_df is None:
    st.error(
        "Census indicators not found. Please run the pipeline first:\n\n"
        "```\npython scripts/fetch_census_profile.py\n```"
    )
    st.stop()

ontario_avg = compute_ontario_averages(indicators_df)
percentile_ranks = compute_percentile_ranks(indicators_df)


# Build community lookup: SGC code -> display name  (+ CSD type)
def _build_community_lookup(geo):
    lookup = {}      # code -> display_name
    type_map = {}    # code -> csd_type
    for _, row in geo.iterrows():
        code = row["sgc_code"]
        name = row.get("geo_name", code)
        county = row.get("county", "")
        csd_type = row.get("csd_type", "")
        if pd.notna(county) and county:
            display = f"{name} ({county})"
        else:
            display = str(name)
        lookup[code] = display
        type_map[code] = str(csd_type) if pd.notna(csd_type) else ""
    return lookup, type_map


community_lookup, csd_type_map = _build_community_lookup(geo_df)

# CSD type presets for the sidebar filter
CSD_TYPE_PRESETS = {
    "All Types":    None,
    "Rural":        ["Township", "Village", "Municipality"],
    "Urban":        ["City", "Town"],
    "First Nations": ["Indian reserve", "Indian settlement"],
}
ALL_CSD_TYPES = sorted(set(t for t in csd_type_map.values() if t))

# Indicator metadata: slug -> (display name, unit, category)
INDICATOR_META = {
    # Demographics
    "population":           ("Population",                " persons", "Demographics"),
    "pop_change_pct":       ("Population Change (5-Year)","%",       "Demographics"),
    "pop_density":          ("Population Density",        " /km\u00b2",  "Demographics"),
    "land_area_sqkm":       ("Land Area",                 " km\u00b2",   "Demographics"),
    "pop_0_14":             ("Youth (0-14)",              " persons", "Demographics"),
    "pop_15_64":            ("Working Age (15-64)",       " persons", "Demographics"),
    "pop_65_plus":          ("Seniors (65+)",             " persons", "Demographics"),
    "cohort_0_4":           ("Preschool Age (0-4)",       " persons", "Demographics"),
    "cohort_20_24":         ("Young Adults (20-24)",      " persons", "Demographics"),
    "cohort_85_plus":       ("Elderly (85+)",             " persons", "Demographics"),
    "avg_age":              ("Average Age",               "years",   "Demographics"),
    "median_age":           ("Median Age",                "years",   "Demographics"),
    # Labour & Income
    "median_hh_income":     ("Median Household Income",  "$",      "Labour & Income"),
    "median_hh_income_at":  ("Median After-Tax Income",  "$",      "Labour & Income"),
    "low_income_pct":       ("Low Income Rate",          "%",      "Labour & Income"),
    "in_labour_force":      ("In Labour Force",          " persons", "Labour & Income"),
    "employed":             ("Employed",                 " persons", "Labour & Income"),
    "unemployed":           ("Unemployed",               " persons", "Labour & Income"),
    "participation_rate":   ("Participation Rate",       "%",      "Labour & Income"),
    "employment_rate":      ("Employment Rate",          "%",      "Labour & Income"),
    "unemployment_rate":    ("Unemployment Rate",        "%",      "Labour & Income"),
    "not_in_labour_force":  ("Not in Labour Force",      " persons", "Labour & Income"),
    # Housing
    "owner_households":     ("Owner Households",              "",       "Housing"),
    "renter_households":    ("Renter Households",             "",       "Housing"),
    "avg_hh_size":          ("Average Household Size",        "",       "Housing"),
    # P0 FIX U2: Separate median and average shelter costs
    "shelter_cost_owned_med":  ("Shelter Cost — Owned (Median)",  "$/mo",   "Housing"),
    "shelter_cost_owned_avg":  ("Shelter Cost — Owned (Average)", "$/mo",   "Housing"),
    "shelter_cost_rented_med": ("Shelter Cost — Rented (Median)", "$/mo",   "Housing"),
    "shelter_cost_rented_avg": ("Shelter Cost — Rented (Average)","$/mo",   "Housing"),
    "unaffordable_renter_pct": ("Unaffordable Renters",       "%",      "Housing"),
    "unaffordable_owner_pct":  ("Unaffordable Owners",        "%",      "Housing"),
    "major_repairs_needed": ("Major Repairs Needed",          "",       "Housing"),
    # FIX U6: Disambiguate count vs percentage display names
    "core_housing_need":    ("Core Housing Need (Count)",     "",       "Housing"),
    "core_housing_need_pct": ("Core Housing Need (%)",        "%",      "Housing"),
    "unsuitable_housing":   ("Unsuitable Housing",            "",       "Housing"),
    "unaffordable_shelter": ("Unaffordable Shelter (30%+)",   "",       "Housing"),
    "affordable_shelter":   ("Affordable Shelter (<30%)",     "",       "Housing"),
    "avg_dwelling_value":   ("Avg Dwelling Value",            "$",      "Housing"),
    "median_dwelling_value": ("Median Dwelling Value",        "$",      "Housing"),  # N2
    "subsidized_housing_pct": ("Subsidized Housing",          "%",      "Housing"),
    "dwellings_occupied":   ("Dwellings Occupied",            "",       "Housing"),
    # N1: Crowding proxies (replaces avg_persons_per_room)
    "crowding_above_1ppr":  ("Crowded (>1 person/room)",      "",       "Housing"),
    "avg_rooms_per_dwelling": ("Avg Rooms per Dwelling",      "",       "Housing"),
    # Housing Stock
    "dwelling_single_detached": ("Single-Detached",      " dwellings", "Housing Stock"),
    "dwelling_semi_detached":   ("Semi-Detached",        " dwellings", "Housing Stock"),
    "dwelling_row":             ("Row Houses",           " dwellings", "Housing Stock"),
    "dwelling_apt_5plus":       ("Apartments (5+ storey)"," dwellings","Housing Stock"),
    "dwelling_apt_under5":      ("Apartments (<5 storey)"," dwellings","Housing Stock"),
    "dwelling_duplex":          ("Duplex",               " dwellings", "Housing Stock"),
    "dwelling_movable":         ("Movable Dwellings",    " dwellings", "Housing Stock"),
    # Household Size Distribution
    "hh_size_1":            ("1 Person",                 " households", "Household Size"),
    "hh_size_2":            ("2 Persons",                " households", "Household Size"),
    "hh_size_3":            ("3 Persons",                " households", "Household Size"),
    "hh_size_4":            ("4 Persons",                " households", "Household Size"),
    "hh_size_5_plus":       ("5+ Persons",               " households", "Household Size"),
    # Education
    "no_education":         ("No Certificate/Diploma",   " persons", "Education"),
    "high_school":          ("High School Diploma",      " persons", "Education"),
    "postsecondary":        ("Postsecondary",            " persons", "Education"),
    "trades_cert":          ("Trades Certificate",       " persons", "Education"),
    "college_cert":         ("College Diploma",          " persons", "Education"),
    "uni_bachelor_plus":    ("University (Bachelor+)",   " persons", "Education"),
    "uni_above_bachelor":   ("Above Bachelor",           " persons", "Education"),
    "uni_bachelor":         ("Bachelor's Degree",        " persons", "Education"),
    # Commuting
    "commute_driver":       ("Car (Driver)",             " persons", "Commuting"),
    "commute_passenger":    ("Car (Passenger)",          " persons", "Commuting"),
    "commute_transit":      ("Public Transit",           " persons", "Commuting"),
    "commute_walk":         ("Walked",                   " persons", "Commuting"),
    "commute_bike":         ("Bicycle",                  " persons", "Commuting"),
    "commute_walk_bike":    ("Walked/Bicycled",          " persons", "Commuting"),
    "commute_lt_15min":     ("Less than 15 Minutes",     " persons", "Commuting"),
    "commute_45_59min":     ("45\u201359 Minutes",            " persons", "Commuting"),
    "commute_60min_plus":   ("60+ Minutes",              " persons", "Commuting"),
    "commute_local":        ("Commute Locally (in CSD)", " persons", "Commuting"),
    "commute_diff_csd":     ("Commute to Different CSD", " persons", "Commuting"),
    "commute_wfh":          ("Worked at Home",           " persons", "Commuting"),
    # Diversity
    "visible_minority":     ("Visible Minority",         " persons", "Diversity"),
    "indigenous_pop":       ("Indigenous Population",    " persons", "Diversity"),
    "immigrant_pop":        ("Immigrant Population",     " persons", "Diversity"),
    "non_immigrant_pop":    ("Non-Immigrant",            " persons", "Diversity"),
    "no_religion":          ("No Religion/Secular",      " persons", "Diversity"),
    # Language
    "lang_english_only":    ("English Only",             " persons", "Language"),
    "lang_french_only":     ("French Only",              " persons", "Language"),
    "lang_bilingual":       ("Bilingual (EN/FR)",        " persons", "Language"),
    "lang_neither":         ("Neither EN nor FR",        " persons", "Language"),
    # Income Distribution (household after-tax; bands match contextual ETL extraction)
    "hh_income_under_10k":  ("Under $10K",               "households", "Income Distribution"),
    "hh_income_10k_20k":    ("$10K–$20K",                "households", "Income Distribution"),
    "hh_income_20k_30k":    ("$20K–$30K",                "households", "Income Distribution"),
    "hh_income_30k_40k":    ("$30K–$40K",                "households", "Income Distribution"),
    "hh_income_40k_50k":    ("$40K–$50K",                "households", "Income Distribution"),
    "hh_income_50k_60k":    ("$50K–$60K",                "households", "Income Distribution"),
    "hh_income_60k_70k":    ("$60K–$70K",                "households", "Income Distribution"),
    "hh_income_70k_80k":    ("$70K–$80K",                "households", "Income Distribution"),
    "hh_income_80k_90k":    ("$80K–$90K",                "households", "Income Distribution"),
    "hh_income_90k_100k":   ("$90K–$100K",               "households", "Income Distribution"),
    "hh_income_100k_125k":  ("$100K–$125K",              "households", "Income Distribution"),
    "hh_income_125k_150k":  ("$125K–$150K",              "households", "Income Distribution"),
    "hh_income_150k_plus":  ("$150K+",                   "households", "Income Distribution"),
    "hh_income_100k_plus":  ("$100K+ (aggregate)",       "households", "Income Distribution"),
    # Climate — DEPRECATED from generic tab (audit 2026-02-24)
    # Climate normals are ATEMPORAL and displayed ONLY in the standalone
    # "🌍 Environment — Climate Profile" section (§8b), loaded from
    # climate_normals.csv. No generic-tab registration needed.
    # Community Amenities — QUARANTINED from generic tab (Rec 1 + audit fix)
    # These are point-in-time snapshots (ODHF / ODCAF), NOT Census time-series.
    # Supported ONLY in standalone sections (§9 Health Access, §8c Arts & Culture).
    # Kept as metadata (not None) so backend tools know they exist.
    "arts_culture_facilities":  ("Cultural Facilities",  "",  "Community Amenities", {"supported_views": ["standalone"]}),
    "health_facilities":        ("Health Facilities",    "",  "Community Amenities", {"supported_views": ["standalone"]}),
    # Broadband Connectivity (Tier 2 — terrestrial, dwelling-weighted)
    "broadband_50_10_pct":        ("Terrestrial ≥50/10 Mbps (USO)",  "%",   "Connectivity"),
    "broadband_25_5_pct":         ("Terrestrial ≥25/5 Mbps",         "%",   "Connectivity"),
    "broadband_underserved_pct":  ("Underserved (<50/10)",            "%",   "Connectivity"),
    "broadband_unserved_pct":     ("Unserved (<5/1)",                 "%",   "Connectivity"),
    "broadband_total_dwellings":  ("Total Dwellings (2021)",          "",    "Connectivity"),
    # Municipal Finance (FIR)
    "total_revenue":            ("Total Revenue",                  "$",      "Municipal Finance"),
    "total_expenses":           ("Total Expenses",                 "$",      "Municipal Finance"),
    "operating_surplus":        ("Accounting Surplus/Deficit",      "$",      "Municipal Finance"),
    "own_purpose_tax_rev":      ("Own-Purpose Tax Revenue",        "$",      "Municipal Finance"),
    "total_taxable_cva":        ("Total Taxable CVA",              "$",      "Municipal Finance"),
    "accumulated_surplus":      ("Accumulated Surplus",            "$",      "Municipal Finance"),
    "net_financial_assets":     ("Net Financial Assets",           "$",      "Municipal Finance"),
    "ompf_grant":               ("OMPF Grant",                     "$",      "Municipal Finance"),
    "ompf_dependency":          ("OMPF Dependency",                "pct",    "Municipal Finance"),
    "ompf_relief_factor":       ("OMPF Relief Factor",             "ratio",  "Municipal Finance"),
    "debt_interest":            ("Debt Interest",                  "$",      "Municipal Finance"),
    "tax_arrears_ratio":        ("Tax Arrears Ratio",              "ratio",  "Municipal Finance"),
    "total_road_km":            ("Total Road KM",                  "km",     "Municipal Finance"),
    "paved_road_km":            ("Paved Roads",                    "km",     "Municipal Finance"),
    "res_building_permits_count": ("Building Permits",             "",       "Municipal Finance"),
    "total_building_permits_count": ("Total Building Permits",         "",     "Municipal Finance"),
    "total_building_permits_value": ("Total Building Permits Value",   "$",    "Municipal Finance"),
    # Data quality
    "tax_share_sum":              ("Tax Share Sum (QA)",               "pct",  "Municipal Finance"),
    "is_invalid_tax_sum":         ("Invalid Tax Sum Flag",             "",     "Municipal Finance"),
    # Phase 2: Reserve Fund Health
    "total_reserves":             ("Total Reserves",                   "$",    "Municipal Finance"),
    "total_reserve_funds":        ("Total Reserve Funds",              "$",    "Municipal Finance"),
    "total_reserves_and_funds":   ("Total Reserves + Reserve Funds",   "$",    "Municipal Finance"),
    "reserves_to_revenue":        ("Reserves-to-Revenue Ratio",        "pct", "Municipal Finance"),
    # Phase 2: Capital Reinvestment
    "capital_additions":          ("Capital Additions",                "$",    "Municipal Finance"),
    "capital_reinvestment_rate":   ("Capital Reinvestment Rate",       "pct",  "Municipal Finance"),
    # Phase 2: User Fees
    "user_fees_charges":          ("User Fees & Charges",              "$",    "Municipal Finance"),
    "user_fee_reliance":          ("User Fee Reliance",                "pct",  "Municipal Finance"),
    # Phase 3: Infrastructure Decay
    "tca_historical_cost":        ("TCA Historical Cost",              "$",    "Municipal Finance"),
    "tca_accum_amortization":     ("TCA Accumulated Amortization",     "$",    "Municipal Finance"),
    "asset_consumption_ratio":    ("Asset Consumption Ratio",          "pct",  "Municipal Finance"),
    # Phase 3: Payroll & Cash Margin
    "total_salaries_benefits":    ("Total Salaries & Benefits",        "$",    "Municipal Finance"),
    "total_amortization_expense": ("Total Amortization Expense",       "$",    "Municipal Finance"),
    "staffing_intensity":         ("Staffing Intensity",               "pct",  "Municipal Finance"),
    "cash_operating_margin":      ("Cash Operating Margin",            "pct",  "Municipal Finance"),
    # Phase 3: Municipal Data
    "total_households":           ("Total Households",                 "",     "Demographics"),
    "total_population":           ("Total Population (FIR)",           "",     "Demographics"),
    "avg_tax_per_household":      ("Avg Tax per Household",            "$",    "Municipal Finance"),
    # Phase 3: Debt
    "total_long_term_debt":       ("Total Long-Term Debt",             "$",    "Municipal Finance"),
    "debt_to_revenue":            ("Debt-to-Revenue Ratio",            "pct", "Municipal Finance"),
}

CATEGORIES = [
    "Demographics", "Labour & Income", "Income Distribution", "Housing", "Housing Stock",
    "Household Size", "Education", "Commuting", "Diversity", "Language",
    "Connectivity",
    "Municipal Finance",
]

# Indicators suitable for the map (rate/average indicators render better than raw counts)
MAP_FRIENDLY_INDICATORS = [
    "population", "pop_change_pct", "pop_density", "median_age", "avg_age",
    "median_hh_income", "median_hh_income_at", "low_income_pct",
    "unemployment_rate", "employment_rate", "participation_rate",
    "avg_hh_size", "shelter_cost_owned_med", "shelter_cost_rented_med",
    "unaffordable_renter_pct", "unaffordable_owner_pct",
    "avg_dwelling_value",
    # Tier 2
    "broadband_50_10_pct", "broadband_25_5_pct",
    "broadband_underserved_pct", "broadband_unserved_pct",
]

# Indicators where HIGHER = WORSE (flip delta color in snapshot)
INVERSE_INDICATORS = {
    "unemployment_rate", "low_income_pct", "unemployed",
    "unaffordable_renter_pct",
    "unaffordable_owner_pct", "major_repairs_pct",
    "core_housing_need", "unsuitable_housing",
    "broadband_underserved_pct", "broadband_unserved_pct",
}


# ---------------------------------------------------------------------------
# Amenity helpers (Rec 2, 7 audit fixes)
# ---------------------------------------------------------------------------
@st.cache_data(max_entries=1, ttl=600)
def _get_amenity_vintage(section: str) -> dict:
    """Read dynamic vintage metadata from amenities_vintage.json.

    Falls back to hardcoded defaults if the file doesn't exist.
    Cached for 10 minutes to avoid re-reading JSON on every Streamlit render.
    """
    import json as _json
    defaults = {
        "health": {"source": "Open Database of Healthcare Facilities (ODHF)", "version": "v1.1", "source_release_year": 2021},
        "arts": {"source": "Open Database of Cultural and Art Facilities (ODCAF)", "version": "v1.0", "source_release_year": 2019},
    }
    if VINTAGE_FILE.exists():
        try:
            with open(VINTAGE_FILE, "r") as f:
                vintage = _json.load(f)
            return vintage.get(section, defaults.get(section, {}))
        except Exception:
            pass
    return defaults.get(section, {})


@st.cache_data(max_entries=1, ttl=600)
def _get_ontario_population() -> float:
    """Return total Ontario population from census_indicators.csv.

    Uses the FULL set of CSDs (not just those with facilities)
    to avoid the data trap identified in the Rec 7 audit.
    Cached for 10 minutes to avoid re-reading CSV on every Streamlit render.
    """
    if not INDICATORS_FILE.exists():
        return 0
    try:
        inds = smart_read(INDICATORS_FILE)
        inds["sgc_code"] = inds["sgc_code"].astype(str).str.zfill(7)
        pop = inds[
            (inds["indicator"] == "population") &
            (inds["census_year"] == inds["census_year"].max())
        ]
        return pop["value"].sum()
    except Exception:
        return 0


def _get_rural_totals(facility_df: pd.DataFrame) -> tuple:
    """Return (rural_population, rural_facility_count) for CSDs < 30K pop.

    This gives a peer-appropriate benchmark for rural/small-town municipalities.
    """
    if "population" not in facility_df.columns:
        return 0, 0
    rural = facility_df[facility_df["population"] < 30_000].copy()
    return rural["population"].sum(), rural["total_facilities"].sum()


def _is_standalone_indicator(meta_tuple) -> bool:
    """Check if an INDICATOR_META entry is standalone-only (has 4th element with views)."""
    if len(meta_tuple) > 3 and isinstance(meta_tuple[3], dict):
        return "standalone" in meta_tuple[3].get("supported_views", [])
    return False


def _format_value(val, unit):
    """Format a numeric value with its unit.
    
    Unit types:
      '$'     - Dollar amount (no decimals)
      '$/mo'  - Monthly dollar
      '$/ha'  - Per-hectare dollar
      '%'     - Already a percentage (e.g. 45.2 → '45.2%')
      'pct'   - Decimal proportion (0-1) displayed as % (e.g. 0.22 → '22.2%')
      'rate'  - Decimal tax rate displayed as % (e.g. 0.005231 → '0.5231%')
      'ratio' - Plain ratio displayed with 4 decimal places (e.g. 0.2177)
    """
    if pd.isna(val):
        return "\u2014"
    if unit == "$":
        return f"${val:,.0f}"
    elif unit == "$/mo":
        return f"${val:,.0f}/mo"
    elif unit == "$/ha":
        return f"${val:,.2f}/ha"
    elif unit == "%":
        return f"{val:.1f}%"
    elif unit == "pct":
        return f"{val * 100:.1f}%"
    elif unit == "rate":
        return f"{val * 100:.4f}%"
    elif unit == "ratio":
        return f"{val:.4f}"
    # Q8 Fix: Handle " persons" unit explicitly (was falling through to generic formatter)
    elif unit == " persons":
        return f"{val:,.0f} persons"
    elif unit in ("years", "/km2", "km2", "ha", "km"):
        return f"{val:,.1f} {unit}"
    elif abs(val) >= 1_000_000:
        return f"{val / 1_000_000:,.1f}M"
    elif abs(val) >= 1_000:
        return f"{val:,.0f}"
    else:
        return f"{val:,.1f}" if val != int(val) else f"{int(val):,}"


def _color_change(val):
    """Conditional color for change column."""
    if isinstance(val, str):
        if val.startswith("+"):
            return "color: #2e7d32"
        elif val.startswith("-"):
            return "color: #c62828"
    return ""


def _safe_slug(text):
    """Create a filesystem-safe slug from text."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(text))


def _data_source_caption(source_name, url=None, note=None):
    """Render a compact data source attribution line below a section header."""
    link = f'<a href="{url}" target="_blank">{source_name}</a>' if url else source_name
    note_text = f" — {note}" if note else ""
    st.caption(f"\U0001f4c2 **Data Source:** {link}{note_text}", unsafe_allow_html=True)


# ── Phase 5C: Community Profile PDF Generator ────────────────────────────────
@st.cache_data(max_entries=3, ttl=1800, show_spinner=False)
def _generate_community_pdf(sgc_code, community_name, _indicators_df, _geo_df):
    """Generate a one-page community profile PDF using fpdf2."""
    from fpdf import FPDF

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header bar
    pdf.set_fill_color(27, 94, 32)  # OFA green
    pdf.rect(0, 0, 210, 28, 'F')
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 6)
    # Sanitize name for Helvetica font (ASCII only)
    _safe_name = community_name.encode('ascii', 'replace').decode('ascii')
    pdf.cell(0, 10, f'Community Profile: {_safe_name}', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(200, 230, 200)
    pdf.cell(0, 6, 'Ontario Federation of Agriculture - Rural Community Data', new_x='LMARGIN', new_y='NEXT')

    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    # Get community's latest data
    comm_data = _indicators_df[_indicators_df['sgc_code'] == sgc_code].copy()
    if comm_data.empty:
        pdf.set_font('Helvetica', '', 12)
        pdf.cell(0, 10, 'No data available for this community.', new_x='LMARGIN', new_y='NEXT')
        return bytes(pdf.output())

    latest_year = comm_data['census_year'].max()
    latest = comm_data[comm_data['census_year'] == latest_year]
    vals = dict(zip(latest['indicator'], latest['value']))

    # County lookup
    geo_row = _geo_df[_geo_df['sgc_code'] == sgc_code]
    county = geo_row['county'].iloc[0] if not geo_row.empty and 'county' in geo_row.columns else 'N/A'
    csd_type = geo_row['csd_type'].iloc[0] if not geo_row.empty and 'csd_type' in geo_row.columns else 'N/A'

    # Section helper
    def _section(title):
        pdf.set_font('Helvetica', 'B', 13)
        pdf.set_fill_color(240, 253, 244)
        pdf.cell(0, 8, f'  {title}', new_x='LMARGIN', new_y='NEXT', fill=True)
        pdf.ln(2)

    def _row(label, value, unit=''):
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(85, 6, f'  {label}:', new_x='RIGHT')
        pdf.set_font('Helvetica', 'B', 10)
        if isinstance(value, float) and not pd.isna(value):
            if unit == '$':
                pdf.cell(0, 6, f'${value:,.0f}', new_x='LMARGIN', new_y='NEXT')
            elif unit == '%':
                pdf.cell(0, 6, f'{value:.1f}%', new_x='LMARGIN', new_y='NEXT')
            else:
                pdf.cell(0, 6, f'{value:,.0f}{unit}', new_x='LMARGIN', new_y='NEXT')
        else:
            pdf.cell(0, 6, str(value) if not pd.isna(value) else 'N/A', new_x='LMARGIN', new_y='NEXT')

    # Overview
    _section('Overview')
    _row('County / District', county)
    _row('CSD Type', csd_type)
    _row('Census Year', str(int(latest_year)))
    pdf.ln(3)

    # Demographics
    _section('Demographics')
    _row('Population', vals.get('population', 'N/A'))
    _row('Population Change (5yr)', vals.get('pop_change_pct', 'N/A'), '%')
    _row('Population Density', vals.get('pop_density', 'N/A'), ' /km2')
    _row('Median Age', vals.get('median_age', 'N/A'), ' years')
    _row('Youth (0-14)', vals.get('pop_0_14', 'N/A'))
    _row('Working Age (15-64)', vals.get('pop_15_64', 'N/A'))
    _row('Seniors (65+)', vals.get('pop_65_plus', 'N/A'))
    pdf.ln(3)

    # Income and Labour
    _section('Income and Labour')
    _row('Median Household Income', vals.get('median_hh_income', 'N/A'), '$')
    _row('Median After-Tax Income', vals.get('median_hh_income_at', 'N/A'), '$')
    _row('Low Income Rate', vals.get('low_income_pct', 'N/A'), '%')
    _row('Employment Rate', vals.get('employment_rate', 'N/A'), '%')
    _row('Unemployment Rate', vals.get('unemployment_rate', 'N/A'), '%')
    pdf.ln(3)

    # Housing
    _section('Housing')
    _row('Average Household Size', vals.get('avg_hh_size', 'N/A'))
    _row('Avg Dwelling Value', vals.get('avg_dwelling_value', 'N/A'), '$')
    _row('Core Housing Need', vals.get('core_housing_need_pct', 'N/A'), '%')
    _row('Unaffordable Owners', vals.get('unaffordable_owner_pct', 'N/A'), '%')
    _row('Unaffordable Renters', vals.get('unaffordable_renter_pct', 'N/A'), '%')
    pdf.ln(3)

    # Connectivity
    _section('Broadband Connectivity')
    _row('50/10 Mbps Coverage (USO)', vals.get('broadband_50_10_pct', 'N/A'), '%')
    _row('25/5 Mbps Coverage', vals.get('broadband_25_5_pct', 'N/A'), '%')
    _row('Underserved (below 50/10)', vals.get('broadband_underserved_pct', 'N/A'), '%')
    _row('Unserved (below 5/1)', vals.get('broadband_unserved_pct', 'N/A'), '%')

    # Footer
    pdf.ln(8)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 5, f'Source: Statistics Canada Census Profile ({int(latest_year)}). Generated by OFA Farm Finance Dashboard.', new_x='LMARGIN', new_y='NEXT')

    return bytes(pdf.output())



# -----------------------------------------------------------------------------
# 3. HEADER
# -----------------------------------------------------------------------------
st.markdown("""
<div class="community-data-header">
    <h1>Rural Ontario Community Data</h1>
    <p>Census Profile data (2006-2021) for Ontario Census Subdivisions</p>
</div>
""", unsafe_allow_html=True)


# Summary KPIs
available_years = sorted(indicators_df["census_year"].unique())
n_communities = indicators_df["sgc_code"].nunique()
n_indicators = indicators_df["indicator"].nunique()

kpi_cols = st.columns(4)
with kpi_cols[0]:
    st.metric("Census Years", f"{len(available_years)}", f"{min(available_years)}-{max(available_years)}")
with kpi_cols[1]:
    st.metric("Communities", f"{n_communities:,}")
with kpi_cols[2]:
    st.metric("Indicators", f"{n_indicators}")
with kpi_cols[3]:
    st.metric("Data Points", f"{len(indicators_df):,}")


# -----------------------------------------------------------------------------
# 4. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    # --- CSD Type Filter ---
    st.header("\U0001f3f7\ufe0f Community Type")
    type_preset = st.radio(
        "Quick filter",
        options=list(CSD_TYPE_PRESETS.keys()),
        index=0,
        horizontal=True,
        help="Filter communities by Census Subdivision type",
    )

    if type_preset == "All Types":
        selected_types = st.multiselect(
            "Or pick specific types",
            options=ALL_CSD_TYPES,
            default=[],
            help="Leave empty for all types",
        )
        if not selected_types:
            selected_types = ALL_CSD_TYPES
    else:
        selected_types = CSD_TYPE_PRESETS[type_preset]

    # Filter community lookup by CSD type
    filtered_codes = {
        code for code, ctype in csd_type_map.items()
        if ctype in selected_types
    }
    filtered_community_lookup = {
        code: name for code, name in community_lookup.items()
        if code in filtered_codes
    }

    st.caption(f"{len(filtered_community_lookup)} communities match filter")
    st.divider()

    # --- Community Selection ---
    st.header("\U0001f4cd Community Selection")
    community_options = sorted(filtered_community_lookup.values())

    # Default to contrasting communities: one urban, one rural
    default_communities = []
    for default_name in ["Guelph", "Zorra", "Barrie", "Kingston"]:
        for code, display in filtered_community_lookup.items():
            if default_name in display:
                default_communities.append(display)
                break
        if len(default_communities) >= 2:
            break
    default_communities = [d for d in default_communities if d in community_options]

    selected_communities = st.multiselect(
        "Select Communities (up to 5)",
        options=community_options,
        default=default_communities[:2],
        max_selections=5,
        help="Search by community name or county",
    )

    # Phase 5C: PDF Export Button
    if len(selected_communities) == 1:
        _rl = {v: k for k, v in community_lookup.items()}
        _pdf_code = _rl.get(selected_communities[0])
        if _pdf_code:
            _pdf_bytes = _generate_community_pdf(
                _pdf_code, selected_communities[0], indicators_df, geo_df
            )
            st.download_button(
                label="📄 Export Community Profile (PDF)",
                data=_pdf_bytes,
                file_name=f"{_safe_slug(selected_communities[0])}_profile.pdf",
                mime="application/pdf",
                key="_pdf_export_btn",
            )
    elif len(selected_communities) > 1:
        st.caption("📄 Select a single community for PDF export.")

    st.divider()

    st.header("\U0001f4c5 Census Years")
    selected_years = st.multiselect(
        "Compare Years",
        options=available_years,
        default=available_years,
        help="Select which Census years to display",
    )
    st.divider()

    show_ont_avg = st.checkbox(
        "Show Ontario CSD Median on charts",
        value=True,
        help="Adds a dashed benchmark line showing the median across all Ontario Census Subdivisions (not population-weighted)",
    )
    st.divider()

    st.header("About")
    st.caption(
        "Data from Statistics Canada Census Profile (2006, 2011, 2016, 2021). "
        "Census Subdivisions (CSDs) include cities, towns, townships, and municipalities. "
        "2011 data has fewer indicators because income, labour, and education data "
        "was collected through the separate National Household Survey that year."
    )


# Reverse lookup
reverse_lookup = {v: k for k, v in community_lookup.items()}
selected_codes = [reverse_lookup[name] for name in selected_communities if name in reverse_lookup]


# -----------------------------------------------------------------------------
# 5. MAP VIEW  (shown before community selection requirement)
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("\U0001f5fa\ufe0f Ontario Community Map")
_data_source_caption(
    "Statistics Canada, Census Profile 2006–2021 & 2021 CSD Boundary File",
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E",
    "Boundaries: StatCan Cartographic Boundary Files (CSD level)"
)

boundaries_gdf = load_boundaries()

if boundaries_gdf is not None and HAS_PYDECK:
    # Map controls
    map_ctrl_cols = st.columns([2, 1])
    with map_ctrl_cols[0]:
        map_indicators = [
            s for s in MAP_FRIENDLY_INDICATORS
            if s in indicators_df["indicator"].unique()
        ]
        map_indicator_labels = {INDICATOR_META[s][0]: s for s in map_indicators}
        map_selected_label = st.selectbox(
            "Colour by indicator",
            options=list(map_indicator_labels.keys()),
            index=0,
            key="map_indicator",
        )
        map_slug = map_indicator_labels[map_selected_label]
    with map_ctrl_cols[1]:
        map_year = st.selectbox(
            "Census Year",
            options=available_years,
            index=len(available_years) - 1,
            key="map_year",
        )

    # Q4 Fix: Geographic drift warning for historical years
    if map_year != max(available_years):
        st.warning(
            f"\u26a0\ufe0f **Geographic Drift Warning:** {map_year} data is mapped to modern "
            f"{max(available_years)} municipal boundaries. Communities that were amalgamated "
            f"or dissolved before {max(available_years)} will not display."
        )

    # Get data for the selected indicator + year
    map_data = indicators_df[
        (indicators_df["indicator"] == map_slug) &
        (indicators_df["census_year"] == map_year)
    ][["sgc_code", "value"]].copy()

    # Merge with boundaries
    map_gdf = boundaries_gdf.merge(map_data, on="sgc_code", how="left")

    # Q6 Fix: HTML-escape community names to prevent XSS in pydeck tooltip
    import html as _html
    map_gdf["display_name"] = map_gdf["sgc_code"].map(
        lambda c: _html.escape(str(community_lookup.get(c, c)))
    )

    meta = INDICATOR_META[map_slug]

    # Fill NaN with 0 for rendering (but mark them)
    map_gdf["has_data"] = map_gdf["value"].notna()
    map_gdf["value_display"] = map_gdf.apply(
        lambda row: _format_value(row["value"], meta[1]) if row["has_data"] else "No data",
        axis=1,
    )
    # Q10 Fix: Removed fillna(0) anti-pattern. Pydeck handles NaN natively
    # and the has_data mask already shields the color engine.

    # Color scale
    valid_vals = map_gdf[map_gdf["has_data"]]["value"]
    if len(valid_vals) > 0:
        vmin, vmax = valid_vals.quantile(0.05), valid_vals.quantile(0.95)
        if vmin == vmax:
            vmin, vmax = valid_vals.min(), valid_vals.max()
    else:
        vmin, vmax = 0, 1

    # Normalize to 0-1 for color mapping
    map_gdf["norm"] = map_gdf["value"].clip(vmin, vmax)
    if vmax > vmin:
        map_gdf["norm"] = (map_gdf["norm"] - vmin) / (vmax - vmin)
    else:
        map_gdf["norm"] = 0.5

    # For inverse indicators (higher = worse), flip the colour ramp
    # so green = good (low unemployment) and blue = bad (high unemployment)
    if map_slug in INVERSE_INDICATORS:
        map_gdf.loc[map_gdf["has_data"], "norm"] = 1.0 - map_gdf.loc[map_gdf["has_data"], "norm"]

    # Detect if this is a broadband/connectivity indicator
    _is_broadband = map_slug.startswith("broadband_")

    # Apply color ramp:
    #   Q1 Fix: Broadband ramp reversed so Red=Bad, Yellow=Good.
    #   Broadband → Dark Red (#b30000) to Light Yellow (#ffffcc) sequential
    #   Default   → Blue (#1a5276) to Teal (#2e86c1) to Green (#27ae60)
    def _value_to_rgba(row):
        if not row["has_data"]:
            return [200, 200, 200, 100]  # grey for no data
        t = row["norm"]
        if _is_broadband:
            # Red (Bad, t=0) → Orange → Yellow (Good, t=1)
            if t < 0.5:
                s = t * 2
                r = int(179 + s * (252 - 179))
                g = int(0 + s * (141 - 0))
                b = int(0 + s * (89 - 0))
            else:
                s = (t - 0.5) * 2
                r = int(252 + s * (255 - 252))
                g = int(141 + s * (255 - 141))
                b = int(89 + s * (204 - 89))
            return [r, g, b, 200]
        else:
            # Blue -> Teal -> Green gradient
            if t < 0.5:
                s = t * 2
                r = int(26 + s * (46 - 26))
                g = int(82 + s * (134 - 82))
                b = int(118 + s * (193 - 118))
            else:
                s = (t - 0.5) * 2
                r = int(46 + s * (39 - 46))
                g = int(134 + s * (174 - 134))
                b = int(193 + s * (96 - 193))
            return [r, g, b, 180]

    map_gdf["fill_color"] = map_gdf.apply(_value_to_rgba, axis=1)

    # Q7 Fix: Use pixel-based stroke width to prevent blowout on small CSDs
    if selected_codes:
        map_gdf["line_width"] = map_gdf["sgc_code"].apply(
            lambda c: 3 if c in selected_codes else 0
        )
        map_gdf["line_color"] = map_gdf["sgc_code"].apply(
            lambda c: [255, 165, 0, 255] if c in selected_codes else [0, 0, 0, 50]
        )
    else:
        map_gdf["line_width"] = 0
        map_gdf["line_color"] = [[0, 0, 0, 50]] * len(map_gdf)

    # Q9 Fix: Trim GeoDataFrame to strictly rendering attributes before serialization
    export_cols = ["geometry", "fill_color", "line_color", "line_width", "display_name", "value_display"]
    geojson_data = map_gdf[export_cols].__geo_interface__

    # Q5 Fix: Viewport centered on full Ontario (including Northern communities)
    view_state = pdk.ViewState(
        latitude=49.0,
        longitude=-85.0,
        zoom=4.5,
        pitch=0,
    )

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geojson_data,
        pickable=True,
        stroked=True,
        filled=True,
        get_fill_color="properties.fill_color",
        get_line_color="properties.line_color",
        get_line_width="properties.line_width",
        line_width_units="pixels",  # Q7 Fix: pixel-based stroke prevents blowout
        auto_highlight=True,
        highlight_color=[255, 200, 0, 100],
    )

    tooltip = {
        "html": (
            "<b>{display_name}</b><br/>"
            f"{meta[0]}: " + "{value_display}"
        ),
        "style": {
            "backgroundColor": "#1a5276",
            "color": "white",
            "fontSize": "13px",
            "padding": "8px 12px",
            "borderRadius": "6px",
        },
    }

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v11",
    )

    st.pydeck_chart(deck, height=500)

    # Colour bar legend
    low_label = _format_value(vmin, meta[1])
    high_label = _format_value(vmax, meta[1])

    # Q1 Fix: Dynamic legend that matches the actual color ramp and inverse state
    is_inverse = map_slug in INVERSE_INDICATORS
    if _is_broadband:
        c_bad, c_mid, c_good = "#b30000", "#fc8d59", "#ffffcc"
    else:
        c_bad, c_mid, c_good = "#1a5276", "#2e86c1", "#27ae60"
    # If inverse, the left side (vmin = low value) maps to "good" color
    c_left = c_good if is_inverse else c_bad
    c_right = c_bad if is_inverse else c_good
    grad_css = f"linear-gradient(90deg, {c_left} 0%, {c_mid} 50%, {c_right} 100%)"

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px; margin:8px 0 4px 0; font-size:0.85rem; color:#555;">
            <span><b>{meta[0]}</b> ({map_year})</span>
            <span>{low_label}</span>
            <div style="width:200px; height:14px; border-radius:7px;
                        background: {grad_css};
                        border: 1px solid #ccc;"></div>
            <span>{high_label}</span>
            <span style="margin-left:12px;">\u25a0 <span style='color:#c8c8c8'>Grey</span> = no data</span>
            <span>\u25a0 <span style='color:#ffa500'>Orange</span> = selected</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.info(
        "Map boundaries not available. Run `python scripts/fetch_csd_boundaries.py` to download."
    )


# --- Guard: require community selection for detail views ---
if not selected_codes:
    st.info("\U0001f448 Select one or more communities from the sidebar to explore detailed indicators.")
    st.stop()


# Q3 Fix: Fallback to all available years if user clears the year filter,
# so the dashboard never renders completely blank.
active_years = selected_years if selected_years else available_years

# Filter data
filtered = indicators_df[
    (indicators_df["sgc_code"].isin(selected_codes)) &
    (indicators_df["census_year"].isin(active_years))
].copy()
filtered["community"] = filtered["sgc_code"].map(community_lookup)


# -----------------------------------------------------------------------------
# 6. COMMUNITY SNAPSHOT
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("\U0001f4ca Community Snapshot (Latest Available)")
_data_source_caption(
    "Statistics Canada, Census Profile 2006–2021",
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E",
    "Indicators extracted via Census Profile API"
)

latest_year = max(active_years)
snapshot = filtered[filtered["census_year"] == latest_year]

# Let users know which year the snapshot uses
if selected_years and latest_year != max(available_years):
    st.info(f"Showing {latest_year} snapshot (latest year in your filter). Deselect year filters to use the most recent Census.")

SNAPSHOT_INDICATORS = [
    "population", "median_hh_income", "unemployment_rate",
    "median_age", "pop_change_pct", "low_income_pct",
]

# Pre-compute ranks for each snapshot indicator (for the latest year)
# Q5 Fix: Rank direction is now inverse-aware. For "lower = better" metrics
# (e.g., unemployment_rate, low_income_pct), ascending=True so that the
# lowest value gets Rank 1. For "higher = better" metrics (population,
# income), ascending=False so the highest value gets Rank 1.
_rank_cache = {}
_rank_total = {}
for _slug in SNAPSHOT_INDICATORS:
    _slug_data = indicators_df[
        (indicators_df["indicator"] == _slug) &
        (indicators_df["census_year"] == latest_year)
    ].copy().dropna(subset=["value"])
    if not _slug_data.empty:
        _is_inv = _slug in INVERSE_INDICATORS
        _slug_data["rank"] = _slug_data["value"].rank(
            ascending=_is_inv, method="min"
        ).astype(int)
        _rank_cache[_slug] = dict(zip(_slug_data["sgc_code"], _slug_data["rank"]))
        _rank_total[_slug] = len(_slug_data)
    else:
        _rank_cache[_slug] = {}
        _rank_total[_slug] = 0

for code in selected_codes:
    comm_data = snapshot[snapshot["sgc_code"] == code]
    comm_name = community_lookup.get(code, code)

    st.markdown(f"**{comm_name}** ({latest_year})")
    cols = st.columns(len(SNAPSHOT_INDICATORS))
    for i, slug in enumerate(SNAPSHOT_INDICATORS):
        meta = INDICATOR_META.get(slug, (slug, "", ""))
        row = comm_data[comm_data["indicator"] == slug]
        val = row["value"].values[0] if len(row) > 0 else None

        ont_row = ontario_avg[
            (ontario_avg["census_year"] == latest_year) &
            (ontario_avg["indicator"] == slug)
        ]
        ont_val = ont_row["ont_median"].values[0] if len(ont_row) > 0 else None

        # Rank among all communities
        rank_n = _rank_total.get(slug, 0)
        rank_pos = _rank_cache.get(slug, {}).get(code)

        with cols[i]:
            delta_str = None
            delta_color = "normal"  # Streamlit default: green=up, red=down
            # Q2 Fix: Use pd.notna() instead of `is not None` to guard
            # against np.nan values that bypass Python's `is not None` check.
            if pd.notna(val) and pd.notna(ont_val):
                # Q4 Fix: Rate-based indicators use absolute percentage point
                # differences (pp) instead of misleading relative percentages.
                # Economists require pp for comparing rates.
                # NF1 Fix: Broadened to cover all rate-like units for future-proofing.
                if meta[1] in ("%", "pct", "rate"):
                    pt_diff = val - ont_val
                    # Scale decimal-based rates to whole percentage points
                    # ("pct" and "rate" store 0.15 for 15%; "%" stores 15.0)
                    if meta[1] in ("pct", "rate"):
                        pt_diff *= 100
                    delta_str = f"{pt_diff:+.1f} pp vs Ont. CSD Median"
                elif ont_val != 0:  # Zero-guard only needed for relative division
                    pct_diff = ((val - ont_val) / abs(ont_val)) * 100
                    delta_str = f"{pct_diff:+.0f}% vs Ont. CSD Median"
                # Invert color for "bad" metrics (higher = worse)
                if slug in INVERSE_INDICATORS:
                    delta_color = "inverse"

            # Percentile badge
            pct_val = percentile_ranks.get((slug, latest_year, code))

            # Q9 Fix: Contextual help tooltips for data quality warnings.
            help_parts = []
            if rank_pos:
                help_parts.append(f"Rank: {rank_pos} of {rank_n}")
            if latest_year == 2011 and slug in ("median_hh_income", "unemployment_rate", "low_income_pct"):
                help_parts.append("⚠️ 2011 NHS data — subject to non-response bias in rural areas.")
            if latest_year == 2021 and slug == "median_hh_income":
                help_parts.append("Income references the 2020 tax year (Census T-1 convention).")
            # FIX V1: Census unemployment methodology caveat
            if slug == "unemployment_rate":
                help_parts.append(
                    "Census unemployment is measured during enumeration week "
                    "(May 2021) and may differ from annual Labour Force Survey estimates."
                )
            help_text = "\n\n".join(help_parts) if help_parts else None

            st.metric(
                meta[0],
                _format_value(val, meta[1]),
                delta=delta_str,
                delta_color=delta_color,
                help=help_text,
            )
            # Mini percentile bar
            if pct_val is not None:
                is_inverse = slug in INVERSE_INDICATORS
                # For inverse metrics, flip interpretation
                display_pct = (100 - pct_val) if is_inverse else pct_val
                # Q10 Fix: Clamp to 1% floor to avoid awkward "Top 0%" labels
                if display_pct >= 50:
                    label = f"\U0001f7e2 Top {max(1, 100 - display_pct):.0f}%"
                    bar_color = "#27ae60"
                else:
                    label = f"\U0001f534 Bottom {max(1, display_pct):.0f}%"
                    bar_color = "#e74c3c"
                st.markdown(
                    f'<div style="font-size:0.82rem;color:#555;margin-top:-8px;font-weight:500;">'
                    f'{label}'
                    f'<div style="background:#ddd;border-radius:4px;height:6px;margin-top:3px;">'
                    f'<div style="background:{bar_color};width:{display_pct:.0f}%;height:6px;border-radius:4px;"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )


# -----------------------------------------------------------------------------
# 6b. TREND ALERTS — Between-Census Change Detection
# Red Team Remediation (Feb 2026): Q1–Q16 applied.
#   - Q1:  MIN_ABS_COUNT raised to 50; boundary-change guardrail (>25% = likely annex)
#   - Q2:  Removed redundant pop_change_pct rule
#   - Q3:  Income adjusted to constant dollars via CPI multiplier
#   - Q4:  Unemployment uses bidirectional "change"; 2011 NHS suppressed
#   - Q5:  Unaffordable renters converted to "crossed" trend (snapshot → trend)
#   - Q6:  Senior share converted to "share_crossed" with pop≥250 guard
#   - Q7:  low_income_pct suppressed across 2011/2016 LICO→LIM-AT boundary
#   - Q8:  Percentage thresholds dynamically scaled by time gap
#   - Q9:  Data suppression alert (prev_val exists but curr_val missing)
#   - Q10: Solved by Q2 (no more duplicate population alerts)
#   - Q11: Metric-specific MIN_ABS_INCOME = 3000 for income
#   - Q12: 2011 NHS guardrail for income/unemployment/low-income
#   - Q13: Solved by Q3 (CPI-adjusted thresholds)
#   - Q14: Explicit guard for single-year selection
#   - Q15: Dynamic caption reflecting methodology guards
#   - Q16: Severity-sorted alert rendering
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("⚡ Trend Alerts")
_data_source_caption(
    "Statistics Canada, Census Profile 2006–2021",
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E",
    "Period-over-period Census comparisons"
)

sorted_years = sorted(selected_years)

# Q14 Fix: Explicitly handle single-year selections
if len(sorted_years) < 2:
    st.info("ℹ️ Please select at least two Census years to enable Trend comparisons.")
else:
    prev_year = sorted_years[-2]
    curr_year = sorted_years[-1]

    # Q8 Fix: Time multiplier to scale percentage thresholds dynamically.
    # A 5% decline over 5 years is very different from 5% over 15 years.
    year_gap = curr_year - prev_year
    time_multiplier = max(1.0, year_gap / 5.0)

    has_alerts = False

    # Q3/Q13 Fix: Historical CPI mapping.
    # Adjusts prev_year nominal dollars to curr_year constant dollars.
    # Source: StatCan Table 18-10-0005-01, Ontario All-Items CPI.
    # N1 Fix: Census income is for the PRIOR calendar year (T-1).
    #   2021 Census → 2020 income; 2016 Census → 2015 income; etc.
    #   Multipliers use T-1 year CPI ratios (base: 2020 CPI = 1.000).
    _CPI_TO_2021 = {
        2006: 1.276,   # 2020 CPI (137.0) / 2005 CPI (107.4)
        2011: 1.176,   # 2020 CPI (137.0) / 2010 CPI (116.5)
        2016: 1.082,   # 2020 CPI (137.0) / 2015 CPI (126.6)
        2021: 1.000,
    }

    # Q2/Q5/Q6 Fix: Removed redundant pop_change_pct, converted snapshots to trends.
    # Schema: (slug, direction, base_threshold, severity, icon, msg_template)
    _ALERT_RULES = [
        ("population",           "decline",       0.05, "warning", "📉",
         "Population declined by {pct:.1f}% ({prev_val:,.0f} → {curr_val:,.0f})"),
        ("median_hh_income",     "real_change",   0.10, "info",    "💰",
         "Real median income shifted by {pct:+.1f}% (inflation-adjusted, {prev_val_adj:,.0f} → {curr_val:,.0f} in {curr_year} dollars)"),
        ("unemployment_rate",    "abs_change",    3.0,  "error",   "🔴",
         "Unemployment shifted by {abs_change:+.1f}pp ({prev_val:.1f}% → {curr_val:.1f}%)"),
        ("unaffordable_renter_pct", "crossed",    35.0, "warning", "🏠",
         "Unaffordable renters crossed 35% threshold (now {curr_val:.1f}%)"),
        ("pop_65_plus",          "share_crossed", 0.25, "info",    "👴",
         "Senior share crossed 25% (now {share_pct:.1f}%)"),
        ("low_income_pct",       "spike",         3.0,  "warning", "📊",
         "Low income rate spiked by {abs_change:+.1f}pp ({prev_val:.1f}% → {curr_val:.1f}%)"),
    ]

    # Q16 Fix: Sort weight map (error > warning > info)
    _SEVERITY_WEIGHT = {"error": 0, "warning": 1, "info": 2}

    # N4 Fix: COVID-19 artefact warning for 2021 Census data
    if 2021 in (prev_year, curr_year):
        st.info(
            "🦠 **COVID-19 Artefact Warning:** "
            "2021 Census labour data reflects the May 2021 Wave 3 "
            "stay-at-home order (temporarily inflating unemployment). "
            "Income data reflects 2020 pandemic benefits like CERB "
            "(artificially inflating medians and depressing poverty rates)."
        )

    for code in selected_codes:
        comm_name = community_lookup.get(code, code)
        comm_alerts = []

        for slug, direction, base_threshold, severity, icon, msg_template in _ALERT_RULES:

            # Q4/Q7/Q12 Fix: Suppress comparisons bridging major methodological breaks
            if slug in ("unemployment_rate", "median_hh_income", "low_income_pct"):
                if 2011 in (prev_year, curr_year):
                    continue  # 2011 NHS non-response bias
            if slug == "low_income_pct" and prev_year < 2016 and curr_year >= 2016:
                continue  # LICO → LIM-AT methodology shift

            curr_row = indicators_df[
                (indicators_df["sgc_code"] == code) &
                (indicators_df["indicator"] == slug) &
                (indicators_df["census_year"] == curr_year)
            ]
            prev_row = indicators_df[
                (indicators_df["sgc_code"] == code) &
                (indicators_df["indicator"] == slug) &
                (indicators_df["census_year"] == prev_year)
            ]

            curr_val = (
                curr_row["value"].values[0]
                if len(curr_row) > 0 and pd.notna(curr_row["value"].values[0])
                else None
            )
            prev_val = (
                prev_row["value"].values[0]
                if len(prev_row) > 0 and pd.notna(prev_row["value"].values[0])
                else None
            )

            # Q9 Fix: Data suppression alert
            if prev_val is not None and curr_val is None:
                comm_alerts.append((
                    "error", "🫙",
                    f"Data for '{slug}' suppressed in {curr_year} "
                    f"(possible severe population drop or non-response).",
                ))
                continue
            if curr_val is None or prev_val is None:
                continue

            try:
                # Q8: Scale percentage thresholds for multi-Census-cycle comparisons
                threshold = (
                    base_threshold * time_multiplier
                    if direction in ("decline", "real_change")
                    else base_threshold
                )

                # ── DECLINE (population) ────────────────────────────
                if direction == "decline" and prev_val > 0:
                    pct = (curr_val - prev_val) / prev_val
                    abs_diff = abs(curr_val - prev_val)
                    # Q1 Fix: Raised floor to 50 to suppress rounding noise
                    if pct < -threshold and abs_diff >= 50:
                        # N3 Fix: Scale boundary guardrail with time_multiplier
                        boundary_threshold = -0.25 * time_multiplier
                        if pct < boundary_threshold:
                            # Q1 guardrail: large drop likely a CSD boundary change
                            comm_alerts.append((
                                "warning", "🗺️",
                                f"Population dropped {abs(pct)*100:.1f}%. "
                                f"Likely a CSD boundary adjustment "
                                f"({prev_val:,.0f} → {curr_val:,.0f}).",
                            ))
                        else:
                            comm_alerts.append((severity, icon, msg_template.format(
                                pct=pct * 100, prev_val=prev_val, curr_val=curr_val)))

                # ── REAL_CHANGE (CPI-adjusted income) ───────────────
                elif direction == "real_change" and prev_val > 0:
                    # Q3/Q11 Fix: Adjust to constant dollars
                    cpi_prev = _CPI_TO_2021.get(prev_year, 1.0)
                    cpi_curr = _CPI_TO_2021.get(curr_year, 1.0)
                    cpi_ratio = cpi_prev / cpi_curr   # >1 when prev is older
                    real_prev = prev_val * cpi_ratio
                    pct = (curr_val - real_prev) / real_prev
                    # Q11 Fix: Metric-specific floor for income ($3,000)
                    if abs(pct) > threshold and abs(curr_val - real_prev) >= 3000:
                        comm_alerts.append((severity, icon, msg_template.format(
                            pct=pct * 100,
                            prev_val_adj=real_prev,
                            curr_val=curr_val,
                            curr_year=curr_year,
                        )))

                # ── ABS_CHANGE (bidirectional rate shift) ───────────
                elif direction == "abs_change":
                    # Q4 Fix: Fires for increases AND decreases
                    abs_change = curr_val - prev_val
                    if abs(abs_change) > threshold:
                        comm_alerts.append((severity, icon, msg_template.format(
                            abs_change=abs_change,
                            prev_val=prev_val, curr_val=curr_val)))

                # ── SPIKE (unidirectional increase) ─────────────────
                elif direction == "spike":
                    abs_change = curr_val - prev_val
                    if abs_change > threshold:
                        comm_alerts.append((severity, icon, msg_template.format(
                            abs_change=abs_change,
                            prev_val=prev_val, curr_val=curr_val)))

                # ── CROSSED (snapshot → trend: previously below, now above) ─
                elif direction == "crossed":
                    # Q5 Fix: Only fire when threshold is NEWLY crossed
                    if curr_val > threshold and prev_val <= threshold:
                        comm_alerts.append((severity, icon, msg_template.format(
                            curr_val=curr_val)))

                # ── SHARE_CROSSED (demographic share threshold) ─────
                elif direction == "share_crossed":
                    # Q6 Fix: Require pop ≥ 250 to insulate against rounding noise
                    pop_curr_row = indicators_df[
                        (indicators_df["sgc_code"] == code) &
                        (indicators_df["indicator"] == "population") &
                        (indicators_df["census_year"] == curr_year)
                    ]
                    pop_prev_row = indicators_df[
                        (indicators_df["sgc_code"] == code) &
                        (indicators_df["indicator"] == "population") &
                        (indicators_df["census_year"] == prev_year)
                    ]
                    pop_curr = (
                        pop_curr_row["value"].values[0]
                        if len(pop_curr_row) > 0 and pd.notna(pop_curr_row["value"].values[0])
                        else None
                    )
                    pop_prev = (
                        pop_prev_row["value"].values[0]
                        if len(pop_prev_row) > 0 and pd.notna(pop_prev_row["value"].values[0])
                        else None
                    )
                    if (pop_curr and pop_curr >= 250 and pop_prev and pop_prev >= 250):
                        curr_share = curr_val / pop_curr
                        prev_share = prev_val / pop_prev
                        if curr_share >= threshold and prev_share < threshold:
                            comm_alerts.append((severity, icon, msg_template.format(
                                share_pct=curr_share * 100)))

            except (ValueError, ZeroDivisionError, TypeError):
                continue

        if comm_alerts:
            has_alerts = True
            st.markdown(f"**{comm_name}** — {prev_year} → {curr_year}")
            # Q16 Fix: Sort by severity (error → warning → info)
            comm_alerts.sort(key=lambda x: _SEVERITY_WEIGHT.get(x[0], 99))
            for sev, icon, message in comm_alerts:
                if sev == "error":
                    st.error(f"{icon} {message}")
                elif sev == "warning":
                    st.warning(f"{icon} {message}")
                else:
                    st.info(f"{icon} {message}")

    if not has_alerts:
        st.success("✅ No significant trend alerts detected for the selected communities.")

    # Q15 Fix: Dynamic, robust caption
    st.caption(
        f"Comparing Census {prev_year} → {curr_year} ({year_gap}-year span). "
        f"Percentage thresholds are scaled for the time interval. "
        f"Income changes are inflation-adjusted (CPI). "
        f"Comparisons bridging 2011 NHS are suppressed for income, "
        f"unemployment, and low-income indicators."
    )


# -----------------------------------------------------------------------------
# 7. FIND SIMILAR COMMUNITIES
# Red Team Remediation 2026-02-27: Q1–Q18, A1–A2, N1–N3 applied.
# Uses shared engine: app/similarity_engine.py
# -----------------------------------------------------------------------------

# N2 Fix: Cache wrappers to avoid re-computing on every Streamlit re-render
@st.cache_data(max_entries=1, show_spinner=False)
def _cached_peer_engine(df, ref_code, year, exclude_tuple):
    """Cached wrapper around the shared similarity engine."""
    exclude = list(exclude_tuple) if exclude_tuple else None
    return get_peer_communities(df, ref_code, year, exclude_codes=exclude)

@st.cache_data(max_entries=1, show_spinner=False)
def _cached_display_profile(df, year, cols_tuple):
    """Cached pivot of raw (un-logged) indicator values for UI display."""
    return df[
        (df["census_year"] == year) & (df["indicator"].isin(cols_tuple))
    ].pivot_table(index="sgc_code", columns="indicator", values="value", aggfunc="mean")

st.markdown("---")

with st.expander("🔍 Find Similar Communities", expanded=True):
    if len(selected_codes) == 0:
        st.info("Select a community first.")
    else:
        ref_code = selected_codes[0]
        ref_name = community_lookup.get(ref_code, ref_code)

        # Pin latest_year to max available Census year — Fixes Q17
        _sim_year = max(available_years)

        with st.spinner("Computing community similarity..."):
            # FIX V3: Exclude pop ≤ 5 micro-communities from peer finder.
            # These are StatCan random-rounded CSDs that distort similarity scores.
            _micro_pops = indicators_df[
                (indicators_df["indicator"] == "population")
                & (indicators_df["census_year"] == _sim_year)
                & (indicators_df["value"] <= 5)
            ]["sgc_code"].unique().tolist()
            _exclude = list(set(list(selected_codes) + _micro_pops))

            # N2 Fix: Use cached wrapper (tuple for hashability)
            top10, sim_scores = _cached_peer_engine(
                indicators_df, ref_code, _sim_year, tuple(_exclude),
            )

        if top10 is not None and not top10.empty:
            # ── Gap Analysis ── Fixes Q7, Q8, Q12, Q15
            st.markdown(f"### 📊 Gap Analysis for **{ref_name}**")

            # Align gap indicators to similarity weights + low_income_pct — Fixes Q12
            gap_indicators = list(SIM_WEIGHTS.keys()) + ["low_income_pct"]

            # N1 Fix: Unify fetch list so compare_indicators (e.g. avg_dwelling_value)
            # are included in the display profile
            compare_indicators = [
                "population", "median_hh_income", "unemployment_rate",
                "median_age", "pop_density", "avg_dwelling_value",
            ]
            _fetch_cols = list(set(gap_indicators + compare_indicators))

            # N2 Fix: Use cached display profile (tuple for hashability)
            _gap_profile = _cached_display_profile(
                indicators_df, _sim_year, tuple(_fetch_cols)
            )

            gap_cols = st.columns(4)
            for i, slug in enumerate(gap_indicators):
                if slug not in _gap_profile.columns:
                    continue

                col_data = _gap_profile[slug].dropna()

                # Fix Q8: explicit missing-data guard
                if ref_code not in col_data.index:
                    with gap_cols[i % 4]:
                        meta = INDICATOR_META.get(slug, (slug, "", ""))
                        st.markdown(f"**{meta[0]}**  \n⚪ No data available")
                    continue

                ref_val = col_data[ref_code]
                if pd.isna(ref_val):
                    continue

                meta = INDICATOR_META.get(slug, (slug, "", ""))

                # 1. Standard statistical rank (lowest value ALWAYS gets rank 1)
                ranks = col_data.rank(ascending=True, method="min")
                rank_pos = int(ranks[ref_code])
                rank_total = len(col_data)

                # 2. Literal statistical percentile (0% = lowest value)
                stat_percentile = (rank_pos / rank_total) * 100

                # 3. Performance percentile (100% = best outcome) — Fixes Q7
                is_inverse = slug in INVERSE_INDICATORS
                perf_percentile = (100 - stat_percentile) if is_inverse else stat_percentile

                # 4. Display clamp — Fixes Q15 (0% CSS width = invisible bar)
                display_pct = max(2, min(98, perf_percentile))

                if perf_percentile >= 75:
                    color = "#27ae60"
                    badge = "🟢"
                elif perf_percentile >= 50:
                    color = "#f39c12"
                    badge = "🟡"
                elif perf_percentile >= 25:
                    color = "#e67e22"
                    badge = "🟠"
                else:
                    color = "#e74c3c"
                    badge = "🔴"

                with gap_cols[i % 4]:
                    st.markdown(
                        f"**{meta[0]}**  \n"
                        f"{badge} Rank **{rank_pos}** / {rank_total}  \n"
                        f"Value: {_format_value(ref_val, meta[1])}"
                    )
                    st.markdown(
                        f'<div style="background:#ddd;border-radius:4px;height:8px;margin-top:2px;">'
                        f'<div style="background:{color};width:{display_pct:.0f}%;height:8px;border-radius:4px;"></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # ── Peer Comparison Table ── Fixes Q13 (sortable numeric columns)
            st.markdown("### 🤝 Top 10 Similar Communities")

            # compare_indicators already defined above (N1 fix)
            compare_labels = [INDICATOR_META.get(s, (s,))[0] for s in compare_indicators]

            rows = []
            for sim_code, dist in top10.items():
                sim_name = community_lookup.get(sim_code, sim_code)
                sim_type = csd_type_map.get(sim_code, "")
                similarity = float(sim_scores.loc[sim_code])
                row_data = {
                    "Community": sim_name,
                    "Type": sim_type,
                    "Similarity (%)" : round(similarity, 1),
                }
                for s_slug in compare_indicators:
                    s_label = INDICATOR_META.get(s_slug, (s_slug,))[0]
                    val = (
                        _gap_profile.loc[sim_code, s_slug]
                        if s_slug in _gap_profile.columns and sim_code in _gap_profile.index
                        else None
                    )
                    row_data[s_label] = float(val) if val is not None and pd.notna(val) else None
                rows.append(row_data)

            if rows:
                peer_df = pd.DataFrame(rows)

                # Fix Q13: native numeric formatting via st.column_config
                _peer_col_config = {
                    "Community": st.column_config.TextColumn("Community"),
                    "Type": st.column_config.TextColumn("Type"),
                    "Similarity (%)": st.column_config.NumberColumn("Similarity", format="%.0f%%"),
                }
                for s_slug in compare_indicators:
                    s_meta = INDICATOR_META.get(s_slug, (s_slug, "", ""))
                    s_label = s_meta[0]
                    if s_meta[1] == "$":
                        _peer_col_config[s_label] = st.column_config.NumberColumn(s_label, format="$%,.0f")
                    elif s_meta[1] == "%":
                        _peer_col_config[s_label] = st.column_config.NumberColumn(s_label, format="%.1f%%")
                    elif s_meta[1] in ("/km2", "years"):
                        _peer_col_config[s_label] = st.column_config.NumberColumn(s_label, format="%,.1f")
                    else:
                        _peer_col_config[s_label] = st.column_config.NumberColumn(s_label, format="%,.0f")

                st.dataframe(
                    peer_df,
                    column_config=_peer_col_config,
                    use_container_width=True,
                    hide_index=True,
                )

                # Fix Q11: Disclaimer about excluded sidebar communities
                st.caption(
                    "ℹ️ Communities selected in the sidebar are **excluded** from peer results "
                    "to ensure independence. Similarity is absolute (exponential decay of z-score distance)."
                )

                # CSV Export (raw numeric — no pre-formatting)
                csv_bytes = peer_df.to_csv(index=False).encode("utf-8")
                ref_slug = ref_name.split(" (")[0].replace(" ", "_")
                st.download_button(
                    label="📥 Download Peer Comparison (CSV)",
                    data=csv_bytes,
                    file_name=f"peer_comparison_{ref_slug}_{_sim_year}.csv",
                    mime="text/csv",
                    help="Download the peer comparison table as CSV",
                    key=f"peer_csv_{ref_slug}_{_sim_year}",
                )
            else:
                st.info("Not enough data to compute similarity.")

            # Fix Q14: Methodology expander
            with st.expander("ℹ️ How are peers calculated?"):
                st.markdown(
                    "Peers are determined by **log-normalized, weighted z-score "
                    "Euclidean distance** across exactly **7 Census indicators**:\n\n"
                    + "\n".join(
                        f"- **{INDICATOR_META.get(k, (k,))[0]}** (weight {v}×)"
                        for k, v in SIM_WEIGHTS.items()
                    )
                    + "\n\n"
                    "Population, income, and density are log-transformed before "
                    "normalization to prevent large urban centres from dominating. "
                    "Missing values are excluded pairwise (not filled with zero). "
                    "The similarity score uses exponential decay: a distance of 0 → 100% match, "
                    "distance of 2 → ~45% match."
                )

        elif top10 is None:
            st.warning(f"No indicator data available for {ref_name} in {_sim_year}.")
        else:
            st.info("Not enough data to compute similarity.")


# -----------------------------------------------------------------------------
# 7b. FISCAL BENCHMARKING  (Phase 3: Consultant-Grade Peer Comparison)
# Audit 2026-02-26: Red team remediations Q1-Q20, A1-A2 applied.
# -----------------------------------------------------------------------------
import math

st.markdown("---")
st.subheader("🏛️ Fiscal Benchmarking — Peer Comparison")
_data_source_caption(
    "Ontario Ministry of Municipal Affairs & Housing — Financial Information Returns (FIR)",
    "https://efis.fma.csc.gov.on.ca/fir/",
    "Schedules 10, 12, 22A, 40, 51, 60, 70, 71, 72, 74, 81"
)

# Consultant-grade indicators for benchmarking
# Q19 Audit Fix: Replaced 1.01 sentinel with math.inf for unbounded top band
# Q1/Q3 Audit Fix: debt_to_revenue unit changed from "ratio" to "pct" (BMA standard)
# Q6 Audit Fix: Operating Surplus relabeled to clarify PSAB accrual basis
BENCHMARK_INDICATORS = [
    # (slug, display_name, unit, risk_bands)
    # risk_bands: list of (threshold, label, color) — None = no bands
    ("asset_consumption_ratio", "Asset Consumption Ratio", "pct",
     [
         (0.50, "Low Risk", "#27ae60"),
         (0.75, "Moderate Risk", "#f39c12"),
         (math.inf, "High Risk", "#e74c3c"),
     ]),
    ("staffing_intensity", "Staffing Intensity", "pct", None),
    ("cash_operating_margin", "Cash Operating Margin", "pct", None),
    ("debt_to_revenue", "Debt-to-Revenue", "pct",
     [
         (0.25, "Healthy", "#27ae60"),
         (0.50, "Moderate", "#f39c12"),
         (math.inf, "Tight", "#e74c3c"),
     ]),
    ("avg_tax_per_household", "Avg Tax / Household", "$", None),
    ("reserves_to_revenue", "Reserves-to-Revenue", "pct", None),
    ("capital_reinvestment_rate", "Capital Reinvestment Rate", "pct", None),
    ("ompf_dependency", "OMPF Dependency", "pct", None),
    ("user_fee_reliance", "User Fee Reliance", "pct", None),
    ("operating_surplus", "Accounting Surplus / (Deficit) ⁽ᵃᶜᶜʳᵘᵃˡ⁾", "$", None),
]

with st.expander("🏛️ Fiscal Benchmarking — Peer Comparison", expanded=True):
    _bench_fir = load_fir_indicators()

    if _bench_fir.empty:
        st.info("No FIR data available. Run the FIR ETL pipeline first: `python scripts/process_fir.py`")
    elif len(selected_codes) == 0:
        st.info("Select at least one community to begin benchmarking.")
    else:
        # Q17 Audit Fix: Label clarified to "FIR Reporting Year"
        _bench_years = sorted(_bench_fir["census_year"].unique(), reverse=True)
        _bench_year = st.selectbox(
            "FIR Reporting Year",
            _bench_years,
            index=0,
            key="bench_year_sel",
            help="Select the FIR fiscal reporting year for the comparison. This is the municipal fiscal year, not a Census year.",
        )

        # Focus municipality = first selected community
        _focus_code = selected_codes[0]
        _focus_name = community_lookup.get(_focus_code, _focus_code)

        # --- Peer selector ---
        # Build list of all communities with FIR data for this year
        _bench_yr_data = _bench_fir[_bench_fir["census_year"] == _bench_year]
        _bench_codes = sorted(_bench_yr_data["sgc_code"].unique())
        _bench_names = {c: community_lookup.get(c, c) for c in _bench_codes}

        # Q8 Audit Fix: Graceful failure if focus municipality has no FIR data
        if _focus_code not in _bench_codes:
            st.error(
                f"⚠️ FIR data for **{_focus_name}** is not available for {_bench_year}. "
                f"This may be due to late filing, an unorganized territory, or a missing SGC crosswalk entry. "
                f"Try selecting a different year or community."
            )
        else:
            # Default peers: other selected communities (up to 5)
            _default_peers = [c for c in selected_codes[1:6] if c in _bench_codes]

            _peer_codes = st.multiselect(
                f"Select up to 5 peer municipalities to compare against **{_focus_name}**",
                options=[c for c in _bench_codes if c != _focus_code],
                default=_default_peers,
                format_func=lambda c: _bench_names.get(c, c),
                max_selections=5,
                key="bench_peer_sel",
                help="Choose municipalities to benchmark against. Tip: use the 'Find Similar Communities' section above to identify peers.",
            )

            _all_bench_codes = [_focus_code] + _peer_codes

            # --- Build scorecard table ---
            # Q16 Audit Fix: aggfunc="last" for deterministic latest-submission ordering
            _bench_pivot = _bench_yr_data[
                _bench_yr_data["sgc_code"].isin(_all_bench_codes)
            ].pivot_table(
                index="sgc_code", columns="indicator", values="value", aggfunc="last"
            )

            if _bench_pivot.empty:
                st.warning(f"No FIR data available for the selected communities in {_bench_year}.")
            else:
                # --- Scorecard Table ---
                st.markdown(f"### 📊 Fiscal Scorecard — {_bench_year}")
                st.caption(
                    f"**Focus:** {_focus_name} (highlighted in blue) vs. "
                    f"{len(_peer_codes)} peer{'s' if len(_peer_codes) != 1 else ''}"
                )

                # Q7 Audit Fix: Keep raw numeric values for native Streamlit sorting
                _raw_rows = []
                for _bc in _all_bench_codes:
                    _bname = community_lookup.get(_bc, _bc)
                    _row = {"Municipality": _bname}
                    for _slug, _label, _unit, _bands in BENCHMARK_INDICATORS:
                        _val = _bench_pivot.loc[_bc, _slug] if (
                            _bc in _bench_pivot.index and _slug in _bench_pivot.columns
                        ) else None
                        if _val is not None and pd.notna(_val):
                            _val = float(_val)
                            # Pre-multiply decimals for display as percentages
                            if _unit == "pct":
                                _val = _val * 100
                            _row[_label] = _val
                        else:
                            _row[_label] = None
                    _raw_rows.append(_row)

                _score_df = pd.DataFrame(_raw_rows)

                # Q7 Audit Fix: Use st.column_config for formatted, sortable columns
                _col_config = {"Municipality": st.column_config.TextColumn("Municipality")}
                for _slug, _label, _unit, _bands in BENCHMARK_INDICATORS:
                    if _unit == "$":
                        _col_config[_label] = st.column_config.NumberColumn(_label, format="$%d")
                    elif _unit == "pct":
                        _col_config[_label] = st.column_config.NumberColumn(_label, format="%.1f%%")
                    elif _unit == "ratio":
                        _col_config[_label] = st.column_config.NumberColumn(_label, format="%.4f")

                # Style: highlight focus row
                def _highlight_focus(row):
                    if row["Municipality"] == _focus_name:
                        return ["background-color: rgba(46, 134, 193, 0.15); font-weight: bold"] * len(row)
                    return [""] * len(row)

                st.dataframe(
                    _score_df.style.apply(_highlight_focus, axis=1),
                    column_config=_col_config,
                    use_container_width=True,
                    hide_index=True,
                    height=min(400, 60 + 38 * len(_raw_rows)),
                )

                # --- MMAH Risk Band Legend ---
                # Q10 Audit Fix: Filter out math.inf sentinel from legend display
                _risk_indicators = [
                    (slug, label, bands) for slug, label, _, bands in BENCHMARK_INDICATORS if bands
                ]
                if _risk_indicators:
                    _legend_parts = []
                    for _slug, _label, _bands in _risk_indicators:
                        _parts = []
                        for _thr, _lbl, _clr in _bands:
                            if math.isfinite(_thr):
                                _parts.append(
                                    f'<span style="color:{_clr};font-weight:bold">■</span> {_lbl} (≤{_thr:.0%})'
                                )
                            else:
                                # Highest band: use "> previous threshold" label
                                _prev_thr = max(t for t, _, _ in _bands if math.isfinite(t))
                                _parts.append(
                                    f'<span style="color:{_clr};font-weight:bold">■</span> {_lbl} (>{_prev_thr:.0%})'
                                )
                        _legend_parts.append(f"**{_label}:** {' · '.join(_parts)}")
                    st.markdown(
                        '<div style="font-size:0.8rem;color:#666;margin-top:-8px;margin-bottom:12px">'
                        + " &nbsp;|&nbsp; ".join(_legend_parts) + "</div>",
                        unsafe_allow_html=True,
                    )

                # Q6 Audit Fix: Accrual basis caveat
                st.caption(
                    "⚠️ **Note:** 'Accounting Surplus' is a PSAB accrual-based figure. "
                    "It includes non-cash items (amortization) and capital grants, "
                    "and does **not** represent cash available to the municipality."
                )

                # --- Bar Chart Comparison ---
                st.markdown("### 📈 Visual Comparison")
                _chart_options = [label for _, label, _, _ in BENCHMARK_INDICATORS]
                _chart_choice = st.selectbox(
                    "Select metric to visualize",
                    _chart_options,
                    index=0,
                    key="bench_chart_sel",
                )

                # Find the matching slug/unit/bands
                _chart_slug, _chart_label, _chart_unit, _chart_bands = next(
                    (s, l, u, b) for s, l, u, b in BENCHMARK_INDICATORS if l == _chart_choice
                )

                _chart_data = []
                for _bc in _all_bench_codes:
                    _bname = community_lookup.get(_bc, _bc)
                    _val = _bench_pivot.loc[_bc, _chart_slug] if (
                        _bc in _bench_pivot.index and _chart_slug in _bench_pivot.columns
                    ) else None
                    if _val is not None and pd.notna(_val):
                        _chart_data.append({
                            "Municipality": _bname,
                            "Value": float(_val),
                            "Is Focus": _bc == _focus_code,
                        })

                if _chart_data:
                    import plotly.graph_objects as go

                    _chart_df = pd.DataFrame(_chart_data)
                    _chart_df = _chart_df.sort_values("Value", ascending=True)

                    _bar_colors = [
                        "#2e86c1" if row["Is Focus"] else "#85c1e9"
                        for _, row in _chart_df.iterrows()
                    ]

                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        y=_chart_df["Municipality"],
                        x=_chart_df["Value"],
                        orientation="h",
                        marker_color=_bar_colors,
                        text=[_format_value(v, _chart_unit) for v in _chart_df["Value"]],
                        textposition="outside",
                        textfont=dict(size=12),
                        cliponaxis=False,  # Q11 Audit Fix: prevent text label clipping
                    ))

                    # Q19 Audit Fix: Draw risk lines only for finite thresholds
                    if _chart_bands:
                        for _thr, _lbl, _clr in _chart_bands:
                            if math.isfinite(_thr):
                                fig.add_vline(
                                    x=_thr, line_dash="dash", line_color=_clr,
                                    line_width=2,
                                    annotation_text=f"{_lbl} ({_thr:.0%})",
                                    annotation_position="top",
                                    annotation_font_color=_clr,
                                    annotation_font_size=11,
                                )

                    fig.update_layout(
                        title=f"{_chart_label} — {_bench_year}",
                        xaxis_title=_chart_label,
                        yaxis_title="",
                        height=max(300, 80 * len(_chart_data)),
                        # Q11 Audit Fix: Increased right margin, disabled axis clipping
                        margin=dict(l=10, r=150, t=50, b=40),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(size=13),
                        showlegend=False,
                    )


                    # Format x-axis for percentages/ratios
                    if _chart_unit == "pct":
                        fig.update_xaxes(tickformat=".1%")
                    elif _chart_unit == "$":
                        fig.update_xaxes(tickformat="$,.0f")
                    elif _chart_unit == "ratio":
                        fig.update_xaxes(tickformat=".3f")

                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info(f"No data available for '{_chart_label}' in {_bench_year}.")

                # --- Multi-Year Trend Comparison ---
                st.markdown("### 📉 Trend Over Time")
                _trend_slug = _chart_slug  # Use the same selected metric
                _trend_label = _chart_label
                _trend_unit = _chart_unit
                # Q12 Audit Fix: True decoupling — fetch bands from config, not bar chart state
                _trend_bands = next(
                    (bands for slug, _, _, bands in BENCHMARK_INDICATORS if slug == _trend_slug),
                    None
                )

                _trend_data = _bench_fir[
                    (_bench_fir["sgc_code"].isin(_all_bench_codes)) &
                    (_bench_fir["indicator"] == _trend_slug)
                ].copy()

                if not _trend_data.empty:
                    _trend_data["Municipality"] = _trend_data["sgc_code"].map(community_lookup)
                    _trend_data = _trend_data.sort_values("census_year")

                    import plotly.express as px

                    fig_trend = px.line(
                        _trend_data,
                        x="census_year",
                        y="value",
                        color="Municipality",
                        markers=True,
                        title=f"{_trend_label} — Time Series",
                        labels={"census_year": "FIR Reporting Year", "value": _trend_label},
                    )

                    # Highlight focus municipality line
                    for trace in fig_trend.data:
                        if trace.name == _focus_name:
                            trace.line.width = 4
                        else:
                            trace.line.width = 1.5
                            trace.line.dash = "dot"

                    # Add risk band shading if applicable
                    if _trend_bands:
                        for i, (_thr, _lbl, _clr) in enumerate(_trend_bands):
                            if math.isfinite(_thr):
                                fig_trend.add_hline(
                                    y=_thr, line_dash="dash", line_color=_clr,
                                    line_width=1.5,
                                    annotation_text=_lbl,
                                    annotation_position="right",
                                    annotation_font_color=_clr,
                                    annotation_font_size=10,
                                )

                    fig_trend.update_layout(
                        height=400,
                        margin=dict(l=10, r=10, t=50, b=40),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(size=13),
                        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
                    )

                    if _trend_unit == "pct":
                        fig_trend.update_yaxes(tickformat=".1%")
                    elif _trend_unit == "$":
                        fig_trend.update_yaxes(tickformat="$,.0f")
                    elif _trend_unit == "ratio":
                        fig_trend.update_yaxes(tickformat=".3f")

                    st.plotly_chart(fig_trend, use_container_width=True)
                else:
                    st.info(f"No trend data available for '{_trend_label}'.")

                # --- CSV Export ---
                st.markdown("---")
                _export_rows = []
                for _bc in _all_bench_codes:
                    _bname = community_lookup.get(_bc, _bc)
                    _erow = {"Municipality": _bname, "Year": _bench_year, "Is Focus": _bc == _focus_code}
                    for _slug, _label, _unit, _bands in BENCHMARK_INDICATORS:
                        _val = _bench_pivot.loc[_bc, _slug] if (
                            _bc in _bench_pivot.index and _slug in _bench_pivot.columns
                        ) else None
                        _erow[_label] = _val if _val is not None and pd.notna(_val) else None
                    _export_rows.append(_erow)

                _export_df = pd.DataFrame(_export_rows)
                _csv_bytes = _export_df.to_csv(index=False).encode("utf-8")
                _focus_slug = _focus_name.split(" (")[0].replace(" ", "_")
                st.download_button(
                    label="📥 Download Fiscal Benchmark (CSV)",
                    data=_csv_bytes,
                    file_name=f"fiscal_benchmark_{_focus_slug}_{_bench_year}.csv",
                    mime="text/csv",
                    help="Download the full scorecard comparison as CSV for council reports.",
                    key=f"bench_csv_{_focus_slug}_{_bench_year}",
                )
                st.caption(
                    "💡 **Tip:** Use this data directly in council presentations. "
                    "The Asset Consumption Ratio and Debt-to-Revenue metrics are the exact "
                    "MMAH Financial Indicator Review standards used by provincial auditors."
                )



# -----------------------------------------------------------------------------
# 8. TABBED INDICATOR VIEWS (Chart | Data pattern)
# -----------------------------------------------------------------------------
st.markdown("---")

main_tabs = st.tabs(CATEGORIES)

# FIR categories use their own data source
FIR_CATEGORIES = {"Municipal Finance"}
fir_indicators_df = load_fir_indicators()

for main_tab, category in zip(main_tabs, CATEGORIES):
    with main_tab:
        # Data source attribution for each tab category
        if category in FIR_CATEGORIES:
            _data_source_caption(
                "Ontario Ministry of Municipal Affairs & Housing — Financial Information Returns (FIR)",
                "https://efis.fma.csc.gov.on.ca/fir/"
            )
            if fir_indicators_df.empty:
                st.info(f"No {category} data available. Run the FIR ETL pipeline to generate data.")
                continue

            fir_filtered = fir_indicators_df[
                fir_indicators_df["sgc_code"].isin(selected_codes)
            ].copy()
            fir_filtered["community"] = fir_filtered["sgc_code"].map(community_lookup)
            cat_indicators = [
                (slug, meta) for slug, meta in INDICATOR_META.items()
                if meta[2] == category and not _is_standalone_indicator(meta)
            ]
            available_slugs = set(fir_filtered["indicator"].unique())
            cat_indicators = [(s, m) for s, m in cat_indicators if s in available_slugs]
            # Use fir_filtered as the data source for this tab
            _tab_data = fir_filtered
        else:
            # Source caption for non-FIR tabs
            if category == "Connectivity":
                _data_source_caption(
                    "ISED National Broadband Data — Open Canada",
                    "https://open.canada.ca/data/en/dataset/00a331db-121b-445d-b119-35dbbe3eedd9",
                    "Terrestrial broadband coverage, dwelling-weighted"
                )
            else:
                _data_source_caption(
                    "Statistics Canada, Census Profile 2006–2021",
                    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm?Lang=E"
                )
            cat_indicators = [
                (slug, meta) for slug, meta in INDICATOR_META.items()
                if meta[2] == category and not _is_standalone_indicator(meta)
            ]
            available_slugs = set(filtered["indicator"].unique())
            cat_indicators = [(s, m) for s, m in cat_indicators if s in available_slugs]
            _tab_data = filtered

        # ---- Custom: Income Distribution (grouped histogram) ----
        if category == "Income Distribution":
            import plotly.graph_objects as go

            # Ordered band slugs (low → high)
            INCOME_BAND_ORDER = [
                "hh_income_under_10k", "hh_income_10k_20k", "hh_income_20k_30k",
                "hh_income_30k_40k", "hh_income_40k_50k", "hh_income_50k_60k",
                "hh_income_60k_70k", "hh_income_70k_80k", "hh_income_80k_90k",
                "hh_income_90k_100k", "hh_income_100k_125k", "hh_income_125k_150k",
                "hh_income_150k_plus",
                # Legacy fallbacks for 2011 aggregate
                "hh_income_100k_plus",
            ]
            INCOME_BAND_LABELS = {
                "hh_income_under_10k": "<$10K",
                "hh_income_10k_20k":  "$10–$20K",
                "hh_income_20k_30k":  "$20–$30K",
                "hh_income_30k_40k":  "$30–$40K",
                "hh_income_40k_50k":  "$40–$50K",
                "hh_income_50k_60k":  "$50–$60K",
                "hh_income_60k_70k":  "$60–$70K",
                "hh_income_70k_80k":  "$70–$80K",
                "hh_income_80k_90k":  "$80–$90K",
                "hh_income_90k_100k": "$90–$100K",
                "hh_income_100k_125k": "$100–$125K",
                "hh_income_125k_150k": "$125–$150K",
                "hh_income_150k_plus": "$150K+",
                "hh_income_100k_plus": "$100K+ (agg)",
            }

            # Year selector for income distribution
            inc_years = sorted(
                indicators_df[
                    (indicators_df["indicator"].str.startswith("hh_income"))
                    & (indicators_df["sgc_code"].isin(selected_codes))
                ]["census_year"].unique()
            )
            if not inc_years:
                st.info("No household after-tax income data available for the selected communities.")
                continue

            inc_year = st.selectbox(
                "Census Year", inc_years,
                index=len(inc_years) - 1,  # Default to most recent
                key="income_dist_year",
            )

            # --- Context KPI: Median After-Tax Household Income ---
            median_at = indicators_df[
                (indicators_df["indicator"] == "median_hh_income_at")
                & (indicators_df["census_year"] == inc_year)
                & (indicators_df["sgc_code"].isin(selected_codes))
            ]
            if not median_at.empty:
                kpi_cols = st.columns(min(len(median_at), 4))
                for ki, (_, mrow) in enumerate(median_at.iterrows()):
                    name = community_lookup.get(mrow["sgc_code"], mrow["sgc_code"])
                    with kpi_cols[ki % len(kpi_cols)]:
                        st.metric(
                            label=f"{name} — Median After-Tax HH Income ({inc_year})",
                            value=f"${mrow['value']:,.0f}" if pd.notna(mrow["value"]) else "N/A",
                        )

            # --- Build percentage distribution per community ---
            inc_data = indicators_df[
                (indicators_df["indicator"].isin(INCOME_BAND_ORDER))
                & (indicators_df["census_year"] == inc_year)
                & (indicators_df["sgc_code"].isin(selected_codes))
            ].copy()

            if inc_data.empty:
                st.warning(f"No household income distribution data for {inc_year}.")
                continue

            # --- Compute percentage within each community ---
            # 1. Base fallback: sum extracted bands for all selected CSDs
            totals = inc_data.groupby("sgc_code")["value"].sum()

            # 2. Look up true totals extracted from Census header (N3 FIX)
            total_hh_data = indicators_df[
                (indicators_df["indicator"] == "hh_income_total")
                & (indicators_df["census_year"] == inc_year)
                & (indicators_df["sgc_code"].isin(selected_codes))
            ]

            if not total_hh_data.empty:
                # Use groupby().first() as a safeguard against duplicate indices
                true_totals = total_hh_data.groupby("sgc_code")["value"].first()
                # Overwrite fallback with true total where available.
                # .update() ignores NaN, safely keeping the band sum fallback
                # for any CSD where the Census total was suppressed.
                totals.update(true_totals)

            inc_data["pct"] = inc_data.apply(
                lambda r: (r["value"] / totals.get(r["sgc_code"], 0) * 100)
                if totals.get(r["sgc_code"], 0) > 0 else 0,
                axis=1,
            )
            inc_data["community"] = inc_data["sgc_code"].map(community_lookup)

            # Sort bands in logical order
            band_order_present = [b for b in INCOME_BAND_ORDER if b in inc_data["indicator"].values]
            inc_data["band_label"] = inc_data["indicator"].map(INCOME_BAND_LABELS)
            label_order = [INCOME_BAND_LABELS[b] for b in band_order_present]

            # --- Grouped bar chart ---
            show_pct = st.toggle(
                "Show as percentage of households",
                value=True,
                key="income_dist_pct_toggle",
            )

            fig = go.Figure()
            colors = [
                "#2E86C1", "#E74C3C", "#27AE60", "#F39C12",
                "#8E44AD", "#1ABC9C", "#D35400", "#7F8C8D",
            ]
            for ci, (sgc, grp) in enumerate(inc_data.groupby("sgc_code")):
                cname = community_lookup.get(sgc, sgc)
                # Order by band
                # N4 FIX: fillna(0) prevents NaN from displaying as "nan" in hover text
                grp = grp.set_index("indicator").reindex(band_order_present).fillna(0).reset_index()
                y_vals = grp["pct"].values if show_pct else grp["value"].values
                hover_text = [
                    f"{cname}<br>{INCOME_BAND_LABELS.get(b, b)}<br>"
                    f"Households: {grp.loc[grp['indicator']==b, 'value'].values[0]:,.0f}<br>"
                    f"Share: {grp.loc[grp['indicator']==b, 'pct'].values[0]:.1f}%"
                    for b in band_order_present
                ]
                fig.add_trace(go.Bar(
                    name=cname,
                    x=[INCOME_BAND_LABELS[b] for b in band_order_present],
                    y=y_vals,
                    marker_color=colors[ci % len(colors)],
                    hovertext=hover_text,
                    hoverinfo="text",
                ))

            fig.update_layout(
                barmode="group",
                xaxis_title="After-Tax Household Income Band",
                yaxis_title="% of Households" if show_pct else "Number of Households",
                legend_title="Community",
                height=500,
                margin=dict(t=40, b=80),
                xaxis_tickangle=-45,
                template="plotly_white",
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- Data table ---
            with st.expander("📊 View Data Table"):
                pivot = inc_data.pivot_table(
                    index="community", columns="indicator",
                    values="pct" if show_pct else "value",
                    aggfunc="first",
                )
                # Reorder columns
                pivot = pivot.reindex(columns=band_order_present)
                pivot.columns = [INCOME_BAND_LABELS.get(c, c) for c in pivot.columns]
                if show_pct:
                    st.dataframe(pivot.style.format("{:.1f}%"), use_container_width=True)
                else:
                    st.dataframe(pivot.style.format("{:,.0f}"), use_container_width=True)

            # --- Data caveats ---
            st.caption(
                "⚠️ **Data Notes:** "
                "Income bands use nominal (not inflation-adjusted) dollars. "
                "Values from the 2011 National Household Survey (NHS) have known reliability issues "
                "due to low response rates, particularly in rural areas. "
                "Statistics Canada applies random rounding (±5) to all counts, "
                "which can distort percentages for very small communities. "
                "After-tax household income is the standard measure for wellbeing analysis."
            )
            continue

        # ---- End custom Income Distribution ----

        if not cat_indicators:
            st.info(f"No {category} data available for the selected communities and years.")
            continue

        # Indicator selector
        indicator_options = {meta[0]: slug for slug, meta in cat_indicators}
        selected_indicator_name = st.selectbox(
            f"Select {category} Indicator",
            options=list(indicator_options.keys()),
            key=f"indicator_{category}",
        )
        selected_slug = indicator_options[selected_indicator_name]
        meta = INDICATOR_META[selected_slug]

        ind_data = _tab_data[_tab_data["indicator"] == selected_slug].copy()

        if ind_data.empty:
            st.warning(f"No data available for {selected_indicator_name}.")
            continue

        # Ontario averages for this indicator
        ont_ind = ontario_avg[
            (ontario_avg["indicator"] == selected_slug) &
            (ontario_avg["census_year"].isin(selected_years))
        ].sort_values("census_year")

        # Chart type toggle
        chart_type = st.radio(
            "Chart type",
            ["📈 Time Series", "📊 Single Year"],
            horizontal=True,
            key=f"charttype_{category}_{selected_slug}",
            label_visibility="collapsed",
        )

        # Normalization toggle for bar chart mode
        _normalize_bar = False
        if chart_type == "📊 Single Year" and len(selected_codes) > 1:
            _normalize_bar = st.checkbox(
                "Index to 100 (normalize)",
                key=f"norm_{category}_{selected_slug}",
                help="Set the first community as index 100 so communities of different scales can be compared.",
            )

        # ── Chart | Data sub-tabs ──
        chart_tab, data_tab = st.tabs(["Chart", "Data"])

        with chart_tab:
            chart_col, table_col = st.columns([3, 2])

            with chart_col:
                if chart_type == "📈 Time Series":
                    # ── LINE CHART (existing) ──
                    fig = go.Figure()

                    # Ontario Average benchmark
                    if show_ont_avg and not ont_ind.empty:
                        fig.add_trace(go.Scatter(
                            x=ont_ind["census_year"],
                            y=ont_ind["ont_median"],
                            mode="lines+markers",
                            name="Ontario CSD Median",
                            line=dict(color="#9e9e9e", width=2, dash="dash"),
                            marker=dict(size=6, symbol="diamond", color="#9e9e9e"),
                            hovertemplate=(
                                "<b>Ontario CSD Median</b><br>"
                                "Year: %{x}<br>"
                                f"{meta[0]}: %{{y:,.1f}} {meta[1]}<br>"
                                "<extra></extra>"
                            ),
                        ))

                    # Community traces
                    colors = px.colors.qualitative.Set2
                    for i, code in enumerate(selected_codes):
                        comm_data = ind_data[ind_data["sgc_code"] == code].sort_values("census_year")
                        comm_name = community_lookup.get(code, code)
                        if not comm_data.empty:
                            fig.add_trace(go.Scatter(
                                x=comm_data["census_year"],
                                y=comm_data["value"],
                                mode="lines+markers",
                                name=comm_name.split(" (")[0],
                                line=dict(color=colors[i % len(colors)], width=3),
                                marker=dict(size=10),
                                hovertemplate=(
                                    f"<b>{comm_name.split(' (')[0]}</b><br>"
                                    f"Year: %{{x}}<br>"
                                    f"{meta[0]}: %{{y:,.1f}} {meta[1]}<br>"
                                    "<extra></extra>"
                                ),
                            ))

                    # --- Intercensal population estimates (2022-2024+) ---
                    _has_estimates = False
                    if selected_slug == "population":
                        try:
                            from scripts.scenario_engine import get_pop_estimates
                            for i, code in enumerate(selected_codes):
                                _est = get_pop_estimates(code)
                                if not _est.empty:
                                    _has_estimates = True
                                    _cname = community_lookup.get(code, code).split(" (")[0]
                                    fig.add_trace(go.Scatter(
                                        x=_est["year"],
                                        y=_est["population"],
                                        mode="lines+markers",
                                        name=f"{_cname} (Estimate)",
                                        line=dict(color=colors[i % len(colors)], width=2, dash="dot"),
                                        marker=dict(size=8, symbol="diamond", color=colors[i % len(colors)]),
                                        hovertemplate=(
                                            f"<b>{_cname} (StatCan Estimate)</b><br>"
                                            f"Year: %{{x}}<br>"
                                            f"Population: %{{y:,.0f}}<br>"
                                            "<extra></extra>"
                                        ),
                                    ))
                        except Exception:
                            pass  # Graceful fallback if estimates unavailable

                    # Build tick range: Census years + estimate years if available
                    _chart_years = list(available_years)
                    if _has_estimates:
                        _chart_years = sorted(set(_chart_years) | set(range(min(available_years), 2026)))

                    unit_label = f" ({meta[1]})" if meta[1] else ""
                    fig.update_layout(
                        title=dict(text=f"{meta[0]}{unit_label} Over Time", font=dict(size=16)),
                        xaxis_title="Census Year",
                        yaxis_title=f"{meta[0]}{unit_label}",
                        template="plotly_white",
                        height=450,
                        hovermode="x unified",
                        legend=dict(
                            orientation="h", yanchor="bottom", y=-0.25,
                            xanchor="center", x=0.5, font=dict(size=12),
                        ),
                        xaxis=dict(
                            tickmode="array",
                            tickvals=_chart_years,
                            ticktext=[str(y) for y in _chart_years],
                            tickfont=dict(size=12),
                        ),
                        yaxis=dict(tickfont=dict(size=12), rangemode="tozero"),  # Always start at zero
                        margin=dict(l=60, r=20, t=50, b=80),
                    )

                    if meta[1] == "$":
                        fig.update_yaxes(tickprefix="$", tickformat=",")
                    elif meta[1] == "$/mo":
                        fig.update_yaxes(tickprefix="$", tickformat=",")
                    elif meta[1] == "$/ha":
                        fig.update_yaxes(tickprefix="$", tickformat=",.2f")
                    elif meta[1] == "%":
                        fig.update_yaxes(ticksuffix="%")
                    elif meta[1] == "pct":
                        # Values stored as decimals (0-1), multiply for display
                        fig.update_yaxes(tickformat=".1%")
                    elif meta[1] == "rate":
                        fig.update_yaxes(tickformat=".4%")
                    elif meta[1] == "ratio":
                        fig.update_yaxes(tickformat=".4f")

                else:
                    # ── BAR CHART (single year comparison) ──
                    bar_year = max(selected_years)
                    bar_data = ind_data[ind_data["census_year"] == bar_year].copy()

                    # Add Ontario Median as a reference bar
                    bar_entries = []
                    colors_bar = px.colors.qualitative.Set2
                    bar_colors = []
                    for i, code in enumerate(selected_codes):
                        row = bar_data[bar_data["sgc_code"] == code]
                        if not row.empty:
                            bar_entries.append({
                                "Community": community_lookup.get(code, code).split(" (")[0],
                                "Value": row["value"].values[0],
                            })
                            bar_colors.append(colors_bar[i % len(colors_bar)])

                    if show_ont_avg and not ont_ind.empty:
                        ont_yr = ont_ind[ont_ind["census_year"] == bar_year]
                        if not ont_yr.empty:
                            bar_entries.append({
                                "Community": "Ontario CSD Median",
                                "Value": ont_yr["ont_median"].values[0],
                            })
                            bar_colors.append("#9e9e9e")

                    if bar_entries:
                        bar_df = pd.DataFrame(bar_entries)

                        # Normalize to index 100 if requested
                        y_col = "Value"
                        y_title_suffix = ""
                        if _normalize_bar and len(bar_df) > 0:
                            base_val = bar_df["Value"].iloc[0]
                            if base_val != 0:
                                bar_df["Indexed"] = (bar_df["Value"] / base_val * 100).round(1)
                                y_col = "Indexed"
                                y_title_suffix = " (Index 100)"

                        fig = go.Figure(
                            go.Bar(
                                x=bar_df["Community"],
                                y=bar_df[y_col],
                                marker_color=bar_colors,
                                text=bar_df[y_col].apply(
                                    lambda v: f"{v:.0f}" if y_col == "Indexed" else _format_value(v, meta[1])
                                ),
                                textposition="outside",
                                hovertemplate="<b>%{x}</b><br>" + (
                                    f"Index: %{{y:.1f}}<extra></extra>" if y_col == "Indexed"
                                    else f"{meta[0]}: %{{y:,.1f}} {meta[1]}<extra></extra>"
                                ),
                            )
                        )
                        unit_label = f" ({meta[1]})" if meta[1] and not _normalize_bar else ""
                        fig.update_layout(
                            title=dict(text=f"{meta[0]}{unit_label}{y_title_suffix} — {bar_year}", font=dict(size=16)),
                            yaxis_title=f"{meta[0]}{unit_label}{y_title_suffix}",
                            template="plotly_white",
                            height=450,
                            showlegend=False,
                            yaxis=dict(tickfont=dict(size=12), rangemode="tozero"),  # Always start at zero
                            margin=dict(l=60, r=20, t=50, b=40),
                        )
                        if not _normalize_bar:
                            if meta[1] == "$" or meta[1] == "$/mo":
                                fig.update_yaxes(tickprefix="$", tickformat=",")
                            elif meta[1] == "$/ha":
                                fig.update_yaxes(tickprefix="$", tickformat=",.2f")
                            elif meta[1] == "%":
                                fig.update_yaxes(ticksuffix="%")
                            elif meta[1] == "pct":
                                fig.update_yaxes(tickformat=".1%")
                            elif meta[1] == "rate":
                                fig.update_yaxes(tickformat=".4%")
                            elif meta[1] == "ratio":
                                fig.update_yaxes(tickformat=".4f")
                    else:
                        fig = go.Figure()
                        fig.add_annotation(text="No data for selected year", showarrow=False)

                st.plotly_chart(fig, use_container_width=True)

            with table_col:
                # Pivot table with Ontario Median row
                pivot_data = ind_data.copy()
                if show_ont_avg and not ont_ind.empty:
                    ont_rows = ont_ind.rename(columns={"ont_median": "value"}).copy()
                    ont_rows["community"] = "Ontario Median"
                    ont_rows["sgc_code"] = "ONT_AVG"
                    pivot_data = pd.concat([pivot_data, ont_rows], ignore_index=True)

                pivot = pivot_data.pivot_table(
                    index="community", columns="census_year",
                    values="value", aggfunc="first",
                )
                year_cols_int = sorted([c for c in pivot.columns])
                pivot = pivot[year_cols_int]
                pivot.columns = [str(int(c)) for c in pivot.columns]
                year_cols = list(pivot.columns)

                if len(year_cols) >= 2:
                    first_yr, last_yr = year_cols[0], year_cols[-1]
                    change_col = f"Change ({first_yr}-{last_yr})"
                    pivot[change_col] = pivot.apply(
                        lambda row: (
                            f"{((row[last_yr] - row[first_yr]) / row[first_yr] * 100):+.1f}%"
                            if pd.notna(row.get(first_yr)) and pd.notna(row.get(last_yr))
                            and row[first_yr] != 0
                            else "\u2014"
                        ),
                        axis=1,
                    )

                format_dict = {}
                for col in year_cols:
                    if meta[1] == "$":
                        format_dict[col] = "${:,.0f}"
                    elif meta[1] == "$/mo":
                        format_dict[col] = "${:,.0f}"
                    elif meta[1] == "$/ha":
                        format_dict[col] = "${:,.2f}"
                    elif meta[1] == "%":
                        format_dict[col] = "{:.1f}%"
                    elif meta[1] == "pct":
                        format_dict[col] = lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"
                    elif meta[1] == "rate":
                        format_dict[col] = lambda v: f"{v*100:.4f}%" if pd.notna(v) else "—"
                    elif meta[1] == "ratio":
                        format_dict[col] = "{:.4f}"
                    else:
                        format_dict[col] = "{:,.1f}"

                styled = pivot.style.format(format_dict, na_rep="\u2014")
                if len(year_cols) >= 2:
                    styled = styled.map(_color_change, subset=[change_col])

                st.dataframe(styled, use_container_width=True, height=380)

        with data_tab:
            # Raw data table + download (matches main app pattern)
            display_df = ind_data[["census_year", "sgc_code", "community", "value"]].copy()
            display_df = display_df.rename(columns={
                "census_year": "Census Year",
                "sgc_code": "SGC Code",
                "community": "Community",
                "value": meta[0],
            })
            display_df = display_df.sort_values(["Community", "Census Year"])

            # Add Ontario median column
            if show_ont_avg:
                ont_lookup = dict(zip(
                    ont_ind["census_year"].astype(int),
                    ont_ind["ont_median"]
                ))
                display_df["Ontario Median"] = display_df["Census Year"].map(ont_lookup)

            st.dataframe(display_df, use_container_width=True, height=350)

            # Download button
            csv_buf = io.StringIO()
            display_df.to_csv(csv_buf, index=False)
            slug_name = _safe_slug(selected_indicator_name)
            comm_slug = "_".join(_safe_slug(c.split(" (")[0]) for c in selected_communities[:3])
            file_name = f"wellbeing_{slug_name}_{comm_slug}.csv"

            st.download_button(
                label="Download data as CSV",
                data=csv_buf.getvalue(),
                file_name=file_name,
                mime="text/csv",
                help="Download the data used in this chart for further analysis.",
                key=f"dl_{category}_{selected_slug}",
            )

        # 2011 NHS note
        if 2011 in selected_years and category in ("Labour & Income", "Education", "Commuting", "Diversity", "Housing"):
            st.caption(
                "\u26a0\ufe0f Due to Statistics Canada's suppression rules for the voluntary "
                "2011 National Household Survey (NHS), data for approximately 25% of "
                "rural communities is suppressed (GNR > 50%). Missing 2011 trend lines "
                "are expected."
            )

        # LICO vs LIM-AT methodology warning
        if category == "Labour & Income" and 2006 in selected_years:
            st.caption(
                "\u26a0\ufe0f **Methodology Note:** The 2006 Census reported low-income prevalence using the Low Income "
                "Cut-Off (LICO), while 2011\u20132021 data uses the Low Income Measure After-Tax (LIM-AT). "
                "Direct comparisons between 2006 and subsequent years should be treated with caution."
            )

        # Condition 2 (E5): Education universe disclaimer
        if category == "Education":
            st.caption(
                "\u2139\ufe0f **Population universe:** Education data reflects the "
                "\"Population aged 15 years and over,\" which includes high-school-aged "
                "youth (15\u201324) and seniors (65+). For workforce planning, note that "
                "Statistics Canada recommends using the 25\u201364 working-age population. "
                "Raw counts should not be used to compare communities of different sizes; "
                "divide by the total population to obtain rates."
            )

        # Condition 3 (X2) + C4: Commuting raw counts + WFH universe warning
        if category == "Commuting":
            st.caption(
                "\u2139\ufe0f **Raw counts:** Values are person counts, not percentages. "
                "Use caution when comparing communities of different sizes. "
                "**\"Worked at Home\"** belongs to the \"Place of Work Status\" universe "
                "and has a different denominator than commuting mode indicators "
                "(Driver, Transit, Walked, etc.).  \n"
                "**Walked/Bicycled** in 2006 is a combined category; from 2011 onward, "
                "the combined figure is synthesized from separate Walk + Bike counts."
            )

        # N3: 2021 Housing affordability COVID-19 disclaimer
        if category == "Housing" and 2021 in selected_years:
            st.caption(
                "ℹ️ **2021 affordability note:** The 2021 Census calculated shelter costs "
                "based on 2021, but measured the 30% affordability threshold against "
                "**2020 income** — which was inflated by COVID-19 CERB payments. As a result, "
                "2021 housing affordability may appear artificially improved compared to 2016."
            )

        # Housing Stock synthesis note
        if category == "Housing Stock":
            st.caption(
                "ℹ️ **2006 data:** Dwelling type counts for 2006 are back-calculated from "
                "published percentages × total occupied dwellings. Counts for 2011–2021 "
                "are published directly by Statistics Canada."
            )

        # Broadband Connectivity disclaimers
        if category == "Connectivity":
            # Load data vintage if available
            _vintage_str = ""
            try:
                import json as _json
                _vintage_path = DERIVED_DIR / "broadband_vintage.json"
                if _vintage_path.exists():
                    with open(_vintage_path) as _vf:
                        _vdata = _json.load(_vf)
                    _vintage_str = f" Data as of {_vdata.get('metadata_modified', 'unknown')}."
            except Exception:
                pass
            st.caption(
                "✅ **Satellite excluded:** Coverage reflects terrestrial infrastructure only "
                "(wired + fixed wireless). LEO satellite availability is excluded to provide "
                "policy-accurate figures suitable for Universal Broadband Fund applications.  "
                "⚠️ **Indigenous & remote communities:** Broadband data for First Nations "
                "and unorganized territories may be incomplete — absence of mapped coverage "
                "does not confirm absence of service.  "
                "⚠️ **Fixed wireless:** Coverage is based on theoretical propagation; actual "
                "availability may differ due to terrain and foliage.  \n\n"
                "📊 **Methodology:** Dwelling-weighted terrestrial broadband coverage from ISED "
                "PHH Speeds + Pseudo-Household Demographic Distribution, merged via StatCan "
                f"Dissemination Geography Relationship File.{_vintage_str}"
            )

        # ── Tax Burden Comparison (multi-indicator overlay) ──



# -----------------------------------------------------------------------------
# 9. HEALTH ACCESS SECTION
# Audit 2026-02-26: Red team remediations Q1-Q12, Issues 13-15 applied.
# ETL now includes ALL Ontario CSDs (outer join), fixing survivorship bias.
# -----------------------------------------------------------------------------
health_df = load_health_data()

if health_df is not None and not health_df.empty:
    st.markdown("---")
    st.subheader("🏥 Health Access")
    _data_source_caption(
        "Statistics Canada, Open Database of Healthcare Facilities (ODHF) v1.1",
        "https://www.statcan.gc.ca/en/lode/databases/odhf",
        "Per-CSD facility counts and per-capita rates"
    )

    health_selected = health_df[health_df["sgc_code"].isin(selected_codes)].copy()
    # Q10 FIX: Use ETL-generated community names; fallback to community_lookup if column missing
    if "community" not in health_selected.columns:
        health_selected["community"] = health_selected["sgc_code"].map(community_lookup)

    # Q3 FIX: Include "other" in facility type breakdown
    facility_types = [c for c in ["hospitals", "ambulatory", "nursing_residential", "other"] if c in health_df.columns]
    nice_names = {
        "hospitals": "🏥 Hospitals",
        "ambulatory": "🩺 Ambulatory Care",
        "nursing_residential": "🏠 Nursing & Residential",
        "other": "🏢 Other Facilities",
    }

    # Track metric mode for conditional footnote (Q12 fix)
    _health_metric = "Raw Counts"

    if not health_selected.empty:
        # Q9 FIX: Pre-compute Ontario Average once; dropna to align numerator/denominator
        ont_agg_rate = None
        if "population" in health_df.columns:
            valid_pop_df = health_df.dropna(subset=["population"])
            _ont_full_pop = valid_pop_df["population"].sum()
            if _ont_full_pop > 0:
                ont_agg_rate = round(valid_pop_df["total_facilities"].sum() / _ont_full_pop * 10_000, 1)

        ht_cols = st.columns([3, 2])

        with ht_cols[0]:
            # Toggle between raw counts and per-capita
            if "facilities_per_10k" in health_selected.columns:
                _health_metric = st.radio(
                    "Display", ["Per 10K Population", "Raw Counts"],
                    horizontal=True, key="health_metric_toggle",
                    label_visibility="collapsed",
                )

            bar_data = []
            for _, row in health_selected.iterrows():
                # Q1 FIX: Retain full community name without truncation
                cname = str(row["community"]) if pd.notna(row.get("community")) else str(row["sgc_code"])
                pop = row.get("population", None)

                for ft in facility_types:
                    raw_count = row.get(ft, 0)
                    if _health_metric == "Per 10K Population":
                        # Q7 FIX: NaN populations produce None → Plotly omits bar
                        if pd.notna(pop) and pop > 0:
                            display_val = round(raw_count / pop * 10_000, 1)
                        else:
                            display_val = None
                    else:
                        display_val = raw_count

                    if display_val is not None:
                        # Rec 6: asterisk for small-pop communities
                        suffix = " *" if (_health_metric == "Per 10K Population" and pd.notna(pop) and pop < 1_000) else ""
                        bar_data.append({
                            "Community": f"{cname}{suffix}",
                            "Type": nice_names.get(ft, ft),
                            "Value": display_val,
                        })

            if bar_data:
                bar_df = pd.DataFrame(bar_data)
                y_label = "Per 10,000 Population" if _health_metric == "Per 10K Population" else "Facility Count"
                # Q3 FIX: 4th color (#f39c12) for "other"
                fig_h = px.bar(
                    bar_df, x="Community", y="Value", color="Type",
                    barmode="group",
                    color_discrete_sequence=["#e74c3c", "#3498db", "#27ae60", "#f39c12"],
                    title=f"Health Facilities — {_health_metric}",
                    labels={"Value": y_label},
                )
                fig_h.update_layout(
                    template="plotly_white", height=400,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    margin=dict(l=40, r=20, t=50, b=60),
                )
                # Benchmark lines (per-capita mode only)
                if _health_metric == "Per 10K Population":
                    if ont_agg_rate is not None:
                        fig_h.add_hline(
                            y=ont_agg_rate, line_dash="dash", line_color="#9e9e9e", line_width=2,
                            annotation_text=f"Ontario Average ({ont_agg_rate:.1f})",
                            annotation_position="top right",
                            annotation_font_color="#9e9e9e",
                        )
                    # Q2 FIX: Label corrected to <30K (matches code threshold)
                    _rural_pop, _rural_fac = _get_rural_totals(health_df)
                    if _rural_pop > 0:
                        rural_agg = round(_rural_fac / _rural_pop * 10_000, 1)
                        fig_h.add_hline(
                            y=rural_agg, line_dash="dot", line_color="#66bb6a", line_width=2,
                            annotation_text=f"Rural Ontario (<30K Pop) ({rural_agg:.1f})",
                            annotation_position="bottom right",
                            annotation_font_color="#66bb6a",
                        )
                st.plotly_chart(fig_h, use_container_width=True)

        with ht_cols[1]:
            # Summary table
            display_cols = ["community", "total_facilities"]
            if "facilities_per_10k" in health_selected.columns:
                display_cols.append("facilities_per_10k")
            display_cols.extend([ft for ft in facility_types])

            table_df = health_selected[display_cols].copy()
            rename_map = {
                "community": "Community",
                "total_facilities": "Total",
                "facilities_per_10k": "Per 10K Pop",
            }
            rename_map.update({ft: nice_names.get(ft, ft) for ft in facility_types})
            table_df = table_df.rename(columns=rename_map)
            # Q1 FIX: Removed table community truncation

            st.dataframe(table_df, use_container_width=True, hide_index=True, height=350)

            # Q9 FIX: Reuse pre-computed Ontario average
            if ont_agg_rate is not None:
                st.caption(f"Ontario average rate: **{ont_agg_rate:.1f}** facilities per 10,000 population")

    else:
        # Show communities that have no facilities
        no_data_names = [community_lookup.get(c, c) for c in selected_codes]
        st.info(
            f"No health facilities recorded for: {', '.join(no_data_names)}. "
            f"This may indicate very small communities where residents access health services in neighbouring areas."
        )

    # Rec 2 audit fix: dynamic vintage from amenities_vintage.json
    _h_vintage = _get_amenity_vintage("health")
    # Q8 FIX: Expanded caveat regarding operational status changes
    st.caption(
        f"Data: Statistics Canada, {_h_vintage.get('source', 'ODHF')} "
        f"{_h_vintage.get('version', '')} **(Released {_h_vintage.get('source_release_year', 'N/A')})**. "
        "Facility types: Hospitals, Ambulatory Health Care, Nursing & Residential Care, Other. "
        "*(Note: Facility operational status may have changed since the release year).*"
    )
    # Rec 10: Regional context tooltip
    st.caption(
        "ℹ️ Facility counts are based strictly on municipal boundaries. "
        "A count of zero may indicate facilities are located in neighbouring regional hubs, "
        "not necessarily a lack of geographic access."
    )
    # Q12 FIX: Asterisk footnote only shown in per-capita mode
    if _health_metric == "Per 10K Population":
        st.caption(
            "\* Communities marked with * have populations under 1,000. "
            "Per-capita rates for these communities are statistically volatile and should be interpreted with caution."
        )


# -----------------------------------------------------------------------------
# 9b. CRIME SEVERITY INDEX
# -----------------------------------------------------------------------------
CRIME_FILE = WELLBEING_DIR / "crime_severity.csv"

if CRIME_FILE.exists() and selected_codes:
    @st.cache_data(max_entries=1, ttl=1800)
    def _load_crime():
        df = smart_read(CRIME_FILE)
        # SGC codes may be float (3523008.0) — convert via numeric to strip .0
        df["sgc_code"] = pd.to_numeric(df["sgc_code"], errors="coerce")
        df = df.dropna(subset=["sgc_code"])
        df["sgc_code"] = df["sgc_code"].astype(int).astype(str).str.zfill(7)
        return df

    crime_df = _load_crime()
    crime_selected = crime_df[crime_df["sgc_code"].isin(selected_codes)]

    if not crime_selected.empty:
        st.markdown("---")
        st.subheader("🔒 Public Safety — Crime Severity Index")
        _data_source_caption(
            "Statistics Canada, Table 35-10-0188-01",
            "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3510018801",
            "Crime severity index by police service, latest year"
        )

        csi_cols = [c for c in ["csi_overall", "csi_violent", "csi_nonviolent", "clearance_rate"]
                    if c in crime_selected.columns]
        CSI_LABELS = {
            "csi_overall": "Overall CSI",
            "csi_violent": "Violent CSI",
            "csi_nonviolent": "Non-Violent CSI",
            "clearance_rate": "Clearance Rate (%)",
        }

        csi_chart_cols = st.columns([3, 2])

        with csi_chart_cols[0]:
            chart_data = []
            for _, row in crime_selected.iterrows():
                comm = row.get("community_name", community_lookup.get(row["sgc_code"], row["sgc_code"]))
                short_name = str(comm).split(" (")[0]
                for col in csi_cols:
                    if pd.notna(row.get(col)):
                        chart_data.append({
                            "Community": short_name,
                            "Metric": CSI_LABELS.get(col, col),
                            "Value": row[col],
                        })

            if chart_data:
                chart_df = pd.DataFrame(chart_data)
                fig_csi = px.bar(
                    chart_df, x="Metric", y="Value", color="Community",
                    barmode="group",
                    color_discrete_sequence=["#e74c3c", "#3498db", "#27ae60", "#f39c12", "#9b59b6"],
                    title="Crime Severity Index (2024)",
                )
                fig_csi.update_layout(
                    template="plotly_white", height=400,
                    xaxis_title="", yaxis_title="Index Value",
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    margin=dict(l=40, r=20, t=50, b=60),
                )
                # Ontario median reference
                if "csi_overall" in crime_df.columns:
                    ont_med = crime_df["csi_overall"].median()
                    if pd.notna(ont_med):
                        fig_csi.add_hline(
                            y=ont_med, line_dash="dash", line_color="#9e9e9e", line_width=2,
                            annotation_text=f"Ontario Median ({ont_med:.0f})",
                            annotation_position="top right",
                            annotation_font_color="#9e9e9e",
                        )
                st.plotly_chart(fig_csi, use_container_width=True)

        with csi_chart_cols[1]:
            # Summary table
            display_cols = ["community_name"] + csi_cols
            available = [c for c in display_cols if c in crime_selected.columns]
            table_df = crime_selected[available].copy()
            rename_map = {"community_name": "Community"}
            rename_map.update({c: CSI_LABELS.get(c, c) for c in csi_cols})
            table_df = table_df.rename(columns=rename_map)
            if "Community" in table_df.columns:
                table_df["Community"] = table_df["Community"].apply(
                    lambda x: str(x).split(" (")[0] if pd.notna(x) else x
                )
            st.dataframe(table_df, use_container_width=True, hide_index=True, height=350)

            # Context
            if "csi_overall" in crime_df.columns:
                ont_median = crime_df["csi_overall"].median()
                st.caption(
                    f"Ontario median CSI: **{ont_median:.0f}** "
                    f"(Canada baseline = 78.1 in 2024). "
                    f"Lower CSI = less severe crime."
                )

        st.caption(
            "Data: Statistics Canada, Table 35-10-0188-01 (Crime Severity Index, police services in Ontario). "
            "CSI baselined to Canada 2006 = 100. Police services matched to CSDs by name."
        )


# -----------------------------------------------------------------------------
# 8b. ENVIRONMENT — Climate Profile
# Audit 2026-02-24: Pipeline B (ECCC normals) is the sole data source.
# Pipeline A (daily GitHub data) deprecated. See climate_section_red_team_prompt.md
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🌍 Environment — Climate Profile")
_data_source_caption(
    "Environment & Climate Change Canada, Climate Normals 1981–2010",
    "https://climate.weather.gc.ca/climate_normals/index_e.html",
    "Via ECCC Geomet OGC API — nearest-station mapping"
)

if CLIMATE_FILE.exists() and selected_codes:
    @st.cache_data(max_entries=1, ttl=1800)
    def _load_climate():
        df = smart_read(CLIMATE_FILE)
        # Robust SGC normalization (handles float strings like "3523043.0")
        df["sgc_code"] = pd.to_numeric(df["sgc_code"], errors="coerce")
        df = df.dropna(subset=["sgc_code"])
        df["sgc_code"] = df["sgc_code"].astype(int).astype(str).str.zfill(7)
        df = df[df["sgc_code"].str.startswith("35")].copy()
        return df

    climate_df = _load_climate()
    climate_selected = climate_df[climate_df["sgc_code"].isin(selected_codes)]

    # Climate indicator labels — ECCC Climate Normals (1981-2010)
    # Q12 fix: "Mean Daily Max/Min Temp" not "Daily Max/Min"
    CLIMATE_META = {
        "climate_mean_temp":    ("Mean Temperature",        "°C"),
        "climate_max_temp":     ("Mean Daily Max Temp",     "°C"),
        "climate_min_temp":     ("Mean Daily Min Temp",     "°C"),
        "climate_total_precip": ("Annual Precipitation",    "mm"),
        "climate_total_rain":   ("Annual Rainfall",         "mm"),
        "climate_total_snow":   ("Annual Snowfall",         "cm"),
        "climate_gdd":          ("Growing Degree Days (5°C)", "GDD"),
        "climate_frost_days":   ("Frost Days (≤0°C)",       "days"),
        "climate_hot_days":     ("Hot Days (>30°C)",        "days"),
    }

    # Group indicators for tabbed display
    # Q16 fix: separate rain/precip (mm) from snow (cm)
    TEMP_INDICATORS = ["climate_mean_temp", "climate_max_temp", "climate_min_temp"]
    RAIN_INDICATORS = ["climate_total_precip", "climate_total_rain"]
    SNOW_INDICATORS = ["climate_total_snow"]
    GROWING_INDICATORS = ["climate_gdd", "climate_frost_days", "climate_hot_days"]

    climate_cols = [c for c in climate_df.columns if c.startswith("climate_")]

    if climate_selected.empty or not climate_cols:
        st.info("No climate data available for the selected communities.")
    else:
        # Q19 fix: expanded methodology caption
        st.caption(
            "1981-2010 historical climate normals mapped to communities using the "
            "nearest ECCC weather station to each CSD’s geographic centroid. "
            "These are 30-year averages, not current conditions. "
            "Data: Environment and Climate Change Canada, via Geomet OGC API."
        )

        # Show nearest station info with distance warnings (Q8 fix)
        if "nearest_station" in climate_selected.columns:
            station_info = []
            for _, row in climate_selected.iterrows():
                # Q18 fix: retain full community name (no truncation)
                comm = str(row.get("community", community_lookup.get(row["sgc_code"], row["sgc_code"])))
                stn = row.get("nearest_station", "N/A")
                dist = row.get("station_distance_km", "N/A")
                warn = "⚠️" if row.get("distance_warning", False) else ""
                station_info.append(f"**{comm}** → {stn} ({dist} km){warn}")
            st.markdown("Nearest weather stations: " + " | ".join(station_info))
            # Show warning legend if any distances are flagged
            if any(row.get("distance_warning", False) for _, row in climate_selected.iterrows()):
                st.caption("⚠️ Station is >50 km from community centroid — climate values may be less representative.")

        # Tabs for different climate categories
        # Q16 fix: separate Rain/Precip (mm) from Snow (cm)
        ct1, ct2, ct3, ct4 = st.tabs(["Temperature", "Rain & Precipitation", "Snowfall", "Growing Season"])

        # Reference line colors for per-indicator medians (Q15 fix)
        _MEDIAN_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

        def _climate_chart(tab, indicators, title, y_label="Value", use_scatter=False):
            """Render a climate chart for the given indicators.

            Q15 fix: per-indicator median lines (no break)
            Q17: temperature tab uses dot plot
            Q18: full community names
            """
            with tab:
                chart_data = []
                for _, row in climate_selected.iterrows():
                    # Q18 fix: retain full community name
                    comm = str(row.get("community", community_lookup.get(row["sgc_code"], row["sgc_code"])))
                    for col in indicators:
                        if col in climate_cols and pd.notna(row.get(col)):
                            meta = CLIMATE_META.get(col, (col, ""))
                            chart_data.append({
                                "Community": comm,
                                "Indicator": meta[0],
                                "Value": row[col],
                                "Unit": meta[1],
                            })

                if not chart_data:
                    st.info("No data available for this category.")
                    return

                chart_df = pd.DataFrame(chart_data)
                color_seq = ["#e74c3c", "#3498db", "#27ae60", "#f39c12", "#9b59b6"]

                if use_scatter:
                    # Q17: dot plot for temperature (handles negatives better)
                    fig_c = px.scatter(
                        chart_df, x="Indicator", y="Value", color="Community",
                        color_discrete_sequence=color_seq,
                        title=title,
                        labels={"Value": y_label},
                    )
                    fig_c.update_traces(marker=dict(size=14, line=dict(width=1, color="white")))
                else:
                    fig_c = px.bar(
                        chart_df, x="Indicator", y="Value", color="Community",
                        barmode="group",
                        color_discrete_sequence=color_seq,
                        title=title,
                        labels={"Value": y_label},
                    )

                fig_c.update_layout(
                    template="plotly_white", height=400,
                    xaxis_title="", yaxis_title=y_label,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    margin=dict(l=40, r=20, t=50, b=60),
                )

                # Q15 fix: add per-indicator Ontario median reference lines (NO break)
                for i, ind in enumerate(ind for ind in indicators if ind in climate_cols):
                    ont_med = climate_df[ind].median()
                    if pd.notna(ont_med):
                        label = CLIMATE_META.get(ind, (ind,))[0]
                        fig_c.add_hline(
                            y=ont_med, line_dash="dot",
                            line_color=_MEDIAN_COLORS[i % len(_MEDIAN_COLORS)],
                            # N10 fix: Clarify unweighted CSD median AND retain metric label
                            annotation_text=f"Unweighted CSD Med ({label}): {ont_med:.1f}",
                            annotation_position="top right",
                            annotation_font_size=9,
                            annotation_font_color=_MEDIAN_COLORS[i % len(_MEDIAN_COLORS)],
                        )

                st.plotly_chart(fig_c, use_container_width=True)

        # Q17: temperature uses dot plot (scatter) for negative-value clarity
        _climate_chart(ct1, TEMP_INDICATORS, "Temperature Normals (1981-2010)",
                       y_label="°C", use_scatter=True)
        # Q16: rain/precip (mm) separate from snow (cm)
        _climate_chart(ct2, RAIN_INDICATORS, "Rainfall & Precipitation Normals (1981-2010)",
                       y_label="mm")
        _climate_chart(ct3, SNOW_INDICATORS, "Snowfall Normals (1981-2010)",
                       y_label="cm")
        _climate_chart(ct4, ["climate_gdd"], "Growing Degree Days (1981-2010)", y_label="GDD")
        # N3 fix: separate Frost/Hot Days (small scale) from GDD (large scale)
        _climate_chart(ct4, ["climate_frost_days", "climate_hot_days"],
                       "Threshold Days (1981-2010)", y_label="Days")

        # Full data table
        with st.expander("Climate Data Table"):
            available_cols = [c for c in climate_cols if c in climate_selected.columns]
            disp_cols = ["sgc_code"] + available_cols
            if "nearest_station" in climate_selected.columns:
                disp_cols.insert(1, "nearest_station")
            if "station_distance_km" in climate_selected.columns:
                disp_cols.insert(2, "station_distance_km")
            pivot_display = climate_selected[disp_cols].copy()
            # Q18 fix: retain full community name
            pivot_display.insert(0, "Community", climate_selected.apply(
                lambda r: str(r.get("community", community_lookup.get(r["sgc_code"], r["sgc_code"]))),
                axis=1,
            ))
            pivot_display = pivot_display.drop(columns=["sgc_code"])
            rename_map = {col: CLIMATE_META.get(col, (col,))[0] for col in available_cols}
            if "nearest_station" in pivot_display.columns:
                rename_map["nearest_station"] = "Nearest Station"
            if "station_distance_km" in pivot_display.columns:
                rename_map["station_distance_km"] = "Distance (km)"
            pivot_display = pivot_display.rename(columns=rename_map)
            st.dataframe(pivot_display, use_container_width=True, hide_index=True)

        # N4 + N2 fixes: vintage caveat and shared-station note
        st.caption(
            "Data: Environment and Climate Change Canada (ECCC) Climate Normals 1981-2010, "
            "via Geomet OGC API. Each community is mapped to its nearest weather station "
            "by geographic centroid. Station distances >50 km are flagged. "
            "**Note:** As historical 1981-2010 baselines, these values do not reflect recent climatic warming. "
            "Additionally, multiple adjacent communities may map to the same weather station, "
            "resulting in identical climate profiles."
        )

else:
    if not CLIMATE_FILE.exists():
        with st.expander("🌍 Environment — Climate Profile (data not yet loaded)"):
            st.info(
                "Climate normals have not been loaded yet. To enable this section:\n\n"
                "Run: `python scripts/fetch_climate_normals.py`\n\n"
                "This will automatically fetch 1981-2010 climate normals from the ECCC "
                "Geomet API and map each community to its nearest weather station."
            )


# -----------------------------------------------------------------------------
# 8c. ARTS & CULTURE
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🎭 Arts & Culture Facilities")
_data_source_caption(
    "Statistics Canada, Open Database of Cultural and Art Facilities (ODCAF)",
    "https://www.statcan.gc.ca/en/lode/databases/odcaf",
    "Per-CSD facility counts and per-capita rates"
)

if ARTS_FILE.exists() and selected_codes:
    @st.cache_data(max_entries=1, ttl=1800)
    def _load_arts():
        df = smart_read(ARTS_FILE)
        # Robust SGC normalization (handle float strings like "3523043.0")
        df["sgc_code"] = pd.to_numeric(df["sgc_code"], errors="coerce")
        df = df.dropna(subset=["sgc_code"])
        df["sgc_code"] = df["sgc_code"].astype(int).astype(str).str.zfill(7)
        df = df[df["sgc_code"].str.startswith("35")].copy()
        return df

    arts_df = _load_arts()
    arts_selected = arts_df[arts_df["sgc_code"].isin(selected_codes)]

    if arts_selected.empty:
        no_data_names = [community_lookup.get(c, c) for c in selected_codes]
        st.info(
            f"No arts/culture facilities recorded for: {', '.join(no_data_names)}."
        )
    else:
        # Facility type display names (also used as whitelist for chart columns)
        _arts_nice_names = {
            "art_or_cultural_centre": "🎭 Cultural Centres",
            "artist": "🎨 Artist Studios",
            "festival_site": "🎉 Festival Sites",
            "gallery": "🖼️ Galleries",
            "heritage": "🏛️ Heritage Sites",
            "library": "📚 Libraries",
            "museum": "🏛️ Museums",
            "performing_arts": "🎶 Performing Arts",
            "theatre": "🎬 Theatres",
        }

        # FIX A2: Whitelist approach instead of fragile skip_cols blacklist
        arts_type_cols = [c for c in arts_selected.columns if c in _arts_nice_names]

        # Metric toggle
        _arts_metric = st.radio(
            "View as",
            ["Raw Counts", "Per 10K Population"],
            horizontal=True,
            key="arts_metric",
            label_visibility="collapsed",
        )

        at_cols = st.columns([2, 1])

        with at_cols[0]:
            # Rec 8: Build GROUPED bar chart by facility type (not just totals)
            chart_rows = []
            for _, row in arts_selected.iterrows():
                comm = row.get("community", community_lookup.get(row["sgc_code"], row["sgc_code"]))
                short_name = str(comm).split(" (")[0]
                pop = row.get("population", None)

                # Rec 6 audit fix: asterisk for small-pop (not emoji)
                if _arts_metric == "Per 10K Population" and pop and pop < 1_000:
                    short_name = f"{short_name} *"
                    _has_small_pop = True

                for ft in arts_type_cols:
                    raw_count = row.get(ft, 0)
                    if pd.isna(raw_count):
                        raw_count = 0
                    raw_count = int(raw_count)
                    if raw_count == 0:
                        continue  # skip zero-count types to reduce clutter

                    if _arts_metric == "Per 10K Population" and pop and pop > 0:
                        display_val = round(raw_count / pop * 10_000, 1)
                    else:
                        display_val = raw_count

                    nice = _arts_nice_names.get(ft, ft.replace("_", " ").title())
                    chart_rows.append({
                        "Community": short_name,
                        "Type": nice,
                        "Value": display_val,
                    })

            if chart_rows:
                chart_df = pd.DataFrame(chart_rows)
                y_label = "Per 10K Pop" if _arts_metric == "Per 10K Population" else "Count"
                fig_a = px.bar(
                    chart_df, x="Community", y="Value", color="Type",
                    barmode="stack",
                    color_discrete_sequence=["#e74c3c", "#3498db", "#27ae60", "#f39c12", "#9b59b6",
                                             "#1abc9c", "#e67e22", "#2ecc71", "#8e44ad"],
                    title=f"Arts & Culture Facilities — {_arts_metric}",
                    labels={"Value": y_label},
                )
                fig_a.update_layout(
                    template="plotly_white", height=450,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
                    margin=dict(l=40, r=20, t=50, b=60),
                )
                # Tooltip clarity: append unit when per-capita toggle is active
                _hover_suffix = " per 10k pop" if _arts_metric == "Per 10K Population" else ""
                fig_a.update_traces(
                    hovertemplate="%{x}<br>%{data.name}: %{y:.1f}" + _hover_suffix + "<extra></extra>"
                )
                # Rec 7 audit fix: full Ontario population + Rural Average
                if _arts_metric == "Per 10K Population":
                    _a_tot = arts_df["total_facilities"].sum()
                    _ont_full_pop = _get_ontario_population()
                    if _ont_full_pop > 0:
                        ont_agg = round(_a_tot / _ont_full_pop * 10_000, 1)
                        fig_a.add_hline(
                            y=ont_agg, line_dash="dash", line_color="#9e9e9e", line_width=2,
                            annotation_text=f"Ontario Average ({ont_agg:.1f})",
                            annotation_position="top right",
                            annotation_font_color="#9e9e9e",
                        )
                    _rural_pop, _rural_fac = _get_rural_totals(arts_df)
                    if _rural_pop > 0:
                        rural_agg = round(_rural_fac / _rural_pop * 10_000, 1)
                        fig_a.add_hline(
                            y=rural_agg, line_dash="dot", line_color="#66bb6a", line_width=2,
                            annotation_text=f"Rural Ontario ({rural_agg:.1f})",
                            annotation_position="bottom right",
                            annotation_font_color="#66bb6a",
                        )
                st.plotly_chart(fig_a, use_container_width=True)
            else:
                st.info("No facility type data available for the selected communities.")

        with at_cols[1]:
            # Summary table
            display_cols = ["community", "total_facilities"]
            if "facilities_per_10k" in arts_selected.columns:
                display_cols.append("facilities_per_10k")
            available_display = [c for c in display_cols if c in arts_selected.columns]
            table_df = arts_selected[available_display].copy()
            rename_map = {
                "community": "Community",
                "total_facilities": "Total",
                "facilities_per_10k": "Per 10K Pop",
            }
            table_df = table_df.rename(columns=rename_map)
            if "Community" in table_df.columns:
                table_df["Community"] = table_df["Community"].apply(
                    lambda x: x.split(" (")[0] if pd.notna(x) else x
                )
            st.dataframe(table_df, use_container_width=True, hide_index=True, height=300)

            # Rec 7 audit fix: use full Ontario population
            _a_tot = arts_df["total_facilities"].sum()
            _ont_full_pop = _get_ontario_population()
            if _ont_full_pop > 0:
                ont_agg_rate = round(_a_tot / _ont_full_pop * 10_000, 1)
                st.caption(f"Ontario average rate: **{ont_agg_rate:.1f}** arts facilities per 10,000 population")

    # FIX A3: Prominent pre-pandemic data warning
    st.warning(
        "\u26a0\ufe0f **Pre-Pandemic Baseline:** This data represents a frozen **2019** snapshot "
        "(ODCAF v1.0). It does not reflect cultural sector closures or openings that "
        "occurred during or after the COVID-19 pandemic."
    )
    # Rec 10: Regional context tooltip
    st.caption(
        "\u2139\ufe0f Facility counts are based strictly on municipal boundaries. "
        "A count of zero may indicate facilities are located in neighbouring regional hubs, "
        "not necessarily a lack of geographic access."
    )
    # FIX A4: Conditionally render small-pop asterisk footnote
    if any((row.get("population") or 0) < 1_000 for _, row in arts_selected.iterrows()):
        st.caption(
            "\* Communities marked with * have populations under 1,000. "
            "Per-capita rates for these communities are statistically volatile and should be interpreted with caution."
        )

else:
    if not ARTS_FILE.exists():
        with st.expander("🎭 Arts & Culture Facilities (data not yet loaded)"):
            st.info(
                "Arts & Culture facility data has not been loaded yet. To enable this section:\n\n"
                "1. Download ODCAF from [Statistics Canada](https://www.statcan.gc.ca/en/lode/databases/odcaf)\n"
                "2. Place the ZIP in `data/raw/ODCAF*.zip`\n"
                "3. Run: `python scripts/fetch_arts_facilities.py`"
            )


# =============================================================================
# §10. RURAL LABOUR MARKET MONITOR
# Data: SEPH (14-10-0203-01) + CMHC Housing Starts (34-10-0143-01)
# Added: April 2026 — based on OMAFRA Rural Ontario Economic Monitor pattern
# =============================================================================

_SEPH_FILE  = DERIVED_DIR / "rural_labour_seph.parquet"
_CMHC_FILE  = DERIVED_DIR / "rural_housing_starts.parquet"

_seph_exists = _SEPH_FILE.exists()
_cmhc_exists = _CMHC_FILE.exists()

if _seph_exists or _cmhc_exists:
    st.markdown("---")
    st.subheader("📊 Rural Labour Market Monitor")
    st.caption(
        "Provincial-level labour market and housing supply indicators for Ontario. "
        "Unlike the census indicators above (which are community-level), these datasets "
        "track Ontario-wide trends by industry sector and dwelling type."
    )
    _data_source_caption(
        "Statistics Canada — SEPH (14-10-0203-01) & CMHC (34-10-0143-01)",
        "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410020301",
        "Survey of Employment, Payrolls and Hours + CMHC Starts and Completions Survey"
    )

    _rlm_tab_seph, _rlm_tab_cmhc = st.tabs(["🏭 Employment by Industry (SEPH)", "🏠 Housing Starts (CMHC)"])

    # ─── TAB 1: SEPH Industry Employment ────────────────────────────────────
    with _rlm_tab_seph:
        if not _seph_exists:
            st.info(
                "SEPH industry employment data not yet loaded. "
                "Run: `python scripts/fetch_rural_labour_housing.py`"
            )
        else:
            @st.cache_data(max_entries=1, ttl=1800)
            def _load_seph():
                df = pd.read_parquet(_SEPH_FILE)
                return df

            seph_df = _load_seph()

            if seph_df.empty:
                st.warning("SEPH data file is empty. Re-run the pipeline.")
            else:
                # Filter to Ontario (province level) for comparability
                _ont_opts = sorted(seph_df["geo"].unique())
                _seph_default = [g for g in _ont_opts if g.strip().lower() == "ontario"]
                _seph_geos = st.multiselect(
                    "Geography",
                    options=_ont_opts,
                    default=_seph_default if _seph_default else _ont_opts[:1],
                    key="seph_geo_select",
                    help="Select one or more Ontario geographies to display",
                )

                _seph_years = sorted(seph_df["year"].unique())
                _seph_year_range = st.select_slider(
                    "Year range",
                    options=_seph_years,
                    value=(_seph_years[max(0, len(_seph_years)-10)], _seph_years[-1]),
                    key="seph_year_range",
                )

                seph_filt = seph_df[
                    (seph_df["geo"].isin(_seph_geos)) &
                    (seph_df["year"] >= _seph_year_range[0]) &
                    (seph_df["year"] <= _seph_year_range[1])
                ]

                if seph_filt.empty:
                    st.info("No data for the selected geography/year range.")
                else:
                    _seph_view = st.radio(
                        "View",
                        ["📊 By Industry (Latest Year)", "📈 Industry Trend Over Time"],
                        horizontal=True,
                        key="seph_view_mode",
                        label_visibility="collapsed",
                    )

                    _latest_seph_year = seph_filt["year"].max()

                    if _seph_view == "📊 By Industry (Latest Year)":
                        # Bar chart: all industries for latest year
                        _seph_bar = seph_filt[seph_filt["year"] == _latest_seph_year].copy()
                        _seph_bar = _seph_bar.sort_values("employees_thousands", ascending=True)

                        _seph_cols_chart, _seph_cols_table = st.columns([3, 2])
                        with _seph_cols_chart:
                            fig_seph = go.Figure()
                            _seph_colors = px.colors.qualitative.Set2
                            for _gi, _geo in enumerate(_seph_geos):
                                _geo_bar = _seph_bar[_seph_bar["geo"] == _geo]
                                if _geo_bar.empty:
                                    continue
                                _geo_bar = _geo_bar.sort_values("employees_thousands", ascending=True)
                                fig_seph.add_trace(go.Bar(
                                    y=_geo_bar["industry"],
                                    x=_geo_bar["employees_thousands"],
                                    name=_geo,
                                    orientation="h",
                                    marker_color=_seph_colors[_gi % len(_seph_colors)],
                                    hovertemplate=(
                                        "<b>%{y}</b><br>"
                                        f"{_geo}<br>"
                                        "Employees: %{x:,.1f}K<extra></extra>"
                                    ),
                                ))
                            fig_seph.update_layout(
                                title=f"Paid Employment by Industry — Ontario ({_latest_seph_year})",
                                xaxis_title="Employees (thousands, annual avg)",
                                yaxis_title="",
                                template="plotly_white",
                                height=max(500, 30 * len(_seph_bar["industry"].unique())),
                                barmode="group",
                                margin=dict(l=10, r=20, t=50, b=40),
                                legend=dict(
                                    orientation="h", yanchor="bottom",
                                    y=-0.12, xanchor="center", x=0.5,
                                ),
                            )
                            st.plotly_chart(fig_seph, use_container_width=True)

                        with _seph_cols_table:
                            _seph_pivot = _seph_bar.pivot_table(
                                index="industry", columns="geo",
                                values="employees_thousands", aggfunc="mean",
                            ).round(1)
                            st.dataframe(
                                _seph_pivot.style.format("{:,.1f}"),
                                use_container_width=True,
                                height=400,
                            )
                            _seph_csv = _seph_bar.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                "📥 Download Industry Data (CSV)",
                                data=_seph_csv,
                                file_name=f"seph_industry_{_latest_seph_year}.csv",
                                mime="text/csv",
                                key="seph_dl_bar",
                            )

                    else:
                        # Time-series: pick an industry
                        _all_industries = sorted(seph_filt["industry"].unique())
                        _sel_industry = st.selectbox(
                            "Select Industry",
                            options=_all_industries,
                            key="seph_industry_sel",
                        )
                        _seph_trend = seph_filt[seph_filt["industry"] == _sel_industry]

                        fig_seph_ts = px.line(
                            _seph_trend,
                            x="year",
                            y="employees_thousands",
                            color="geo",
                            markers=True,
                            title=f"{_sel_industry} Employment — Ontario",
                            labels={"employees_thousands": "Employees (thousands)", "year": "Year", "geo": "Geography"},
                            color_discrete_sequence=px.colors.qualitative.Set2,
                        )
                        fig_seph_ts.update_layout(
                            template="plotly_white",
                            height=420,
                            margin=dict(l=10, r=10, t=50, b=40),
                            legend=dict(
                                orientation="h", yanchor="bottom",
                                y=-0.2, xanchor="center", x=0.5,
                            ),
                        )
                        fig_seph_ts.update_traces(line=dict(width=2), marker=dict(size=8))
                        st.plotly_chart(fig_seph_ts, use_container_width=True)

                    st.caption(
                        "⚠️ **Note:** SEPH employment figures are seasonally adjusted monthly estimates "
                        "averaged to annual. Values in thousands of employees. "
                        "Source: Statistics Canada, Survey of Employment, Payrolls and Hours "
                        "(Table 14-10-0203-01). Ontario economic region breakdown reflects "
                        "available geographies in the public bulk download."
                    )

    # ─── TAB 2: CMHC Housing Starts ─────────────────────────────────────────
    with _rlm_tab_cmhc:
        if not _cmhc_exists:
            st.info(
                "CMHC housing starts data not yet loaded. "
                "Run: `python scripts/fetch_rural_labour_housing.py`"
            )
        else:
            @st.cache_data(max_entries=1, ttl=1800)
            def _load_cmhc():
                df = pd.read_parquet(_CMHC_FILE)
                return df

            cmhc_df = _load_cmhc()

            if cmhc_df.empty:
                st.warning("CMHC data file is empty. Re-run the pipeline.")
            else:
                # Geography filter
                _cmhc_geos = sorted(cmhc_df["geo"].unique())
                _cmhc_default = [g for g in _cmhc_geos if "Ontario" in g and "Toronto" not in g and "," not in g]
                _cmhc_sel_geos = st.multiselect(
                    "Geography",
                    options=_cmhc_geos,
                    default=_cmhc_default[:3] if _cmhc_default else _cmhc_geos[:2],
                    key="cmhc_geo_select",
                    help="Filter by Ontario census metropolitan areas or province",
                )

                # Dwelling type filter
                _cmhc_types = sorted(cmhc_df["dwelling_type"].unique())
                _cmhc_sel_types = st.multiselect(
                    "Dwelling Types",
                    options=_cmhc_types,
                    default=[t for t in _cmhc_types if "All" in t or "Single" in t],
                    key="cmhc_type_select",
                )

                # Year range
                _cmhc_years = sorted(cmhc_df["year"].unique())
                _cmhc_yr_range = st.select_slider(
                    "Year range",
                    options=_cmhc_years,
                    value=(_cmhc_years[max(0, len(_cmhc_years)-10)], _cmhc_years[-1]),
                    key="cmhc_year_range",
                )

                cmhc_filt = cmhc_df[
                    (cmhc_df["geo"].isin(_cmhc_sel_geos)) &
                    (cmhc_df["dwelling_type"].isin(_cmhc_sel_types)) &
                    (cmhc_df["year"] >= _cmhc_yr_range[0]) &
                    (cmhc_df["year"] <= _cmhc_yr_range[1])
                ]

                if cmhc_filt.empty:
                    st.info("No data for the selected filters.")
                else:
                    _cmhc_view = st.radio(
                        "Chart view",
                        ["📈 Quarterly Trend", "📊 Annual by Dwelling Type"],
                        horizontal=True,
                        key="cmhc_view_mode",
                        label_visibility="collapsed",
                    )

                    _cmhc_chart_col, _cmhc_table_col = st.columns([3, 2])

                    with _cmhc_chart_col:
                        if _cmhc_view == "📈 Quarterly Trend":
                            # Line chart: starts by quarter
                            _cmhc_line = cmhc_filt.copy()
                            _cmhc_line = _cmhc_line.sort_values("period")
                            _cmhc_line["series"] = _cmhc_line["geo"] + " — " + _cmhc_line["dwelling_type"]

                            fig_cmhc = px.line(
                                _cmhc_line,
                                x="period",
                                y="starts",
                                color="series",
                                markers=True,
                                title="Ontario Housing Starts — Quarterly",
                                labels={
                                    "starts": "Housing Starts",
                                    "period": "Quarter",
                                    "series": "Series",
                                },
                                color_discrete_sequence=px.colors.qualitative.Set2,
                            )
                            fig_cmhc.update_layout(
                                template="plotly_white",
                                height=450,
                                margin=dict(l=10, r=10, t=50, b=60),
                                xaxis_tickangle=-45,
                                legend=dict(
                                    orientation="h", yanchor="bottom",
                                    y=-0.35, xanchor="center", x=0.5,
                                    font=dict(size=11),
                                ),
                            )
                            st.plotly_chart(fig_cmhc, use_container_width=True)

                        else:
                            # Stacked bar: annual totals by dwelling type
                            _cmhc_annual = (
                                cmhc_filt.groupby(["year", "geo", "dwelling_type"])["starts"]
                                .sum()
                                .reset_index()
                            )
                            fig_cmhc_bar = px.bar(
                                _cmhc_annual,
                                x="year",
                                y="starts",
                                color="dwelling_type",
                                facet_col="geo" if len(_cmhc_sel_geos) > 1 else None,
                                barmode="stack",
                                title="Annual Housing Starts by Dwelling Type",
                                labels={
                                    "starts": "Annual Starts",
                                    "year": "Year",
                                    "dwelling_type": "Type",
                                },
                                color_discrete_sequence=px.colors.qualitative.Set2,
                            )
                            fig_cmhc_bar.update_layout(
                                template="plotly_white",
                                height=450,
                                margin=dict(l=10, r=10, t=50, b=40),
                                legend=dict(
                                    orientation="h", yanchor="bottom",
                                    y=-0.2, xanchor="center", x=0.5,
                                ),
                            )
                            st.plotly_chart(fig_cmhc_bar, use_container_width=True)

                    with _cmhc_table_col:
                        # Summary pivot: annual starts by type
                        _cmhc_summary = (
                            cmhc_filt.groupby(["year", "dwelling_type"])["starts"]
                            .sum()
                            .reset_index()
                            .pivot_table(index="year", columns="dwelling_type", values="starts", aggfunc="sum")
                        )
                        _cmhc_summary.columns.name = None
                        _cmhc_summary = _cmhc_summary.sort_index(ascending=False)
                        st.dataframe(
                            _cmhc_summary.style.format("{:,.0f}"),
                            use_container_width=True,
                            height=380,
                        )
                        _cmhc_csv = cmhc_filt.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "📥 Download Housing Starts (CSV)",
                            data=_cmhc_csv,
                            file_name=f"cmhc_starts_ontario_{_cmhc_yr_range[0]}_{_cmhc_yr_range[1]}.csv",
                            mime="text/csv",
                            key="cmhc_dl",
                        )

                    st.caption(
                        "⚠️ **Coverage note:** CMHC Starts data (Table 34-10-0143-01) covers urban "
                        "centres with populations ≥ 10,000. Housing starts in smaller rural communities "
                        "(<10,000 population) are estimated separately by CMHC and are **not** included "
                        "in this table. For rural starts, see the CMHC Housing Market Information Portal. "
                        "Source: Statistics Canada / CMHC, Starts and Completions Survey."
                    )

else:
    with st.expander("📊 Rural Labour Market Monitor (data not yet loaded)"):
        st.info(
            "SEPH industry employment and CMHC housing starts data have not been loaded yet.\\n\\n"
            "Run: `python scripts/fetch_rural_labour_housing.py`\\n\\n"
            "This downloads Statistics Canada Table 14-10-0203-01 (SEPH) and "
            "Table 34-10-0143-01 (CMHC Housing Starts) and processes them for display."
        )


# -----------------------------------------------------------------------------
# 8. FULL PROFILE EXPORT
# -----------------------------------------------------------------------------
st.markdown("---")

export_data = filtered[["census_year", "sgc_code", "community", "indicator", "value"]].copy()
export_data["indicator_label"] = export_data["indicator"].map(
    lambda s: INDICATOR_META.get(s, (s,))[0]
)
export_data["unit"] = export_data["indicator"].map(
    lambda s: INDICATOR_META.get(s, ("", ""))[1]
)

csv_bytes = export_data.to_csv(index=False).encode("utf-8")
comm_names = " & ".join([c.split(" (")[0] for c in selected_communities[:3]])
filename = f"wellbeing_{comm_names.replace(' ', '_')}_{latest_year}.csv"

st.download_button(
    label="\U0001f4e5 Download Full Community Profile (CSV)",
    data=csv_bytes,
    file_name=filename,
    mime="text/csv",
    help="Download ALL indicator data for the selected communities and years",
)

# --- PDF Report Download ---
try:
    import sys as _sys
    _scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    from generate_pdf_report import generate_pdf

    if len(selected_codes) == 1:
        pdf_code = selected_codes[0]
        pdf_name = selected_communities[0].split(" (")[0].replace(" ", "_")
        if st.button("\U0001f4c4 Generate PDF Community Profile", help="Generate a branded PDF report for the selected community"):
            with st.spinner("Generating PDF report..."):
                pdf_bytes = generate_pdf(pdf_code, latest_year)
            st.download_button(
                label="\U0001f4e5 Download PDF Report",
                data=pdf_bytes,
                file_name=f"community_profile_{pdf_name}_{latest_year}.pdf",
                mime="application/pdf",
                key="download_pdf_report",
            )
            st.success("PDF report generated! Click above to download.")
    elif len(selected_codes) > 1:
        st.caption("PDF reports are available for single community selection. Select one community to generate a PDF.")
except ImportError:
    st.caption("PDF reports require `fpdf2`. Install with: `pip install fpdf2`")
except Exception as e:
    st.error(f"PDF generation failed: {e}")


# -----------------------------------------------------------------------------
# 9. FOOTER
# -----------------------------------------------------------------------------
with st.expander("\U0001f4d6 Data Sources & Methodology"):
    st.markdown("""
**Data Source:** Statistics Canada Census Profile

| Census Year | Product | Scope |
|------------|---------|-------|
| 2021 | Census Profile (98-401-X2021) | Ontario CSDs |
| 2016 | Census Profile (98-401-X2016) | Ontario CSDs |
| 2011 | Census Profile (98-316-XWE) | All Canada (filtered to Ontario) |
| 2006 | Community Profiles (92-591-XE) | Ontario CSDs |

**Ontario CSD Median:** The dashed benchmark line shows the **unweighted median** across all
Ontario Census Subdivisions. This is NOT a population-weighted provincial average \u2014 it
represents the "typical CSD" rather than the "typical Ontarian". Small CSDs carry equal
weight to large ones in computing this median.

**Map:** CSD boundaries from StatCan 2021 Census Cartographic Boundary Files,
simplified for web rendering. Colours represent the 5th-95th percentile range.
For inverse indicators (e.g., unemployment rate), green = low (good) and blue = high.

**Processing:** Characteristic names are normalized across Census years to enable
time-series comparison. Some indicators may not be available for all years due to
changes in Census methodology (e.g., the 2011 NHS split).

**⚠️ Municipal Boundary Changes:** Some Ontario CSDs underwent amalgamation or
annexation between Census years (e.g., Norfolk County formed in 2001 from multiple
townships). Census data for these communities may show discontinuities that reflect
boundary changes rather than genuine population or economic shifts. Compare
pre- and post-amalgamation data with caution.
    """)

from app.utils import global_footer
global_footer()
