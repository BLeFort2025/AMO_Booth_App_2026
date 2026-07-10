"""
🔮 Scenario Planner
====================
Interactive population projections for rural Ontario communities.

Methodology: Hamilton-Perry Cohort Change Ratios (CCRs) with
Ontario Ministry of Finance Census Division share-capture controls.

See: scripts/scenario_engine.py for projection logic.
"""

import streamlit as st
import pandas as pd
import altair as alt
import sys
from pathlib import Path

# --- Inject project root for imports ---
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from scripts.scenario_engine import (
    run_scenario,
    SCENARIO_PRESETS,
    AGE_BANDS,
    get_mof_county_projection,
    calculate_housing_metrics,
    calculate_infrastructure_metrics,
    calculate_economic_metrics,
)
from app.smart_read import smart_read

# --- Page config ---
st.set_page_config(
    page_title="Scenario Planner — Rural Ontario",
    page_icon="🔮",
    layout="wide",
)

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()


# --- CSS ---
st.markdown("""
<style>
    .scenario-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .scenario-header h1 {
        color: #e8e8ff;
        font-size: 2rem;
        margin: 0 0 0.5rem 0;
    }
    .scenario-header p {
        color: #a8a8c8;
        margin: 0;
        font-size: 0.95rem;
    }
    .metric-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
    }
    .metric-card .label {
        color: var(--text-color);
        opacity: 0.8;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-card .value {
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--text-color);
    }
    .metric-card .delta {
        font-size: 0.82rem;
        margin-top: 2px;
    }
    .delta-up { color: #10b981; }
    .delta-down { color: #ef4444; }
    .ccr-badge {
        display: inline-block;
        background: var(--secondary-background-color);
        color: var(--primary-color);
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 2px;
    }
    .preset-desc {
        background: var(--secondary-background-color);
        border-left: 3px solid #eab308;
        padding: 0.6rem 1rem;
        margin: 0.5rem 0 1rem 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.9rem;
        color: var(--text-color);
    }
    .method-note {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 8px;
        padding: 0.8rem 1rem;
        font-size: 0.85rem;
        color: var(--text-color);
        margin-top: 1rem;
    }
    .housing-card {
        background: var(--secondary-background-color);
        border: 1px solid #f59e0b;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .housing-card .value {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-color);
    }
    .housing-card .label {
        color: var(--text-color);
        opacity: 0.8;
        font-size: 0.78rem;
        text-transform: uppercase;
    }
    .gap-positive {
        background: rgba(220, 38, 38, 0.1);
        border: 1px solid #fca5a5;
        border-radius: 8px;
        padding: 1rem;
        color: #ef4444;
    }
    .gap-negative {
        background: rgba(22, 163, 74, 0.1);
        border: 1px solid #86efac;
        border-radius: 8px;
        padding: 1rem;
        color: #10b981;
    }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("""
<div class="scenario-header">
    <h1>🔮 Scenario Planner</h1>
    <p>Hamilton-Perry population projections calibrated to Ontario Ministry of Finance Census Division controls</p>
</div>
""", unsafe_allow_html=True)

# --- Load geography ---
WELLBEING_DIR = Path("data/latest/wellbeing")
GEO_FILE = WELLBEING_DIR / "dim_geography.csv"
CENSUS_FILE = WELLBEING_DIR / "census_indicators.csv"
FIR_FILE = Path("data/derived/fir_indicators.csv")

if not GEO_FILE.exists() or not CENSUS_FILE.exists():
    st.error("Required data files not found. Please run the Census data pipeline first.")
    st.stop()

@st.cache_data(max_entries=3, ttl=1800)
def load_geo():
    geo = smart_read(GEO_FILE)
    geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)
    return geo

geo = load_geo()

# --- Sidebar: Community Selection ---
st.sidebar.header("🗺️ Select Community")

# County filter
counties = sorted(geo["county"].dropna().unique())
selected_county = st.sidebar.selectbox("County / District", counties, index=counties.index("Wellington") if "Wellington" in counties else 0)

# Filter communities by county
county_csds = geo[geo["county"] == selected_county].sort_values("geo_name")
if county_csds.empty:
    st.warning("No communities found in this county.")
    st.stop()

community_options = {
    f"{row['geo_name']} ({row['sgc_code']})": row["sgc_code"]
    for _, row in county_csds.iterrows()
}
selected_label = st.sidebar.selectbox("Community", list(community_options.keys()))
selected_code = community_options[selected_label]
selected_name = selected_label.split(" (")[0]


# --- FIR Data Lookup ---
@st.cache_data(max_entries=3, ttl=1800)
def _load_fir_benchmarks():
    """Load FIR data indexed by SGC code for benchmark lookup."""
    if not FIR_FILE.exists():
        return {}
    fir = smart_read(FIR_FILE)
    if "sgc_code" not in fir.columns:
        return {}
    fir["sgc_code"] = pd.to_numeric(fir["sgc_code"], errors="coerce")
    fir = fir.dropna(subset=["sgc_code"])
    fir["sgc_code"] = fir["sgc_code"].astype(int).astype(str).str.zfill(7)
    # Get latest year per municipality
    fir = fir.sort_values("year", ascending=False).drop_duplicates("sgc_code")
    return fir.set_index("sgc_code").to_dict("index")

fir_data = _load_fir_benchmarks()
fir_row = fir_data.get(selected_code, {})
has_fir = bool(fir_row)

# --- Sidebar: Scenario Controls ---
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Scenario Controls")

# Preset selector
preset_name = st.sidebar.selectbox(
    "Scenario Preset",
    list(SCENARIO_PRESETS.keys()),
    index=1,  # Default: Stable
    help="Pre-configured scenario settings. Adjust sliders below to customize.",
)
preset = SCENARIO_PRESETS[preset_name]

# Show preset description
st.sidebar.markdown(f'<div class="preset-desc">{preset["description"]}</div>', unsafe_allow_html=True)

# Migration slider
migration = st.sidebar.slider(
    "Migration Attractiveness",
    min_value=0.5,
    max_value=2.0,
    value=preset["migration_factor"],
    step=0.1,
    help="1.0 = current trend. >1.0 = more in-migration (GTA spillover). <1.0 = out-migration (employer loss).",
)

# Aging slider
aging = st.sidebar.slider(
    "Aging Rate Multiplier",
    min_value=0.85,
    max_value=1.15,
    value=preset["aging_factor"],
    step=0.05,
    help="1.0 = current trend. >1.0 = faster aging. <1.0 = younger in-migrants dilute aging.",
)

# Housing cap
housing_cap = st.sidebar.number_input(
    "New Housing Units Approved",
    min_value=0,
    max_value=50000,
    value=0,
    step=100,
    help="Max NEW units above existing stock. Population capped at (existing_dwellings + this) × avg HH size. 0 = unlimited.",
)

# Projection horizon
end_year = st.sidebar.selectbox(
    "Projection Horizon",
    [2031, 2036, 2041, 2046, 2051],
    index=2,
    help="How far into the future to project.",
)

# MOF controls
use_mof = st.sidebar.checkbox(
    "Apply MOF Controls",
    value=True,
    help="Calibrate projections against Ontario Ministry of Finance Census Division projections.",
)

# Warning when MOF controls override scenario sliders
if use_mof and (migration != 1.0 or aging != 1.0):
    st.sidebar.warning(
        "MOF Controls are ON. Your scenario sliders will shape the **age distribution** "
        "but the **total population** will be constrained to the community's historical "
        "share of the Census Division MOF projection. Uncheck MOF Controls to see "
        "the unconstrained scenario."
    )

# --- Sidebar: Housing Controls ---
st.sidebar.markdown("---")
st.sidebar.header("🏠 Housing Controls")

vacancy_pct = st.sidebar.slider(
    "Vacancy Rate Buffer (%)",
    min_value=1,
    max_value=10,
    value=3,
    step=1,
    help="CMHC defines 3% as a healthy vacancy rate. Units needed = households ÷ (1 - vacancy rate).",
)
vacancy_rate = vacancy_pct / 100.0

provincial_target = st.sidebar.number_input(
    "Bill 23 Housing Target (units)",
    min_value=0,
    max_value=100000,
    value=0,
    step=500,
    help="Provincial housing target from Bill 23 (More Homes Built Faster Act). Enter your municipality's target. 0 = no target.",
)

target_year = st.sidebar.selectbox(
    "Target Year",
    [2031, 2036, 2041],
    index=0,
    help="Year by which the provincial target should be met.",
)

# --- Sidebar: Infrastructure Capacity ---
st.sidebar.markdown("---")
st.sidebar.header("🏗️ Infrastructure Capacity")
st.sidebar.caption("Enter your system's rated capacity to see utilization %.")

user_water_cap = st.sidebar.number_input(
    "Water System Capacity (m³/day)",
    min_value=0,
    max_value=100000,
    value=0,
    step=100,
    help="Rated daily capacity of your water treatment system. 0 = don't show utilization.",
)

user_ww_cap = st.sidebar.number_input(
    "Wastewater System Capacity (m³/day)",
    min_value=0,
    max_value=100000,
    value=0,
    step=100,
    help="Rated daily capacity of your wastewater system (lagoon, WWTP). 0 = don't show utilization.",
)

# --- Sidebar: Local Economics ---
st.sidebar.markdown("---")
st.sidebar.header("💰 Local Economics")

# Auto-populate from FIR if available
fir_mill = 0.0
fir_assess = 0
fir_year = None
if has_fir:
    # S22A provides LT and UT rates separately; sum = total municipal rate
    _lt = fir_row.get("residential_lt_rate")
    _ut = fir_row.get("residential_ut_rate")
    lt_val = float(_lt) if _lt and not pd.isna(_lt) else 0.0
    ut_val = float(_ut) if _ut and not pd.isna(_ut) else 0.0
    if lt_val > 0 or ut_val > 0:
        fir_mill = round((lt_val + ut_val) * 100, 2)  # Convert decimal to %
    fir_year = int(fir_row.get("year", 0))

if has_fir and fir_year:
    st.sidebar.markdown(
        f'<div style="background:#e0f7fa;border-left:3px solid #0097a7;padding:6px 10px;'
        f'border-radius:0 6px 6px 0;font-size:0.82rem;color:#006064;margin-bottom:8px;">'
        f'📊 <b>FIR {fir_year}</b> actuals loaded for {selected_name}</div>',
        unsafe_allow_html=True,
    )
else:
    st.sidebar.caption("Override Ontario benchmarks with your municipality's actual values.")

local_mill_rate_pct = st.sidebar.number_input(
    "Local Mill Rate (%)",
    min_value=0.0,
    max_value=3.0,
    value=fir_mill,
    step=0.05,
    format="%.2f",
    help="Your residential mill rate (e.g., 0.85%). 0 = use Ontario benchmark (0.85%).",
)
local_mill_rate = local_mill_rate_pct / 100.0

local_assessment = st.sidebar.number_input(
    "Avg Residential Assessment ($)",
    min_value=0,
    max_value=2000000,
    value=fir_assess,
    step=10000,
    help="Average assessed value per residential unit. 0 = use Ontario benchmark ($350,000).",
)
st.sidebar.caption(
    "Enter your municipality's 2016 MPAC Current Value Assessment (CVA), "
    "NOT current market value. Ontario CVA has been frozen at 2016 levels."
)

# --- Get avg household size from Census ---
@st.cache_data(max_entries=3, ttl=1800)
def _load_census_indicators():
    """Load census indicators once (shared across functions)."""
    df = smart_read(CENSUS_FILE)
    df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)
    return df

def get_avg_hh_size(sgc_code):
    df = _load_census_indicators()
    hh = df[(df["sgc_code"] == sgc_code) & (df["indicator"] == "avg_hh_size")]
    if not hh.empty:
        latest = hh.sort_values("census_year").iloc[-1]["value"]
        return round(float(latest), 2) if pd.notna(latest) else 2.5
    return 2.5

avg_hh = get_avg_hh_size(selected_code)

# --- Run Scenario ---
with st.spinner("Running scenario projection..."):
    result = run_scenario(
        sgc_code=selected_code,
        county_name=selected_county,
        migration_factor=migration,
        aging_factor=aging,
        housing_cap=housing_cap,
        avg_hh_size=avg_hh,
        use_mof_controls=use_mof,
        end_year=end_year,
    )

if "error" in result:
    st.error(result["error"])
    st.stop()

proj = result["projection"]
ccrs = result["ccrs"]
meta = result["metadata"]
census_hist = result["census_history"]
estimate_hist = result.get("estimate_history", pd.DataFrame())

# --- KPI Cards ---
base_row = proj.iloc[0]
end_row = proj.iloc[-1]
pop_change = end_row["total"] - base_row["total"]
pop_change_pct = (pop_change / base_row["total"] * 100) if base_row["total"] > 0 else 0
delta_sign = "+" if pop_change >= 0 else ""

# Per-metric delta class: population/households use pop direction,
# dependency ratio and senior share are "inverse" (higher = worse)
dep_change = end_row["dependency_ratio"] - base_row["dependency_ratio"]
senior_change = end_row["senior_share_pct"] - base_row["senior_share_pct"]
hh_change = end_row["est_households"] - base_row["est_households"]

cols = st.columns(5)
metrics = [
    ("Projected Population", f"{int(end_row['total']):,}", f"{delta_sign}{pop_change_pct:.1f}% from {int(base_row['year'])}", "delta-up" if pop_change >= 0 else "delta-down"),
    ("Dependency Ratio", f"{end_row['dependency_ratio']:.1f}", f"{'↑' if dep_change > 0 else '↓'} from {base_row['dependency_ratio']:.1f}", "delta-down" if dep_change > 0 else "delta-up"),
    ("Senior Share", f"{end_row['senior_share_pct']:.1f}%", f"{'↑' if senior_change > 0 else '↓'} from {base_row['senior_share_pct']:.1f}%", "delta-down" if senior_change > 0 else "delta-up"),
    ("Est. Households", f"{int(end_row['est_households']):,}", f"Need {int(hh_change):+,}", "delta-up" if hh_change >= 0 else "delta-down"),
    ("Avg HH Size", f"{avg_hh}", f"Census {int(base_row['year'])}", ""),
]

for col, (label, value, delta, delta_cls) in zip(cols, metrics):
    col.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        <div class="delta {delta_cls}">{delta}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("")

# --- Main content ---
# --- Calculate Housing Metrics ---
housing = calculate_housing_metrics(
    result,
    vacancy_rate=vacancy_rate,
    provincial_target=provincial_target,
    target_year=target_year,
)

# --- Calculate Phase 3-4 Metrics ---
infra = calculate_infrastructure_metrics(
    result, housing,
    user_water_capacity=user_water_cap,
    user_ww_capacity=user_ww_cap,
)

econ = calculate_economic_metrics(
    result, housing,
    local_mill_rate=local_mill_rate,
    local_assessment=local_assessment,
)

tab_proj, tab_structure, tab_housing, tab_infra, tab_econ, tab_compare, tab_scenarios, tab_data = st.tabs([
    "📈 Population",
    "👥 Age Structure",
    "🏠 Housing",
    "🏗️ Infrastructure",
    "💰 Economy",
    "📊 MOF Comparison",
    "⚖️ Scenario Comparison",
    "📋 Data",
])

# ---- Tab 1: Population Projection (Fan Chart) ----
with tab_proj:
    st.subheader(f"Population Projection: {selected_name}")

    # Build chart data: Census history + projection
    chart_data = []

    # Historical Census data
    if not census_hist.empty and "population" in census_hist.columns:
        for _, row in census_hist.iterrows():
            chart_data.append({
                "year": int(row["census_year"]),
                "population": int(row["population"]),
                "series": "Census (Actual)",
            })

    # Intercensal estimates (2022-2024)
    if not estimate_hist.empty:
        for _, row in estimate_hist.iterrows():
            chart_data.append({
                "year": int(row["year"]),
                "population": int(row["population"]),
                "series": "StatCan Estimate",
            })

    # Projection
    for _, row in proj.iterrows():
        chart_data.append({
            "year": int(row["year"]),
            "population": int(row["total"]),
            "series": f"Scenario: {preset_name}",
        })

    chart_df = pd.DataFrame(chart_data)

    # Also add the comparison scenarios for the fan effect
    # Cached to avoid re-running all preset scenarios on every page load
    @st.cache_data(max_entries=3, ttl=1800, show_spinner=False)
    def _compute_fan_data(_sgc_code, _county_name, _avg_hh, _use_mof, _end_year, _current_preset):
        fan_rows = []
        for pname, pvals in SCENARIO_PRESETS.items():
            if pname == _current_preset:
                continue
            fan_result = run_scenario(
                sgc_code=_sgc_code,
                county_name=_county_name,
                migration_factor=pvals["migration_factor"],
                aging_factor=pvals["aging_factor"],
                housing_cap=0,
                avg_hh_size=_avg_hh,
                use_mof_controls=_use_mof,
                end_year=_end_year,
            )
            if "error" not in fan_result:
                for _, row in fan_result["projection"].iterrows():
                    fan_rows.append({
                        "year": int(row["year"]),
                        "population": int(row["total"]),
                        "series": pname,
                    })
        return fan_rows

    fan_data = _compute_fan_data(selected_code, selected_county, avg_hh, use_mof, end_year, preset_name)

    fan_df = pd.DataFrame(fan_data)
    all_chart = pd.concat([chart_df, fan_df], ignore_index=True)

    # Build the layered chart
    base_chart = alt.Chart(all_chart).encode(
        x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
        y=alt.Y("population:Q", title="Population", scale=alt.Scale(zero=False)),
    )

    # Fan lines (thin, muted)
    fan_lines = base_chart.transform_filter(
        alt.FieldOneOfPredicate(field="series", oneOf=[p for p in SCENARIO_PRESETS if p != preset_name])
    ).mark_line(
        strokeDash=[4, 4],
        strokeWidth=1.5,
        opacity=0.4,
    ).encode(
        color=alt.Color("series:N", scale=alt.Scale(
            domain=list(SCENARIO_PRESETS.keys()) + ["Census (Actual)", "StatCan Estimate", f"Scenario: {preset_name}"],
            range=["#ef4444", "#6b7280", "#3b82f6", "#10b981", "#1e293b", "#f59e0b", "#7c3aed"],
        ), legend=alt.Legend(title="Scenario")),
    )

    # Census points
    census_points = base_chart.transform_filter(
        alt.datum.series == "Census (Actual)"
    ).mark_circle(size=80, color="#1e293b").encode(
        tooltip=["year:Q", "population:Q"],
    )

    census_line = base_chart.transform_filter(
        alt.datum.series == "Census (Actual)"
    ).mark_line(strokeWidth=2.5, color="#1e293b")

    # Active scenario line (bold)
    active_line = base_chart.transform_filter(
        alt.datum.series == f"Scenario: {preset_name}"
    ).mark_line(strokeWidth=3, color="#7c3aed").encode(
        tooltip=["year:Q", "population:Q"],
    )

    active_points = base_chart.transform_filter(
        alt.datum.series == f"Scenario: {preset_name}"
    ).mark_circle(size=50, color="#7c3aed")

    # Estimate points (orange diamonds, dashed line)
    estimate_line = base_chart.transform_filter(
        alt.datum.series == "StatCan Estimate"
    ).mark_line(strokeWidth=2, color="#f59e0b", strokeDash=[6, 3])

    estimate_points = base_chart.transform_filter(
        alt.datum.series == "StatCan Estimate"
    ).mark_point(size=70, color="#f59e0b", shape="diamond", filled=True).encode(
        tooltip=["year:Q", "population:Q"],
    )

    chart = (fan_lines + census_line + census_points + estimate_line + estimate_points + active_line + active_points).properties(
        height=420,
    ).configure_axis(
        grid=True,
        gridOpacity=0.15,
    )

    st.altair_chart(chart, use_container_width=True)

    # --- Forecast Accuracy Badge ---
    if not estimate_hist.empty:
        # Compare our projection (from 2021 Census) against StatCan estimates
        # Run a "from Census 2021" baseline projection to get what we WOULD have projected
        from scripts.scenario_engine import get_census_age_data, calculate_ccrs, project_population
        _census = get_census_age_data(selected_code)
        if not _census.empty:
            _ccrs = calculate_ccrs(_census)
            _latest = _census.iloc[-1]
            _census_base_year = int(_latest["census_year"])
            _census_base = {
                "youth": float(_latest.get("pop_0_14", 0)),
                "working": float(_latest.get("pop_15_64", 0)),
                "senior": float(_latest.get("pop_65_plus", 0)),
            }
            _census_base["total"] = _census_base["youth"] + _census_base["working"] + _census_base["senior"]
            _proj_from_census = project_population(_census_base, _ccrs, start_year=_census_base_year, end_year=end_year)

            # Interpolate to get annual values for comparison
            from scripts.scenario_engine import interpolate_annual
            if _proj_from_census["year"].diff().max() > 1:
                _proj_from_census = interpolate_annual(_proj_from_census)

            # Calculate MAPE for overlapping years
            errors = []
            for _, est_row in estimate_hist.iterrows():
                yr = int(est_row["year"])
                actual = float(est_row["population"])
                projected = _proj_from_census[_proj_from_census["year"] == yr]
                if not projected.empty and actual > 0:
                    proj_val = float(projected["total"].values[0])
                    pct_error = abs(proj_val - actual) / actual * 100
                    errors.append({"year": yr, "projected": int(proj_val), "actual": int(actual), "error_pct": round(pct_error, 1)})

            if errors:
                mape = sum(e["error_pct"] for e in errors) / len(errors)
                if mape <= 2:
                    badge_color, badge_icon = "#10b981", "🟢"
                elif mape <= 5:
                    badge_color, badge_icon = "#f59e0b", "🟡"
                else:
                    badge_color, badge_icon = "#ef4444", "🔴"

                years_str = ", ".join(str(e["year"]) for e in errors)
                st.markdown(f"""
                <div style="background: {badge_color}22; border-left: 4px solid {badge_color}; padding: 10px 15px; border-radius: 4px; margin-bottom: 10px;">
                    {badge_icon} <strong>Forecast Verification:</strong> MAPE = <strong>{mape:.1f}%</strong>
                    <span style="color: #64748b;"> — comparing our {_census_base_year} Census-based projection to StatCan estimates for {years_str}</span>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("📊 Forecast vs. Actual Detail"):
                    err_df = pd.DataFrame(errors)
                    st.dataframe(err_df, hide_index=True, use_container_width=True)

    # CCR display
    st.markdown("**Cohort Change Ratios** (2016 → 2021):")
    ccr_cols = st.columns(3)
    ccr_labels = [
        ("Youth (0–14)", ccrs["youth"], "How fast the youth population is changing"),
        ("Working Age (15–64)", ccrs["working"], "Working-age retention/attraction"),
        ("Seniors (65+)", ccrs["senior"], "Senior population growth rate"),
    ]
    for col, (label, value, desc) in zip(ccr_cols, ccr_labels):
        color = "#10b981" if value >= 1.0 else "#ef4444"
        col.markdown(f'<span class="ccr-badge" style="color:{color}">{label}: {value:.3f}</span>', unsafe_allow_html=True)
        col.caption(desc)

    _cohort_label = "18 five-year cohort Hamilton-Perry with diagonal survival ratios" if meta.get("cohort_mode") else "3-band Cohort Change Ratios"
    st.markdown(f"""
    <div class="method-note">
        <strong>Methodology:</strong> {_cohort_label} derived from
        2016 and 2021 Census data. {'Calibrated to Ontario MOF ' + selected_county + ' County projections via share-capture raking.' if meta['use_mof'] else 'Running without MOF controls.'}
        Migration factor: {migration}×, Aging rate: {aging}×{f', Housing cap: {housing_cap:,} units' if housing_cap > 0 else ''}.
    </div>
    """, unsafe_allow_html=True)


# ---- Tab 2: Age Structure ----
with tab_structure:
    st.subheader("Age Structure Over Time")

    # Stacked area chart of age bands
    structure_data = []
    for _, row in proj.iterrows():
        for band, key, color in [
            ("0–14 (Youth)", "youth", "#3b82f6"),
            ("15–64 (Working)", "working", "#10b981"),
            ("65+ (Senior)", "senior", "#f59e0b"),
        ]:
            structure_data.append({
                "year": int(row["year"]),
                "Age Group": band,
                "Population": int(row[key]),
            })

    struct_df = pd.DataFrame(structure_data)

    area_chart = alt.Chart(struct_df).mark_area(opacity=0.75).encode(
        x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
        y=alt.Y("Population:Q", stack="zero"),
        color=alt.Color("Age Group:N", scale=alt.Scale(
            domain=["0–14 (Youth)", "15–64 (Working)", "65+ (Senior)"],
            range=["#3b82f6", "#10b981", "#f59e0b"],
        )),
        tooltip=["year:Q", "Age Group:N", "Population:Q"],
    ).properties(height=380)

    st.altair_chart(area_chart, use_container_width=True)

    # Dependency ratio line
    st.markdown("#### Dependency Ratio Trend")
    st.caption("(Youth + Seniors) ÷ Working Age × 100. Higher = more dependents per worker.")

    dep_chart = alt.Chart(proj).mark_line(
        strokeWidth=2.5,
        color="#ef4444",
        point=alt.OverlayMarkDef(size=40),
    ).encode(
        x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
        y=alt.Y("dependency_ratio:Q", title="Dependency Ratio", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("year:Q", title="Year"),
            alt.Tooltip("dependency_ratio:Q", title="Dep. Ratio", format=".1f"),
        ],
    ).properties(height=280)

    st.altair_chart(dep_chart, use_container_width=True)

    # Share breakdown table
    st.markdown("#### Age Band Shares")
    share_cols = ["year", "youth_share_pct", "working_share_pct", "senior_share_pct", "dependency_ratio"]
    if all(c in proj.columns for c in share_cols):
        display = proj[proj["year"] % 5 == 1][share_cols].copy() if len(proj) > 10 else proj[share_cols].copy()
        display.columns = ["Year", "Youth %", "Working %", "Senior %", "Dep. Ratio"]
        st.dataframe(display, use_container_width=True, hide_index=True)


# ---- Tab 3: Housing Demand ----
with tab_housing:
    st.subheader(f"🏠 Housing Demand: {selected_name}")

    h_demand = housing["housing_demand"]
    h_profile = housing["housing_profile"]
    h_mix = housing["dwelling_mix"]
    h_bill23 = housing.get("bill23_gap", {})

    if h_demand.empty or not h_profile:
        st.warning("Housing data not available for this community. Census dwelling indicators may be missing.")
    else:
        # --- Current Stock Summary ---
        st.markdown("#### Current Housing Stock (Census)")
        stock_cols = st.columns(5)

        stock_metrics = [
            ("Total Dwellings", f"{int(h_profile.get('total_dwellings', 0)):,}"),
            ("Owner Occupied", f"{h_profile.get('owner_pct', 0):.0f}%"),
            ("Renter Occupied", f"{h_profile.get('renter_pct', 0):.0f}%"),
            ("Unaffordable (Own)", f"{h_profile.get('unaffordable_owner_pct', 0):.0f}%"),
            ("Unaffordable (Rent)", f"{h_profile.get('unaffordable_renter_pct', 0):.0f}%"),
        ]

        for col, (label, value) in zip(stock_cols, stock_metrics):
            col.markdown(f"""
            <div class="housing-card">
                <div class="label">{label}</div>
                <div class="value">{value}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")

        # --- Dwelling Type Breakdown ---
        dw_types = h_profile.get("dwelling_types", {})
        if dw_types:
            dw_df = pd.DataFrame([
                {"Type": k, "Units": int(v) if pd.notna(v) else 0}
                for k, v in dw_types.items() if pd.notna(v) and v > 0
            ])
            if not dw_df.empty:
                dw_chart = alt.Chart(dw_df).mark_arc(innerRadius=60).encode(
                    theta=alt.Theta("Units:Q"),
                    color=alt.Color("Type:N", scale=alt.Scale(
                        scheme="tableau10"
                    )),
                    tooltip=["Type:N", alt.Tooltip("Units:Q", format=",")],
                ).properties(height=280, title="Dwelling Type Mix")

                col_donut, col_demand = st.columns([1, 2])
                with col_donut:
                    st.altair_chart(dw_chart, use_container_width=True)

                with col_demand:
                    # --- Units Needed Over Time ---
                    st.markdown("#### Projected Housing Units Needed")

                    current_stock = h_profile.get("total_dwellings", 0)

                    demand_chart_data = h_demand[["year", "units_needed", "new_units_from_base"]].copy()
                    demand_chart_data.columns = ["Year", "Total Units Needed", "New Units Required"]

                    base = alt.Chart(demand_chart_data).encode(
                        x=alt.X("Year:Q", axis=alt.Axis(format="d")),
                    )

                    units_line = base.mark_line(
                        strokeWidth=2.5, color="#f59e0b",
                        point=alt.OverlayMarkDef(size=40)
                    ).encode(
                        y=alt.Y("Total Units Needed:Q", title="Total Units", scale=alt.Scale(zero=False)),
                        tooltip=["Year:Q", alt.Tooltip("Total Units Needed:Q", format=",")],
                    )

                    # Horizontal line for current stock
                    stock_rule = alt.Chart(pd.DataFrame({"y": [current_stock]})).mark_rule(
                        strokeDash=[5, 3], color="#6b7280", strokeWidth=1.5
                    ).encode(y="y:Q")

                    stock_label = alt.Chart(pd.DataFrame({
                        "x": [int(h_demand["year"].max())],
                        "y": [current_stock],
                        "label": [f"Current Stock: {current_stock:,}"]
                    })).mark_text(align="right", dy=-10, fontSize=11, color="#6b7280").encode(
                        x="x:Q", y="y:Q", text="label:N"
                    )

                    demand_combined = (units_line + stock_rule + stock_label).properties(height=250)
                    st.altair_chart(demand_combined, use_container_width=True)

        st.markdown("---")

        # --- Housing Demand Table ---
        st.markdown("#### Housing Demand Projections")

        h_key_years = h_demand[h_demand["year"].isin([2021, 2026, 2031, 2036, 2041, 2046, 2051])].copy()
        if h_key_years.empty:
            h_key_years = h_demand.copy()

        h_display = h_key_years[[
            "year", "population", "proj_hh_size", "households",
            "units_needed", "new_units_from_base", "senior_hh_share_pct"
        ]].copy()
        h_display.columns = [
            "Year", "Population", "Proj. HH Size", "Households",
            "Units Needed", "New Units", "Senior HH Share %"
        ]
        st.dataframe(h_display, use_container_width=True, hide_index=True)

        # --- Dwelling Mix Projection ---
        if not h_mix.empty:
            st.markdown("#### Projected Dwelling Mix")
            st.caption("As the senior household share increases, demand shifts from single-detached to apartment units.")

            # Melt for stacked area
            type_cols = [c for c in h_mix.columns if c not in ["year", "total_units"]]
            if type_cols:
                mix_long = h_mix.melt(
                    id_vars=["year"],
                    value_vars=type_cols,
                    var_name="Dwelling Type",
                    value_name="Units",
                )

                mix_chart = alt.Chart(mix_long).mark_area(opacity=0.7).encode(
                    x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                    y=alt.Y("Units:Q", stack="zero"),
                    color=alt.Color("Dwelling Type:N", scale=alt.Scale(scheme="tableau10")),
                    tooltip=["year:Q", "Dwelling Type:N", alt.Tooltip("Units:Q", format=",")],
                ).properties(height=350)

                st.altair_chart(mix_chart, use_container_width=True)

        # --- Bill 23 Gap Analysis ---
        if h_bill23:
            st.markdown("---")
            st.markdown("#### Bill 23 Gap Analysis")

            gap = h_bill23["gap"]
            gap_class = "gap-positive" if gap > 0 else "gap-negative"

            gap_cols = st.columns(4)
            gap_cols[0].metric("Provincial Target", f"{h_bill23['provincial_target']:,} units")
            gap_cols[1].metric("Demographic Demand", f"{h_bill23['demographic_demand']:,} units")
            gap_cols[2].metric("Gap", f"{gap:+,} units", delta=f"{h_bill23['gap_pct']:+.1f}%")
            gap_cols[3].metric("Annual Pace Needed", f"{h_bill23['annual_units_target']:,}/yr")

            if h_bill23["exceeds_demand"]:
                st.markdown(f"""
                <div class="gap-positive">
                    <strong>⚠️ Target exceeds demographic demand by {gap:,} units ({h_bill23['gap_pct']:.1f}%).</strong><br>
                    Filling this target would require <strong>{h_bill23['pop_growth_pct']:.1f}%</strong> population growth
                    ({h_bill23['pop_growth_needed']:,} additional residents) — significantly above the projected scenario.
                    This suggests the target assumes in-migration beyond current demographic trends,
                    or addresses existing pent-up demand.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="gap-negative">
                    <strong>✅ Demographic demand ({h_bill23['demographic_demand']:,}) meets or exceeds the provincial target.</strong><br>
                    Annual demographic demand: {h_bill23['annual_units_demographic']:,} units/year.
                    Target pace: {h_bill23['annual_units_target']:,} units/year.
                </div>
                """, unsafe_allow_html=True)

        # Methodology note
        st.markdown(f"""
        <div class="method-note">
            <strong>Housing Methodology:</strong> Population → households (using projected declining HH size,
            starting at {h_profile.get('avg_hh_size', 2.5)} PPU, declining 0.5%/yr) → units needed
            (with {vacancy_rate:.0%} vacancy buffer). Dwelling mix shifts as senior household share increases:
            higher senior share → more apartment demand. Headship rates: Working 42%, Senior 62%.
        </div>
        """, unsafe_allow_html=True)


# ---- Tab 4: Infrastructure Load ----
with tab_infra:
    st.subheader(f"🏗️ Infrastructure Load: {selected_name}")

    i_load = infra["infrastructure_load"]
    i_dc = infra["development_charges"]

    if i_load.empty:
        st.warning("Infrastructure data not available.")
    else:
        # --- KPI row ---
        base_infra = i_load.iloc[0]
        end_infra = i_load.iloc[-1]

        infra_cols = st.columns(4)
        infra_cols[0].metric("Water Demand", f"{end_infra['water_demand_m3d']:,.0f} m³/day",
                            delta=f"{end_infra['water_demand_m3d'] - base_infra['water_demand_m3d']:+,.0f}")
        infra_cols[1].metric("School Seats", f"{end_infra['total_students']:,}",
                            delta=f"{end_infra['total_students'] - base_infra['total_students']:+,}")
        infra_cols[2].metric("ER Visits/yr", f"{end_infra['total_er_visits']:,}",
                            delta=f"{end_infra['total_er_visits'] - base_infra['total_er_visits']:+,}")
        infra_cols[3].metric("Family Docs Needed", f"{end_infra['family_docs_needed']:.0f}",
                            delta=f"{end_infra['family_docs_needed'] - base_infra['family_docs_needed']:+.0f}")

        st.markdown("")

        # --- Capacity Utilization KPIs (if user provided capacity) ---
        if user_water_cap > 0 or user_ww_cap > 0:
            st.markdown("#### 🚰 System Capacity Utilization (at Maximum Day Demand)")
            st.caption("Utilization calculated at MDD (2.0x average daily demand), per MECP design standards.")
            util_cols = st.columns(4)
            if user_water_cap > 0:
                pf = 2.0  # MDD peaking factor
                water_util_now = base_infra['water_demand_m3d'] * pf / user_water_cap * 100
                water_util_end = end_infra['water_demand_m3d'] * pf / user_water_cap * 100
                util_color = "inverse" if water_util_end > 80 else "normal"
                util_cols[0].metric("Water MDD Util. (Now)", f"{water_util_now:.0f}%")
                util_cols[1].metric("Water MDD Util. (Projected)", f"{water_util_end:.0f}%",
                                   delta=f"{water_util_end - water_util_now:+.0f}pp")
            if user_ww_cap > 0:
                pf = 2.0
                ww_util_now = base_infra['ww_demand_m3d'] * pf / user_ww_cap * 100
                ww_util_end = end_infra['ww_demand_m3d'] * pf / user_ww_cap * 100
                util_cols[2].metric("WW MDD Util. (Now)", f"{ww_util_now:.0f}%")
                util_cols[3].metric("WW MDD Util. (Projected)", f"{ww_util_end:.0f}%",
                                   delta=f"{ww_util_end - ww_util_now:+.0f}pp")

            # Warning if approaching capacity
            if user_water_cap > 0 and water_util_end > 80:
                st.warning(f"⚠️ **Water system projected to reach {water_util_end:.0f}% of rated capacity by {int(end_row['year'])}.** "
                           f"MECP recommends expansion planning when utilization exceeds 80%.")
            if user_ww_cap > 0 and ww_util_end > 80:
                st.warning(f"⚠️ **Wastewater system projected to reach {ww_util_end:.0f}% of rated capacity by {int(end_row['year'])}.** "
                           f"Lagoon and WWTP expansions typically require 5–7 years of EA and construction.")
            st.markdown("")

        # --- Water & Wastewater Chart ---
        col_water, col_school = st.columns(2)

        with col_water:
            st.markdown("#### Water & Wastewater Demand")
            ww_data = i_load[["year", "water_demand_m3d", "ww_demand_m3d"]].melt(
                id_vars=["year"], var_name="Type", value_name="m³/day"
            )
            ww_data["Type"] = ww_data["Type"].map({
                "water_demand_m3d": "Water",
                "ww_demand_m3d": "Wastewater",
            })
            ww_chart = alt.Chart(ww_data).mark_line(
                strokeWidth=2.5, point=alt.OverlayMarkDef(size=30)
            ).encode(
                x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("m³/day:Q", title="m³/day", scale=alt.Scale(zero=False)),
                color=alt.Color("Type:N", scale=alt.Scale(
                    domain=["Water", "Wastewater"],
                    range=["#3b82f6", "#8b5cf6"]
                )),
                tooltip=["year:Q", "Type:N", alt.Tooltip("m³/day:Q", format=",.0f")],
            ).properties(height=280)

            # Add capacity lines if user provided values
            capacity_layers = [ww_chart]
            if user_water_cap > 0:
                water_cap_line = alt.Chart(pd.DataFrame({"y": [user_water_cap]})).mark_rule(
                    strokeDash=[5, 3], color="#3b82f6", strokeWidth=2
                ).encode(y="y:Q")
                water_cap_label = alt.Chart(pd.DataFrame({
                    "x": [int(i_load["year"].max())],
                    "y": [user_water_cap],
                    "label": [f"Water Capacity: {user_water_cap:,.0f}"]
                })).mark_text(align="right", dy=-10, fontSize=10, color="#3b82f6").encode(
                    x="x:Q", y="y:Q", text="label:N"
                )
                capacity_layers.extend([water_cap_line, water_cap_label])
            if user_ww_cap > 0:
                ww_cap_line = alt.Chart(pd.DataFrame({"y": [user_ww_cap]})).mark_rule(
                    strokeDash=[5, 3], color="#8b5cf6", strokeWidth=2
                ).encode(y="y:Q")
                ww_cap_label = alt.Chart(pd.DataFrame({
                    "x": [int(i_load["year"].max())],
                    "y": [user_ww_cap],
                    "label": [f"WW Capacity: {user_ww_cap:,.0f}"]
                })).mark_text(align="right", dy=-10, fontSize=10, color="#8b5cf6").encode(
                    x="x:Q", y="y:Q", text="label:N"
                )
                capacity_layers.extend([ww_cap_line, ww_cap_label])

            combined_ww = alt.layer(*capacity_layers).properties(height=280)
            st.altair_chart(combined_ww, use_container_width=True)

        with col_school:
            st.markdown("#### School Seats Needed")
            school_data = i_load[["year", "elementary_students", "secondary_students"]].melt(
                id_vars=["year"], var_name="Level", value_name="Students"
            )
            school_data["Level"] = school_data["Level"].map({
                "elementary_students": "Elementary",
                "secondary_students": "Secondary",
            })
            school_chart = alt.Chart(school_data).mark_area(opacity=0.7).encode(
                x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("Students:Q", stack="zero"),
                color=alt.Color("Level:N", scale=alt.Scale(
                    domain=["Elementary", "Secondary"],
                    range=["#10b981", "#f59e0b"]
                )),
                tooltip=["year:Q", "Level:N", alt.Tooltip("Students:Q", format=",")],
            ).properties(height=280)
            st.altair_chart(school_chart, use_container_width=True)

        # --- Healthcare ---
        st.markdown("#### Healthcare Demand")
        col_er, col_docs = st.columns(2)
        with col_er:
            er_chart = alt.Chart(i_load).mark_line(
                strokeWidth=2.5, color="#ef4444", point=alt.OverlayMarkDef(size=30)
            ).encode(
                x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("total_er_visits:Q", title="ER Visits/Year", scale=alt.Scale(zero=False)),
                tooltip=["year:Q", alt.Tooltip("total_er_visits:Q", format=",")],
            ).properties(height=250)

            # Overlay: senior ER visits
            er_senior = alt.Chart(i_load).mark_area(
                opacity=0.3, color="#fbbf24"
            ).encode(
                x="year:Q",
                y=alt.Y("er_visits_senior:Q", title="ER Visits/Year"),
            )
            st.altair_chart(er_senior + er_chart, use_container_width=True)
            st.caption("🟡 Yellow area = Senior ER visits. 🔴 Red line = Total ER visits.")

        with col_docs:
            doc_chart = alt.Chart(i_load).mark_line(
                strokeWidth=2.5, color="#6366f1", point=alt.OverlayMarkDef(size=30)
            ).encode(
                x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("family_docs_needed:Q", title="Family Doctors Needed", scale=alt.Scale(zero=False)),
                tooltip=["year:Q", alt.Tooltip("family_docs_needed:Q", format=".0f")],
            ).properties(height=250)
            st.altair_chart(doc_chart, use_container_width=True)
            st.caption(f"Based on Ontario avg of 1.1 family docs per 1,000 population (CIHI).")

        # --- Development Charges ---
        st.markdown("---")
        st.markdown("#### Development Charge Estimate")
        st.caption(f"Based on {i_dc['new_units']:,} new units needed by {int(end_row['year'])}")

        dc_cols = st.columns(3)
        dc_cols[0].metric("Per Unit", f"${i_dc['total_per_unit']:,}")
        dc_cols[1].metric("New Units", f"{i_dc['new_units']:,}")
        dc_cols[2].metric("Total DC Revenue", f"${i_dc['total_aggregate']:,.0f}")

        # DC breakdown bar
        dc_df = pd.DataFrame([
            {"Component": k, "$/Unit": v}
            for k, v in i_dc["components"].items()
        ])
        dc_bar = alt.Chart(dc_df).mark_bar(cornerRadiusTopRight=4, cornerRadiusTopLeft=4).encode(
            x=alt.X("Component:N", sort="-y", title=None),
            y=alt.Y("$/Unit:Q", title="$ per Unit"),
            color=alt.Color("Component:N", scale=alt.Scale(scheme="tableau10"), legend=None),
            tooltip=["Component:N", alt.Tooltip("$/Unit:Q", format="$,")],
        ).properties(height=250)
        st.altair_chart(dc_bar, use_container_width=True)

        st.markdown(f"""
        <div class="method-note">
            <strong>Infrastructure Methodology:</strong> Water demand: {220} L/capita/day Average Daily Demand (ADD).
            Capacity utilization calculated at Maximum Day Demand (MDD = 2.0× ADD), per MECP design standards.
            School seats: youth × enrollment rates (Elem 88%, Sec 92%). ER visits: age-specific rates
            (Ontario avg per 1,000). Development Charges: FCM/Watson Southern Ontario benchmarks.
        </div>
        """, unsafe_allow_html=True)


# ---- Tab 5: Economic Impact ----
with tab_econ:
    st.subheader(f"💰 Economic Impact: {selected_name}")

    e_proj = econ["economic_projection"]

    if e_proj.empty:
        st.warning("Economic data not available.")
    else:
        base_econ = e_proj.iloc[0]
        end_econ = e_proj.iloc[-1]

        # --- KPI row ---
        econ_cols = st.columns(4)
        econ_cols[0].metric("Tax Revenue", f"${end_econ['total_tax_rev']:,.0f}",
                            delta=f"${end_econ['total_tax_rev'] - base_econ['total_tax_rev']:+,.0f}")
        econ_cols[1].metric("Labour Force", f"{end_econ['labour_force']:,}",
                            delta=f"{end_econ['labour_force'] - base_econ['labour_force']:+,}")
        econ_cols[2].metric("Fiscal Balance", f"${end_econ['fiscal_balance']:,.0f}",
                            delta=f"${end_econ['fiscal_per_capita']:+,}/capita")
        econ_cols[3].metric("Construction Value", f"${end_econ['construction_value']:,.0f}",
                            delta=f"{end_econ['construction_jobs']:,} jobs")

        # --- Fiscal Balance Explanation ---
        st.info(
            "📊 **Understanding the Fiscal Balance:** Service costs shown here span **three levels of government**: "
            "municipal (lower-tier and upper-tier/county), provincial (education, healthcare), and federal. "
            "Property tax is only the **lower-tier municipal** revenue source — it is not meant to cover "
            "provincial healthcare or education costs. The remaining ~40–60% is funded by provincial grants, "
            "federal transfers, user fees, and upper-tier levies. A negative balance here is normal and expected.",
            icon="ℹ️",
        )

        st.markdown("")

        # --- Tax Revenue & Service Cost ---
        col_tax, col_fiscal = st.columns(2)

        with col_tax:
            st.markdown("#### Tax Revenue vs Service Costs")
            fiscal_data = e_proj[["year", "total_tax_rev", "service_cost_total"]].melt(
                id_vars=["year"], var_name="Type", value_name="Amount"
            )
            fiscal_data["Type"] = fiscal_data["Type"].map({
                "total_tax_rev": "Tax Revenue",
                "service_cost_total": "Service Costs",
            })
            fiscal_chart = alt.Chart(fiscal_data).mark_line(
                strokeWidth=2.5, point=alt.OverlayMarkDef(size=30)
            ).encode(
                x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("Amount:Q", title="$", scale=alt.Scale(zero=False)),
                color=alt.Color("Type:N", scale=alt.Scale(
                    domain=["Tax Revenue", "Service Costs"],
                    range=["#10b981", "#ef4444"]
                )),
                tooltip=["year:Q", "Type:N", alt.Tooltip("Amount:Q", format="$,.0f")],
            ).properties(height=300)
            st.altair_chart(fiscal_chart, use_container_width=True)

        with col_fiscal:
            st.markdown("#### Fiscal Balance per Capita")
            balance_chart = alt.Chart(e_proj).mark_bar(
                cornerRadiusTopRight=3, cornerRadiusTopLeft=3
            ).encode(
                x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y("fiscal_per_capita:Q", title="$/capita"),
                color=alt.condition(
                    alt.datum.fiscal_per_capita >= 0,
                    alt.value("#10b981"),
                    alt.value("#ef4444")
                ),
                tooltip=["year:Q", alt.Tooltip("fiscal_per_capita:Q", format="$,.0f")],
            ).properties(height=300)
            st.altair_chart(balance_chart, use_container_width=True)

        # --- Labour Force ---
        st.markdown("#### Labour Force Projection")
        labour_data = e_proj[["year", "employed", "unemployed"]].melt(
            id_vars=["year"], var_name="Status", value_name="Workers"
        )
        labour_data["Status"] = labour_data["Status"].map({
            "employed": "Employed",
            "unemployed": "Unemployed",
        })
        labour_chart = alt.Chart(labour_data).mark_area(opacity=0.7).encode(
            x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
            y=alt.Y("Workers:Q", stack="zero"),
            color=alt.Color("Status:N", scale=alt.Scale(
                domain=["Employed", "Unemployed"],
                range=["#3b82f6", "#f59e0b"]
            )),
            tooltip=["year:Q", "Status:N", alt.Tooltip("Workers:Q", format=",")],
        ).properties(height=280)
        st.altair_chart(labour_chart, use_container_width=True)

        # --- Data Table ---
        st.markdown("#### Economic Projections Data")
        e_key = e_proj[e_proj["year"].isin([2021, 2026, 2031, 2036, 2041, 2046, 2051])].copy()
        if e_key.empty:
            e_key = e_proj.copy()
        e_display = e_key[[
            "year", "total_tax_rev", "service_cost_total",
            "fiscal_balance", "labour_force", "employed",
            "construction_value", "construction_jobs"
        ]].copy()
        e_display.columns = [
            "Year", "Tax Revenue", "Service Costs",
            "Fiscal Balance", "Labour Force", "Employed",
            "Construction $", "Construction Jobs"
        ]
        st.dataframe(e_display, use_container_width=True, hide_index=True)

        # ── Phase 5B: Property Tax Implications Card ─────────────────────
        st.markdown("---")
        st.markdown("#### 🏛️ Property Tax Implications for Farmland")

        _hh_base = int(base_econ.get("est_households", base_row.get("est_households", 0)))
        _hh_end = int(end_econ.get("est_households", end_row.get("est_households", 0)))
        _hh_delta = _hh_end - _hh_base

        # Use FIR actuals if available, else Ontario benchmarks
        _eff_assess = local_assessment if local_assessment > 0 else 350_000
        _eff_mill = local_mill_rate if local_mill_rate > 0 else 0.0085

        _new_res_tax_base = _hh_delta * _eff_assess
        _new_res_tax_rev = _new_res_tax_base * _eff_mill
        _data_source = "FIR actuals" if (local_mill_rate > 0 or local_assessment > 0) else "Ontario benchmarks"

        # Farm tax impact: if the residential base grows, the farm tax share decreases
        # under revenue-neutral assumptions (more houses = farm share diluted)
        _farm_ratio = 0.25  # Provincial maximum
        _farm_cva = 0
        if has_fir:
            _fir_ratio = fir_row.get("farmland_tax_ratio")
            if _fir_ratio and not pd.isna(_fir_ratio) and _fir_ratio > 0:
                _farm_ratio = float(_fir_ratio)
            _fir_farm_cva = fir_row.get("farmland_cva")
            if _fir_farm_cva and not pd.isna(_fir_farm_cva):
                _farm_cva = float(_fir_farm_cva)

        _current_res_cva = _hh_base * _eff_assess
        _future_res_cva = _hh_end * _eff_assess
        _total_base_current = _current_res_cva + _farm_cva
        _total_base_future = _future_res_cva + _farm_cva

        # Farm share of tax base now vs future
        _farm_share_now = _farm_cva / _total_base_current * 100 if _total_base_current > 0 else 0
        _farm_share_future = _farm_cva / _total_base_future * 100 if _total_base_future > 0 else 0
        _farm_share_delta = _farm_share_future - _farm_share_now

        _ptax_cols = st.columns(4)
        _ptax_cols[0].metric(
            "Δ Households", f"{_hh_delta:+,}",
            delta=f"{int(base_row['year'])} → {int(end_row['year'])}",
            delta_color="off",
        )
        _ptax_cols[1].metric(
            "New Res. Tax Revenue", f"${_new_res_tax_rev:,.0f}",
            delta=f"${_new_res_tax_base/1e6:,.0f}M new CVA",
            delta_color="off",
        )
        _ptax_cols[2].metric(
            "Farm CVA Share", f"{_farm_share_future:.1f}%",
            delta=f"{_farm_share_delta:+.1f}pp" if _farm_cva > 0 else "No FIR data",
            delta_color="normal" if _farm_share_delta <= 0 else "inverse",
        )
        _ptax_cols[3].metric(
            "Farm Tax Ratio", f"{_farm_ratio:.4f}",
            help="Current farm-to-residential tax ratio from FIR data" if has_fir else "Provincial max (0.25) — no FIR data available",
        )

        if _hh_delta > 0 and _farm_cva > 0:
            st.success(
                f"📉 **Population growth dilutes farm tax burden.** With {_hh_delta:,} new households "
                f"adding ${_new_res_tax_base/1e6:,.0f}M to the residential tax base, farmland's share "
                f"of the total assessment base drops from **{_farm_share_now:.1f}%** to "
                f"**{_farm_share_future:.1f}%** — a {abs(_farm_share_delta):.1f}pp reduction."
            )
        elif _hh_delta < 0 and _farm_cva > 0:
            st.warning(
                f"📈 **Population decline concentrates farm tax burden.** With {abs(_hh_delta):,} "
                f"fewer households, farmland's share of the total assessment base **increases** from "
                f"**{_farm_share_now:.1f}%** to **{_farm_share_future:.1f}%** — a "
                f"{abs(_farm_share_delta):.1f}pp increase."
            )
        elif _farm_cva == 0:
            st.info("FIR farmland CVA data not available for this municipality. Tax implications shown using Ontario benchmarks only.")

        st.caption(f"Calculations use {_data_source}. CVA frozen at 2016 MPAC levels — growth comes from new units only.")


        # Dynamic methodology note showing actual values used
        display_mill = local_mill_rate if local_mill_rate > 0 else 0.0085
        display_assess = local_assessment if local_assessment > 0 else 350_000
        is_custom_econ = local_mill_rate > 0 or local_assessment > 0
        custom_note = " *(using your local values)*" if is_custom_econ else " *(Ontario benchmarks)*"

        st.markdown(f"""
        <div class="method-note">
            <strong>Economic Methodology:</strong> Tax base: est. households × ${display_assess:,.0f} avg assessment × {display_mill*100:.2f}% mill rate{custom_note}.
            Service costs: age-weighted per capita (Youth $3,200, Working $1,800, Senior $4,500) —
            includes all government levels (see note above).
            Labour force: working-age × 65% + senior × 15% participation.
            Construction: $320K/unit, 150 jobs per 100 units (direct + indirect).
        </div>
        """, unsafe_allow_html=True)


# ---- Tab 6: MOF Comparison ----
with tab_compare:
    st.subheader(f"MOF Comparison: {selected_name} vs. {selected_county} County")

    mof_county = result["mof_county"]
    if mof_county.empty:
        st.info("MOF projections not available. Download from Ontario Data Catalogue and run `python scripts/fetch_mof_projections.py`.")
    else:
        # Show local share of county
        mof_2024 = mof_county[mof_county["year"] == 2024]
        if not mof_2024.empty:
            county_pop = int(mof_2024["total"].values[0])
            local_share = base_row["total"] / county_pop * 100 if county_pop > 0 else 0

            share_cols_display = st.columns(3)
            share_cols_display[0].metric(f"{selected_county} County (2024)", f"{county_pop:,}")
            share_cols_display[1].metric(f"{selected_name} (Base)", f"{int(base_row['total']):,}")
            share_cols_display[2].metric("Local Share", f"{local_share:.1f}%")

        # Dual-axis: county on left, local on right
        compare_data = []
        for _, row in mof_county.iterrows():
            compare_data.append({
                "year": int(row["year"]),
                "population": int(row["total"]),
                "series": f"{selected_county} County (MOF)",
            })
        for _, row in proj.iterrows():
            compare_data.append({
                "year": int(row["year"]),
                "population": int(row["total"]),
                "series": f"{selected_name} (Projected)",
            })

        compare_df = pd.DataFrame(compare_data)

        # They're on very different scales, use independent Y axes
        county_chart = alt.Chart(compare_df).transform_filter(
            alt.datum.series == f"{selected_county} County (MOF)"
        ).mark_line(strokeWidth=2, color="#94a3b8", strokeDash=[5, 3]).encode(
            x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
            y=alt.Y("population:Q", title=f"{selected_county} County", axis=alt.Axis(titleColor="#94a3b8")),
            tooltip=["year:Q", alt.Tooltip("population:Q", format=",")],
        )

        local_chart = alt.Chart(compare_df).transform_filter(
            alt.datum.series == f"{selected_name} (Projected)"
        ).mark_line(strokeWidth=2.5, color="#7c3aed").encode(
            x="year:Q",
            y=alt.Y("population:Q", title=f"{selected_name}", axis=alt.Axis(titleColor="#7c3aed")),
            tooltip=["year:Q", alt.Tooltip("population:Q", format=",")],
        )

        dual = alt.layer(county_chart, local_chart).resolve_scale(
            y="independent"
        ).properties(height=380)

        st.altair_chart(dual, use_container_width=True)
        st.caption("Grey dashed = MOF county projection. Purple = local scenario projection.")


# ---- Tab 7: Scenario Comparison ----
with tab_scenarios:
    st.subheader(f"Scenario Comparison: {selected_name}")

    # Let user pick a second preset to compare against
    compare_presets = [p for p in SCENARIO_PRESETS.keys() if p != preset_name]
    compare_preset_name = st.selectbox(
        "Compare against",
        options=compare_presets,
        index=0,
        help="Select a second scenario preset to compare side-by-side with your current scenario.",
        key="scenario_compare_selector",
    )
    compare_preset = SCENARIO_PRESETS[compare_preset_name]

    # Run the comparison scenario (cached to avoid redundant engine calls)
    @st.cache_data(max_entries=3, ttl=1800, show_spinner=False)
    def _run_comparison_scenario(_sgc, _county, _mig, _age, _hh, _mof, _ey):
        return run_scenario(
            sgc_code=_sgc,
            county_name=_county,
            migration_factor=_mig,
            aging_factor=_age,
            housing_cap=0,
            avg_hh_size=_hh,
            use_mof_controls=_mof,
            end_year=_ey,
        )

    with st.spinner(f"Running {compare_preset_name} scenario..."):
        compare_result = _run_comparison_scenario(
            selected_code, selected_county,
            compare_preset["migration_factor"],
            compare_preset["aging_factor"],
            avg_hh, use_mof, end_year,
        )

    if "error" in compare_result:
        st.error(f"Could not run comparison scenario: {compare_result['error']}")
    else:
        comp_proj = compare_result["projection"]
        comp_end = comp_proj.iloc[-1]

        # Calculate comparison housing & econ metrics
        comp_housing = calculate_housing_metrics(
            compare_result,
            vacancy_rate=vacancy_rate,
            provincial_target=provincial_target,
            target_year=target_year,
        )
        comp_econ = calculate_economic_metrics(
            compare_result, comp_housing,
            local_mill_rate=local_mill_rate,
            local_assessment=local_assessment,
        )

        # ── Side-by-side KPI Cards ──
        st.markdown("#### Key Metrics Comparison")
        st.markdown(f"**Current:** {preset_name} ({preset['description'][:60]}...)  ")
        st.markdown(f"**Comparison:** {compare_preset_name} ({compare_preset['description'][:60]}...)")
        st.markdown("")

        # Extract key metrics from both
        curr_pop = int(end_row["total"])
        comp_pop = int(comp_end["total"])
        curr_hh = int(end_row["est_households"])
        comp_hh = int(comp_end["est_households"])
        curr_senior = end_row["senior_share_pct"]
        comp_senior = comp_end["senior_share_pct"]
        curr_dep = end_row["dependency_ratio"]
        comp_dep = comp_end["dependency_ratio"]

        # Tax and fiscal from econ projections
        e_proj_curr = econ["economic_projection"]
        e_proj_comp = comp_econ["economic_projection"]
        curr_tax = e_proj_curr.iloc[-1]["total_tax_rev"] if not e_proj_curr.empty else 0
        comp_tax = e_proj_comp.iloc[-1]["total_tax_rev"] if not e_proj_comp.empty else 0
        curr_fiscal = e_proj_curr.iloc[-1]["fiscal_per_capita"] if not e_proj_curr.empty else 0
        comp_fiscal = e_proj_comp.iloc[-1]["fiscal_per_capita"] if not e_proj_comp.empty else 0

        # Display side-by-side
        kpi_data = [
            ("Population", f"{curr_pop:,}", f"{comp_pop:,}", curr_pop - comp_pop),
            ("Households", f"{curr_hh:,}", f"{comp_hh:,}", curr_hh - comp_hh),
            ("Senior Share", f"{curr_senior:.1f}%", f"{comp_senior:.1f}%", curr_senior - comp_senior),
            ("Dependency Ratio", f"{curr_dep:.1f}", f"{comp_dep:.1f}", curr_dep - comp_dep),
            ("Tax Revenue", f"${curr_tax:,.0f}", f"${comp_tax:,.0f}", curr_tax - comp_tax),
            ("Fiscal $/Capita", f"${curr_fiscal:,.0f}", f"${comp_fiscal:,.0f}", curr_fiscal - comp_fiscal),
        ]

        kpi_cols = st.columns(len(kpi_data))
        for col, (label, curr_val_str, comp_val_str, delta) in zip(kpi_cols, kpi_data):
            with col:
                st.markdown(f"**{label}**")
                st.markdown(f"🅰 {preset_name}: **{curr_val_str}**")
                st.markdown(f"🅱 {compare_preset_name}: **{comp_val_str}**")
                delta_sign = "+" if delta > 0 else ""
                delta_str = f"{delta_sign}{delta:,.1f}" if isinstance(delta, float) else f"{delta_sign}{delta:,}"
                st.caption(f"Δ {delta_str}")

        st.markdown("---")

        # ── Overlay Population Chart ──
        st.markdown("#### Population Projection Overlay")

        overlay_data = []
        for _, row in proj.iterrows():
            overlay_data.append({
                "year": int(row["year"]),
                "population": int(row["total"]),
                "series": f"{preset_name}",
            })
        for _, row in comp_proj.iterrows():
            overlay_data.append({
                "year": int(row["year"]),
                "population": int(row["total"]),
                "series": f"{compare_preset_name}",
            })

        overlay_df = pd.DataFrame(overlay_data)

        overlay_chart = alt.Chart(overlay_df).mark_line(
            strokeWidth=2.5, point=alt.OverlayMarkDef(size=30)
        ).encode(
            x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d")),
            y=alt.Y("population:Q", title="Population", scale=alt.Scale(zero=False)),
            color=alt.Color("series:N", scale=alt.Scale(
                domain=[preset_name, compare_preset_name],
                range=["#7c3aed", "#f59e0b"]
            ), legend=alt.Legend(title="Scenario")),
            strokeDash=alt.StrokeDash("series:N", scale=alt.Scale(
                domain=[preset_name, compare_preset_name],
                range=[[0], [6, 3]]
            ), legend=None),
            tooltip=["year:Q", alt.Tooltip("population:Q", format=","), "series:N"],
        ).properties(height=380)

        st.altair_chart(overlay_chart, use_container_width=True)
        st.caption(f"Purple solid = {preset_name}. Amber dashed = {compare_preset_name}.")

        # ── Detailed Comparison Table ──
        st.markdown("#### Year-by-Year Comparison")

        comp_table_rows = []
        for i, (_, row_a) in enumerate(proj.iterrows()):
            if i < len(comp_proj):
                row_b = comp_proj.iloc[i]
                yr = int(row_a["year"])
                pop_a = int(row_a["total"])
                pop_b = int(row_b["total"])
                diff = pop_a - pop_b
                diff_pct = (diff / pop_b * 100) if pop_b > 0 else 0
                comp_table_rows.append({
                    "Year": yr,
                    f"{preset_name} Pop": f"{pop_a:,}",
                    f"{compare_preset_name} Pop": f"{pop_b:,}",
                    "Difference": f"{diff:+,}",
                    "Diff %": f"{diff_pct:+.1f}%",
                    f"{preset_name} HH": f"{int(row_a['est_households']):,}",
                    f"{compare_preset_name} HH": f"{int(row_b['est_households']):,}",
                })

        if comp_table_rows:
            comp_table_df = pd.DataFrame(comp_table_rows)
            st.dataframe(comp_table_df, use_container_width=True, hide_index=True)

            # Download
            csv_comp = comp_table_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Comparison CSV",
                data=csv_comp,
                file_name=f"scenario_comparison_{selected_code}_{preset_name}_vs_{compare_preset_name}.csv",
                mime="text/csv",
                key="download_scenario_comparison",
            )


# ---- Tab 8: Data Tables ----
with tab_data:
    st.subheader("Projection Data")

    # Full projection table
    display_cols = ["year", "total", "youth", "working", "senior",
                    "dependency_ratio", "senior_share_pct", "est_households",
                    "change_from_base", "change_pct"]
    available = [c for c in display_cols if c in proj.columns]
    display_proj = proj[available].copy()
    display_proj.columns = [
        c.replace("_", " ").title()
        .replace("Pct", "%")
        .replace("Est ", "Est. ")
        for c in available
    ]

    st.dataframe(display_proj, use_container_width=True, hide_index=True)

    # Download button
    csv = proj.to_csv(index=False)
    st.download_button(
        label="📥 Download Projection CSV",
        data=csv,
        file_name=f"scenario_{selected_code}_{preset_name.lower()}_{end_year}.csv",
        mime="text/csv",
    )

    # Census history
    if not census_hist.empty:
        st.markdown("#### Historical Census Data")
        st.dataframe(census_hist, use_container_width=True, hide_index=True)

    # Methodology
    st.markdown("---")
    st.markdown("""
    #### Methodology Notes

    **Hamilton-Perry Method**: Population is projected by applying Cohort Change Ratios (CCRs) —
    derived from the ratio of each age band's population between the 2016 and 2021 Census — forward
    in 5-year steps. CCRs implicitly capture the combined effects of mortality, fertility, and net migration.

    **MOF Share-Capture**: Local projections are calibrated ("raked") so the community maintains its
    proportional share of the Ontario Ministry of Finance's Census Division population projection.
    This ensures defensibility for Official Plan reviews and Ontario Land Tribunal proceedings.

    **Limitations**:
    - Broad age bands (0-14, 15-64, 65+) reduce granularity compared to full 5-year cohort models
    - CCRs assume recent demographic trends persist; they cannot anticipate unprecedented events
    - Housing cap is a simple population ceiling; real housing-population dynamics are more complex
    - Seasonal populations are not captured in Census "usual place of residence" data

    **Sources**: Statistics Canada Census Profile (2016, 2021), Ontario Ministry of Finance Population
    Projections for Census Divisions (2024–2051).
    """)

from app.utils import global_footer
global_footer()
