import streamlit as st
import pandas as pd
from app.smart_read import smart_read
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import geopandas as gpd
from pathlib import Path
import json

# Setup page configuration
try:
    st.set_page_config(page_title="Ontario Farmland Values", page_icon="🗺️", layout="wide")
except Exception:
    pass # Might already be called by another page in multi-page structure

from app.utils import inject_standalone_mode
inject_standalone_mode()

st.title("🗺️ Ontario Farmland Values & Rents")
st.markdown("""
Explore 10 years of longitudinal data on agricultural real estate in Ontario. This dashboard 
tracks median cash rents, reported market values, and calculates the synthesized "Agricultural Value"
using the Income Capitalization Approach (Rent ÷ Cap Rate).

*Source Data:* [Ontario Farmland Value & Rental Value Survey (University of Guelph)](https://www.onfarmlandsurvey.com/)
""")

# Define paths
DATA_DIR = Path("data/surveys")
MASTER_CSV = DATA_DIR / "onfvrvs_master_valuation.csv"
BOUNDARY_FILE = Path("data/latest/wellbeing") / "ontario_csd_boundaries.geojson"
GEO_MAPPING_FILE = Path("data/latest/wellbeing") / "dim_geography.csv"

# ---------------------------------------------------------------------------
# Data Loading Core
# ---------------------------------------------------------------------------
@st.cache_data(max_entries=3, ttl=3600)
def load_valuation_data():
    if not MASTER_CSV.exists():
        return None
    df = smart_read(MASTER_CSV)
    # Ensure certain columns are numeric
    cols_to_numeric = [
        'median_cash_rent_per_acre', 'market_value_per_acre', 
        'rent_price_ratio_pct', 'pct_sales_to_farmers',
        'agricultural_value_per_acre', 'market_premium_pct'
    ]
    for c in cols_to_numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

@st.cache_data(max_entries=3, ttl=3600*24)
def load_geospatial_boundaries():
    """Load Ontario CSD boundaries and dissolve to county level (which aligns with our Regions)."""
    if not BOUNDARY_FILE.exists() or not GEO_MAPPING_FILE.exists():
        return None, None
        
    try:
        # Load the CSD boundaries
        gdf = gpd.read_file(BOUNDARY_FILE)
        gdf["sgc_code"] = gdf["sgc_code"].astype(str).str.zfill(7)
        # Extract county code (first 4 digits of 7-digit SGC)
        gdf["county_code"] = gdf["sgc_code"].str[:4]
        # Dissolve to county level
        county_gdf = gdf.dissolve(by="county_code", as_index=False)
        
        # Load geography mapping to get the names
        geo_df = smart_read(GEO_MAPPING_FILE)
        geo_df["sgc_code"] = geo_df["sgc_code"].astype(str).str.zfill(7)
        geo_df["county_code"] = geo_df["sgc_code"].str[:4]
        county_mapping = geo_df.drop_duplicates("county_code")[["county_code", "county"]].dropna()
        
        # Merge county names into the GeoDataFrame
        county_gdf = county_gdf.merge(county_mapping, on="county_code", how="left")
        
        # We also create a mapping dict for exact geo_name cleaning matching
        # ONFVRVS stripped "region" to actual county names.
        # Clean the dim_geography names slightly if needed
        county_gdf['geo_name'] = county_gdf['county'].str.replace('Greater Sudbury / Grand Sudbury', 'Greater Sudbury')
        
        return county_gdf
    except Exception as e:
        print(f"Error loading boundaries: {e}")
        return None

# Load data into memory
df = load_valuation_data()

if df is None or df.empty:
    st.error("Data not found. Please ensure `scripts/derive_farmland_valuations.py` has been executed.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar Filters & Constants
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Map Configuration")
    
    available_years = sorted(df['year'].unique().tolist(), reverse=True)
    selected_year = st.slider("Select Year", min_value=min(available_years), max_value=max(available_years), value=max(available_years))
    METRICS = {
        "median_cash_rent_per_acre": {"label": "Median Rent ($/acre)", "format": "${:,.0f}"},
        "agricultural_value_per_acre": {"label": "Agricultural Value (Income Cap) ($/acre)", "format": "${:,.0f}"},
        "market_value_per_acre": {"label": "Market Value (Reported) ($/acre)", "format": "${:,.0f}"},
        "market_premium_pct": {"label": "Market Premium over Ag Value (%)", "format": "{:,.1f}%"},
        "rent_price_ratio_pct": {"label": "Survey Ratio (Legacy / Raw) (%)", "format": "{:,.2f}%"},
        "pct_sales_to_farmers": {"label": "Sales to Farmers (%)", "format": "{:,.1f}%"}
    }
    
    selected_metric = st.selectbox(
        "Select Metric to Map",
        options=list(METRICS.keys()),
        format_func=lambda x: METRICS[x]["label"]
    )
    st.divider()
    st.subheader("Interactive Valuation Model")
    user_noi_deduction = st.slider("NOI Deduction (Taxes/Maintenance)", min_value=0, max_value=40, value=15, step=1,
                                  help="Percentage of gross rent deducted to calculate Net Operating Income (NOI). Covers landlord property taxes, insurance, and maintenance (e.g. tile drain amortized CapEx). Typical range: 10–25%.")
    user_risk_premium = st.slider("Agricultural Risk Premium", min_value=0.0, max_value=8.0, value=4.0, step=0.1,
                                 help="Additional yield demanded above the risk-free Bank of Canada 10-Yr Bond to compensate for agricultural production risk, illiquidity, and management burden.")
    user_growth_rate = st.slider("Expected Annual Rent Growth (g)", min_value=0.0, max_value=10.0, value=2.5, step=0.1,
                                help="Expected annual growth in cash rents and NOI—not capital appreciation. Ontario cash rents have historically grown 2–4% annually. Using capital appreciation rates here would double-count speculative gains.")
    
# ---------------------------------------------------------------------------
# Dynamic Model Recalculation
# ---------------------------------------------------------------------------
# Recalculate values "On-The-Fly" based on user slider inputs
if 'boc_10yr_yield' in df.columns:
    noi_factor = 1.0 - (user_noi_deduction / 100.0)
    df['calculated_cap_rate'] = df['boc_10yr_yield'] + user_risk_premium - user_growth_rate
    # Floor cap rate at 2.0% — minimum credible farmland cap rate
    # (prevents model instability when low BoC yields push the formula toward zero)
    df['calculated_cap_rate'] = df['calculated_cap_rate'].clip(lower=2.0)
    cap_rate_decimal = df['calculated_cap_rate'] / 100.0
    
    # Override Ag Value
    df['agricultural_value_per_acre'] = (df['median_cash_rent_per_acre'] * noi_factor) / cap_rate_decimal
    
    # Override Premium (Safe Division)
    safe_ag_val = df['agricultural_value_per_acre'].replace(0, np.nan)
    df['market_premium_pct'] = ((df['market_value_per_acre'] - safe_ag_val) / safe_ag_val) * 100

with st.expander("ℹ️ About the Income Capitalization Approach", expanded=False):
    st.markdown(f"""
    The **Agricultural Value** presented here is calculated using the Income Capitalization Approach—the cornerstone of agricultural economic valuation models. 
    
    $$ \\text{{Capitalization Rate}} = \\text{{BoC 10-Year Yield}} + \\text{{Risk Premium}} - \\text{{Rent Growth}} (g) $$
    
    To avoid the mathematical Circularity Trap of endogenous ratios, our engine derives a robust **Exogenous Capitalization Rate**. We map the historical Bank of Canada 10-Year Bond Yield for the given year and add a user-defined **{user_risk_premium}%** Agricultural Risk Premium to compensate for production risk, illiquidity, and management burden.
    
    **Critical distinction:** The growth rate (**g = {user_growth_rate}%**) represents expected annual growth in **cash rents and NOI**—not capital appreciation. Ontario cash rents have historically grown 2–4% annually, well below the 5–8% capital appreciation rates observed in FCC data. Using capital appreciation as *g* would bake speculative gains into the fundamental valuation, creating the exact circularity this tool is designed to avoid.
    
    We convert gross median cash rent into **Net Operating Income (NOI)** by deducting a **{user_noi_deduction}%** allowance for landlord property taxes, insurance, and maintenance (e.g. tile drain amortized CapEx).
    
    A **2.0% cap rate floor** is applied to prevent model instability in low interest rate environments (e.g. 2020), consistent with the minimum cap rates observed in North American agricultural appraisal practice.
    
    **Data Confidence:** Regions with survey sample sizes of N=10–19 are flagged as ⚠️ Low-N to signal reduced statistical reliability. Regions below N=10 are suppressed entirely.
    """)

# ---------------------------------------------------------------------------
# Top-Line Metrics 
# ---------------------------------------------------------------------------
df_year = df[df['year'] == selected_year]
df_prev = df[df['year'] == (selected_year - 1)]

col1, col2, col3, col4 = st.columns(4)

def stat_card(col, title, current, previous, is_currency=True, is_pct=False):
    if pd.isna(current):
        col.metric(title, "N/A", None)
        return
        
    v_str = f"${current:,.0f}" if is_currency else f"{current:,.2f}%" if is_pct else f"{current:,.1f}"
    
    delta = None
    if pd.notna(previous) and previous != 0:
        pct_change = ((current - previous) / previous)
        d_str = f"{pct_change * 100:,.1f}% YoY (Matched Sample)"
        delta = d_str
        
    col.metric(title, v_str, delta)

# Calculate medians/means for the specific year
cur_rent = df_year['median_cash_rent_per_acre'].median()
cur_val = df_year['market_value_per_acre'].median()
cur_ag_val = df_year['agricultural_value_per_acre'].median()
cur_cap = df_year['calculated_cap_rate'].median() if 'calculated_cap_rate' in df_year.columns else df_year['rent_price_ratio_pct'].median()

# For YoY calculations, only compare against counties that reported data in the CURRENT year
# This prevents survivorship bias (e.g. low-rent counties dropping out in 2025) from artificially inflating the median growth.
if not df_prev.empty:
    matched_counties = df_year.dropna(subset=['median_cash_rent_per_acre'])['geo_name'].unique()
    matched_prev_rent = df_prev[df_prev['geo_name'].isin(matched_counties)]
    prv_rent = matched_prev_rent['median_cash_rent_per_acre'].median() if not matched_prev_rent.empty else None
    
    matched_val_counties = df_year.dropna(subset=['market_value_per_acre'])['geo_name'].unique()
    matched_prev_val = df_prev[df_prev['geo_name'].isin(matched_val_counties)]
    prv_val = matched_prev_val['market_value_per_acre'].median() if not matched_prev_val.empty else None
    
    matched_ag_counties = df_year.dropna(subset=['agricultural_value_per_acre'])['geo_name'].unique()
    matched_prev_ag = df_prev[df_prev['geo_name'].isin(matched_ag_counties)]
    prv_ag_val = matched_prev_ag['agricultural_value_per_acre'].median() if not matched_prev_ag.empty else None
    
    matched_cap_counties = df_year.dropna(subset=['calculated_cap_rate' if 'calculated_cap_rate' in df_year.columns else 'rent_price_ratio_pct'])['geo_name'].unique()
    matched_prev_cap = df_prev[df_prev['geo_name'].isin(matched_cap_counties)]
    prv_cap = matched_prev_cap['calculated_cap_rate'].median() if 'calculated_cap_rate' in df_prev.columns else None
else:
    prv_rent = prv_val = prv_ag_val = prv_cap = None

stat_card(col1, "Provincial Median Rent", cur_rent, prv_rent, is_currency=True)
stat_card(col2, "Provincial Median Market Value", cur_val, prv_val, is_currency=True)
stat_card(col3, "Provincial Median Agricultural Value", cur_ag_val, prv_ag_val, is_currency=True)
stat_card(col4, "Provincial Median Cap Rate", cur_cap, prv_cap, is_currency=False, is_pct=True)

st.divider()

# ---------------------------------------------------------------------------
# Map Generation
# ---------------------------------------------------------------------------
st.subheader(f"Geospatial Analysis: {METRICS[selected_metric]['label']} ({selected_year})")

county_gdf = load_geospatial_boundaries()

if county_gdf is not None:
    # We must merge `df_year` with `county_gdf` based on `geo_name`
    # df_year['geo_name'] holds strings like 'Huron', 'Oxford', etc.
    
    # First, let's normalize names slightly to maximize mapping
    def safe_merge_name(x):
        if not isinstance(x, str): return ""
        # The GeoJSON has elements like "Haldimand-Norfolk" while survey might just have "Norfolk" or "Haldimand".
        # We'll just do a strict join for now.
        return x.lower()

    df_year_copy = df_year.copy()
    df_year_copy['join_key'] = df_year_copy['geo_name'].apply(safe_merge_name)
    
    county_gdf_copy = county_gdf.copy()
    county_gdf_copy['join_key'] = county_gdf_copy['geo_name'].apply(safe_merge_name)
    
    # Merge
    map_gdf = county_gdf_copy.merge(df_year_copy, on='join_key', how='left')
    
    # We DO NOT drop NaN values here because we want to map the entire province
    # to provide spatial context. Missing data regions will be colored gray.
    # map_gdf = map_gdf.dropna(subset=[selected_metric])
    
    if map_gdf.empty:
        st.warning("No data points mapped for this metric/year combination.")
    else:
        # Calculate global scale bounds across ALL years for an apples-to-apples color scale
        global_valid_vals = df[selected_metric].dropna()
        min_val = global_valid_vals.min() if not global_valid_vals.empty else 0
        max_val = global_valid_vals.max() if not global_valid_vals.empty else 0
        
        # Provide a scale function to determine polygon color
        def get_color(row):
            val = row.get(selected_metric)
            # Insufficient Data Protection: Gray out if very low N
            n_rent = row.get('rent_n', 0)
            n_price = row.get('price_n', 0)
            n_max = pd.to_numeric(max(n_rent if pd.notnull(n_rent) else 0, n_price if pd.notnull(n_price) else 0))
            
            if pd.isna(val) or n_max < 10: 
                return [150, 150, 150, 200] # Gray for missing OR insufficient data
                
            if max_val == min_val:
                ratio = 0.5
            else:
                ratio = (val - min_val) / (max_val - min_val)
            
            # Inverse scales for cap rate (higher cap rate = lower value relative to rent)
            if selected_metric == "rent_price_ratio_pct":
                ratio = 1 - ratio
                
            # Viridis-esque simple scaling from yellow to deep dark green
            r = int(255 * (1 - ratio))
            g = int(255 * (0.5 + 0.5 * ratio))
            b = int(255 * (0.2))
            
            # Low-N desaturation: blend toward gray for N=10-19 to signal reduced confidence
            if n_max < 20:
                gray = 170
                blend = 0.45  # 45% toward gray
                r = int(r + (gray - r) * blend)
                g = int(g + (gray - g) * blend)
                b = int(b + (gray - b) * blend)
                return [r, g, b, 160]  # Also slightly more transparent
            
            return [r, g, b, 200]

        map_gdf['color'] = map_gdf.apply(get_color, axis=1)
        
        # Format the display value right into the GeoDataFrame as a string
        fmt = METRICS[selected_metric]["format"]
        def format_display(row):
            val = row.get(selected_metric)
            if pd.isna(val): return "N/A"
            base_str = fmt.format(val)
            # Add top-coded + flag if present
            if row.get('is_top_coded', False) == True:
                base_str += "+"
            return base_str
            
        # PyDeck handles strings perfectly if pre-formatted
        map_gdf['display_value'] = map_gdf.apply(format_display, axis=1)
        
        # Format Sample Size string with confidence tiering
        def format_n(row):
            val = row.get(selected_metric)
            if pd.isna(val):
                return "No Survey Data"
            n_rent = row.get('rent_n', 0)
            n_price = row.get('price_n', 0)
            n = max(n_rent if pd.notnull(n_rent) else 0, n_price if pd.notnull(n_price) else 0)
            if n < 10:
                return f"N={int(n)} (Insufficient Data)"
            elif n < 20:
                return f"N={int(n)} ⚠️ Low sample size"
            return f"N={int(n)}"
            
        map_gdf['n_display'] = map_gdf.apply(format_n, axis=1)
            
        # Keep geo_name for tooltip
        map_gdf['display_name'] = map_gdf['geo_name_x'] # Original capitalized county
        
        # Convert to GeoJSON directly from Geopandas
        geojson = json.loads(map_gdf.to_json())
        
        layer = pdk.Layer(
            "GeoJsonLayer",
            geojson,
            opacity=0.8,
            stroked=True,
            filled=True,
            extruded=False,
            wireframe=True,
            get_fill_color="properties.color",
            get_line_color=[100, 100, 100, 200],  # Darker gray borders for clear visibility
            line_width_min_pixels=1,              # Force minimum border width
            pickable=True,
        )
        
        view_state = pdk.ViewState(
            longitude=-81.0, 
            latitude=44.0, 
            zoom=5.5, 
            min_zoom=4, 
            max_zoom=10
        )
        
        tooltip = {
            "html": "<b>{display_name}</b><br/>" + METRICS[selected_metric]["label"] + ": {display_value}<br/><small>{n_display}</small>",
            "style": {"backgroundColor": "steelblue", "color": "white"}
        }
        
        r = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="mapbox://styles/mapbox/light-v9")
        st.pydeck_chart(r, height=600)
else:
    st.info("PyDeck boundary maps not configured or available. Displaying charts only.")


# ---------------------------------------------------------------------------
# Longitudinal Data Charts
# ---------------------------------------------------------------------------
st.divider()
st.subheader("📈 Longitudinal Trends (2016-2025)")

counties = sorted(df['geo_name'].unique().tolist())
# Pre-select some interesting counties
default_counties = [c for c in ['Huron', 'Oxford', 'Perth', 'York', 'Renfrew'] if c in counties]
if not default_counties:
    default_counties = counties[:3]
    
selected_counties = st.multiselect("Select Counties to Compare", options=counties, default=default_counties[:3])

if selected_counties:
    plot_df = df[df['geo_name'].isin(selected_counties)].copy()
    
    chart_mode = st.radio(
        "Chart Mode",
        options=["📊 Indexed Growth (2016 = 100)", "💲 Absolute Values ($/acre)"],
        index=0,
        horizontal=True,
        help="Indexed Growth normalizes all series to a base year of 2016=100, making it easy to compare growth rates across metrics with different scales. Absolute Values shows raw $/acre."
    )
    
    chart_series = st.multiselect(
        "Select Series to Plot",
        options=["Market Value", "Median Rent", "Agricultural Value"],
        default=["Market Value", "Median Rent"],
        help="Choose which metrics to compare on the chart."
    )
    
    series_config = {
        "Market Value": {"col": "market_value_per_acre", "dash": "solid", "width": 3},
        "Median Rent": {"col": "median_cash_rent_per_acre", "dash": "dash", "width": 2},
        "Agricultural Value": {"col": "agricultural_value_per_acre", "dash": "dot", "width": 2},
    }
    
    fig = go.Figure()
    colors = px.colors.qualitative.Plotly
    
    BASE_YEAR = 2016
    
    for i, county in enumerate(selected_counties):
        cdf = plot_df[plot_df['geo_name'] == county].sort_values('year')
        color = colors[i % len(colors)]
        
        for series_name in chart_series:
            cfg = series_config[series_name]
            col = cfg["col"]
            
            if col not in cdf.columns:
                continue
            
            if chart_mode.startswith("📊"):
                # Indexed Growth: normalize to base year = 100
                base_row = cdf[cdf['year'] == BASE_YEAR]
                if base_row.empty or pd.isna(base_row[col].values[0]) or base_row[col].values[0] == 0:
                    # County doesn't have base year data — use earliest available year
                    valid = cdf.dropna(subset=[col])
                    valid = valid[valid[col] != 0]
                    if valid.empty:
                        continue
                    base_val = valid[col].values[0]
                    base_label = f" (base: {int(valid['year'].values[0])})"
                else:
                    base_val = base_row[col].values[0]
                    base_label = ""
                
                y_values = (cdf[col] / base_val) * 100
                y_title = "Index (Base Year = 100)"
                y_format = ".0f"
                name_suffix = f"{base_label}"
            else:
                # Absolute Values
                y_values = cdf[col]
                y_title = "Value ($/acre)"
                y_format = "$,.0f"
                name_suffix = ""
            
            fig.add_trace(go.Scatter(
                x=cdf['year'],
                y=y_values,
                name=f"{county} — {series_name}{name_suffix}",
                mode='lines+markers',
                line=dict(color=color, width=cfg["width"], dash=cfg["dash"]),
                marker=dict(size=6),
            ))
    
    # Add base-year reference line for indexed mode
    if chart_mode.startswith("📊"):
        fig.add_hline(
            y=100, line_dash="dash", line_color="rgba(128,128,128,0.4)", line_width=1,
            annotation_text=f"{BASE_YEAR} Baseline", annotation_position="bottom right",
            annotation_font_size=10, annotation_font_color="gray"
        )
    
    fig.update_layout(
        title="10-Year Farmland Economics: " + ("Indexed Growth" if chart_mode.startswith("📊") else "Absolute Values"),
        xaxis=dict(title="Year", tickmode='linear', dtick=1),
        yaxis=dict(
            title=dict(text=y_title),
            tickformat=y_format
        ),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        height=520,
        margin=dict(l=50, r=50, t=50, b=120)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    if chart_mode.startswith("📊"):
        st.caption(f"ℹ️ All series indexed to {BASE_YEAR} = 100. Counties without {BASE_YEAR} data use their earliest available year as the baseline (noted in legend). Divergence between Market Value and Rent indices reveals where speculative premiums have grown fastest.")

# ---------------------------------------------------------------------------
# Valuation Math Breakdown
# ---------------------------------------------------------------------------
if selected_counties:
    st.subheader(f"🧮 Step-by-Step Valuation ({selected_year})")
    st.markdown("See exactly how the agricultural value is calculated based on your current slider inputs.")
    
    tabs = st.tabs(selected_counties)
    
    for tab, county in zip(tabs, selected_counties):
        with tab:
            county_year_df = df[(df['geo_name'] == county) & (df['year'] == selected_year)]
            
            if not county_year_df.empty:
                row = county_year_df.iloc[0]
                rent = row.get('median_cash_rent_per_acre')
                market_val = row.get('market_value_per_acre')
                boc_yield = row.get('boc_10yr_yield')
                
                if pd.notna(rent) and pd.notna(boc_yield):
                    noi = rent * (1.0 - (user_noi_deduction / 100.0))
                    
                    raw_cap = boc_yield + user_risk_premium - user_growth_rate
                    cap_rate = max(raw_cap, 2.0)
                    
                    ag_val = noi / (cap_rate / 100.0)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("**1. Net Operating Income (NOI)**")
                        st.caption(f"Math: ${rent:,.0f} (Rent) × (1 - {user_noi_deduction/100:.2f}) (Deduction)")
                        st.metric(label="Calculated NOI", value=f"${noi:,.2f}")
                    with col2:
                        st.markdown("**2. Capitalization Rate**")
                        st.caption(f"Math: {boc_yield:.2f}% (BoC Yield) + {user_risk_premium:.2f}% (Risk) - {user_growth_rate:.2f}% (Growth)")
                        # Add floor warning if it was applied
                        if raw_cap < 2.0:
                            st.metric(label="Cap Rate (Floor Applied)", value=f"{cap_rate:.2f}%", delta="Raised to 2.0% minimum", delta_color="off")
                        else:
                            st.metric(label="Cap Rate", value=f"{cap_rate:.2f}%")
                    with col3:
                        st.markdown("**3. Agricultural Value**")
                        st.caption(f"Math: ${noi:,.2f} (NOI) ÷ {cap_rate/100:.4f} (Cap Rate)")
                        st.metric(label="Ag Value", value=f"${ag_val:,.0f}", delta=f"Market: ${market_val:,.0f}", delta_color="off")
                else:
                    st.warning(f"Insufficient data to show calculation for {county} in {selected_year}.")
            else:
                st.warning(f"No survey data available for {county} in {selected_year}.")

st.divider()

# ---------------------------------------------------------------------------
# Data Table
# ---------------------------------------------------------------------------
st.subheader("Raw Data Explorer")

fmt_dict = {
    'median_cash_rent_per_acre': '${:,.0f}',
    'market_value_per_acre': '${:,.0f}',
    'agricultural_value_per_acre': '${:,.0f}',
    'rent_price_ratio_pct': '{:.2f}%',
    'pct_sales_to_farmers': '{:.1f}%',
    'market_premium_pct': '{:.1f}%'
}


display_df = df.copy()

# Add data confidence column based on sample size tiering
def calc_confidence(row):
    n_rent = row.get('rent_n', 0)
    n_price = row.get('price_n', 0)
    n = max(n_rent if pd.notnull(n_rent) else 0, n_price if pd.notnull(n_price) else 0)
    if n < 10:
        return "⛔ Insufficient"
    elif n < 20:
        return "⚠️ Low-N"
    return "✓"

display_df['confidence'] = display_df.apply(calc_confidence, axis=1)

for col, f in fmt_dict.items():
    if col in display_df.columns:
        # Apply formatting but handle NaNs
        display_df[col] = display_df[col].apply(lambda x: f.format(x) if pd.notnull(x) else "N/A")

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=400
)

from app.utils import global_footer
global_footer()
