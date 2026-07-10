import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import altair as alt
import json
import pydeck as pdk
import geopandas as gpd

# --- PROJECT SETUP ---
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.smart_read import smart_read
from app.utils import inject_standalone_mode, make_line_chart, load_dataset, safe_load_dataset, get_table_metadata
from app.dataset_descriptions import DATASET_DESCRIPTIONS
from app.views.county_census_view import render_county_census_view
from app.analytics import AnalyticsOptions

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Agricultural Census", page_icon="📊", layout="wide")
inject_standalone_mode()

st.title("📊 Agricultural Census Data")
st.markdown("""
Welcome to the dedicated Agricultural Census explorer. This page aggregates key snapshots and historical 
trends from the Census of Agriculture to help you understand the changing landscape of farming.

*Use the tabs below to explore different themes.*
""")

# -----------------------------------------------------------------------------
# 2. DATA LOADERS (LAZY & CACHED)
# -----------------------------------------------------------------------------
# To prevent memory bloat, we strictly limit the number of cached DataFrames.
@st.cache_data(max_entries=4, show_spinner="Loading Census data...")
def load_census_table(table_id: str) -> pd.DataFrame:
    """Safely loads a StatCan census table and returns it."""
    try:
        # Always prefer lightning-fast Parquet if it exists
        parquet_path = project_root / "data" / "latest" / f"{table_id}.parquet"
        if parquet_path.exists():
            return smart_read(parquet_path)
            
        # Fallback to CSV
        csv_path = project_root / "data" / "latest" / f"{table_id}.csv"
        if csv_path.exists():
            return smart_read(csv_path)
            
        # Fallback to metadata lookup
        meta = get_table_metadata(table_id)
        if meta:
            return safe_load_dataset(meta)
            
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"Could not load table {table_id}: {e}")
        return pd.DataFrame()

def render_metric_header(table_id: str, title: str, default_metric: str = None):
    """Renders the descriptive header with dataset description."""
    st.subheader(title)
    desc = DATASET_DESCRIPTIONS.get(table_id, "Data from the Census of Agriculture.")
    st.info(f"**What is this?** {desc}")

def get_latest_year_and_total(df: pd.DataFrame, metric_col: str = "VALUE", geo_filter="Canada [") -> tuple:
    """Helper to get headline metric for Insights First strategy."""
    if df.empty or "YEAR" not in df.columns or "GEO" not in df.columns or metric_col not in df.columns:
        return None, None
    f = df[df["GEO"].str.startswith(geo_filter, na=False)]
    if f.empty:
        return None, None
    latest_year = f["YEAR"].max()
    total = f[f["YEAR"] == latest_year][metric_col].sum()
    return latest_year, total

# -----------------------------------------------------------------------------
# 3. THEMATIC TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🧑‍🌾 Who is Farming?",
    "💰 Farm Finances",
    "🚜 Farm Structure & Tech",
    "🗺️ County-Level Deep Dive",
    "🗄️ Master Data Explorer",
    "🔥 Heat Map Explorer"
])

# =============================================================================
# TAB 1: WHO IS FARMING?
# =============================================================================
with tab1:
    st.markdown("### Demographics & Organization")
    st.markdown("Explore how farms are structured legally and the workforce they employ.")
    
    # Legal Organization (32-10-0235-01)
    org_df = load_census_table("32-10-0235-01")
    if not org_df.empty and "YEAR" in org_df.columns:
        render_metric_header("32-10-0235-01", "Legal Organization of Farms")
        
        # Simple processing for chart
        org_df = org_df[org_df["GEO"].str.startswith("Canada [", na=False)].copy()
        if "Operating arrangement" in org_df.columns:
            chart_data = org_df.rename(columns={"VALUE": "Number of Farms", "Operating arrangement": "Category"})
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X("YEAR:O", title="Census Year"),
                y=alt.Y("Number of Farms:Q"),
                color=alt.Color("Category:N", legend=alt.Legend(orient="bottom", title="Organization Type")),
                tooltip=["YEAR", "Category", "Number of Farms"]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.dataframe(org_df.head())
    
    st.divider()
    
    # Paid Agricultural Workers (32-10-0243-01)
    workers_df = load_census_table("32-10-0243-01")
    if not workers_df.empty:
        render_metric_header("32-10-0243-01", "Paid Agricultural Workers")
        latest_yr, total_workers = get_latest_year_and_total(workers_df, "VALUE")
        if total_workers:
            st.metric(f"Total Paid Workers Reported in Canada ({latest_yr})", f"{total_workers:,.0f}")
        # Show breakdown by province for the latest year
        if "YEAR" in workers_df.columns and "GEO" in workers_df.columns:
            latest_yr = workers_df["YEAR"].max()
            prov_df = workers_df[(workers_df["YEAR"] == latest_yr) & (workers_df["GEO"].str.contains(r"\[PR", regex=True, na=False))]
            # Clean up the province names by stripping out the [PR...] part for a cleaner chart
            if not prov_df.empty:
                prov_df = prov_df.copy()
                prov_df["Clean_GEO"] = prov_df["GEO"].str.replace(r"\s*\[.*\]", "", regex=True)
                chart = alt.Chart(prov_df).mark_bar().encode(
                    x=alt.X("VALUE:Q", title="Number of Workers"),
                    y=alt.Y("Clean_GEO:N", sort="-x", title="Province"),
                    color=alt.Color("Clean_GEO:N", legend=None),
                    tooltip=["Clean_GEO", "VALUE"]
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)


# =============================================================================
# TAB 2: FARM FINANCES
# =============================================================================
with tab2:
    st.markdown("### Revenue, Expenses & Capital")
    
    # Revenue Brackets (32-10-0157-01)
    rev_df = load_census_table("32-10-0157-01")
    if not rev_df.empty and "YEAR" in rev_df.columns:
        render_metric_header("32-10-0157-01", "Distribution of Farms by Revenue Bracket")
        
        ca_rev = rev_df[rev_df["GEO"].str.startswith("Canada [", na=False)].copy()
        if "Farm receipts" in ca_rev.columns:
            chart_data = ca_rev.rename(columns={"VALUE": "Number of Farms", "Farm receipts": "Revenue Bracket"})
            chart = alt.Chart(chart_data).mark_line(point=True).encode(
                x=alt.X("YEAR:O", title="Census Year"),
                y=alt.Y("Number of Farms:Q"),
                color=alt.Color("Revenue Bracket:N", legend=alt.Legend(orient="bottom")),
                tooltip=["YEAR", "Revenue Bracket", "Number of Farms"]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
    
    st.divider()

    col1, col2 = st.columns(2)
    # Total Operating Revenues (32-10-0240-01)
    with col1:
        ops_rev_df = load_census_table("32-10-0240-01")
        if not ops_rev_df.empty:
            render_metric_header("32-10-0240-01", "Total Operating Revenues")
            yr, val = get_latest_year_and_total(ops_rev_df)
            if yr:
                st.metric(f"Total Operating Revenues ({yr})", f"${val:,.0f}")
                
    # Total Operating Expenses (32-10-0241-01)
    with col2:
        ops_exp_df = load_census_table("32-10-0241-01")
        if not ops_exp_df.empty:
            render_metric_header("32-10-0241-01", "Total Operating Expenses")
            yr, val = get_latest_year_and_total(ops_exp_df)
            if yr:
                st.metric(f"Total Operating Expenses ({yr})", f"${val:,.0f}")

    st.divider()
    
    # Farm Capital (32-10-0237-01)
    cap_df = load_census_table("32-10-0237-01")
    if not cap_df.empty:
        render_metric_header("32-10-0237-01", "Farm Capital Value")
        ca_cap = cap_df[cap_df["GEO"].str.startswith("Canada [", na=False)].copy()
        if "Farm capital" in ca_cap.columns:
            chart = alt.Chart(ca_cap).mark_bar().encode(
                x=alt.X("YEAR:O", title="Census Year"),
                y=alt.Y("VALUE:Q", title="Capital Value ($)"),
                color=alt.Color("Farm capital:N", legend=alt.Legend(orient="bottom")),
                tooltip=["YEAR", "Farm capital", "VALUE"]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)


# =============================================================================
# TAB 3: FARM STRUCTURE & TECH
# =============================================================================
with tab3:
    st.markdown("### Land, Machinery & Sales Channels")
    
    # Historical Farm Size / Acreage (32-10-0156-01)
    size_df = load_census_table("32-10-0156-01")
    if not size_df.empty and "YEAR" in size_df.columns:
        render_metric_header("32-10-0156-01", "Farm Size Distribution (Acreage)")
        ca_size = size_df[size_df["GEO"].str.startswith("Canada [", na=False)].copy()
        if "Size of area" in ca_size.columns:
            chart_data = ca_size.rename(columns={"VALUE": "Number of Farms", "Size of area": "Acreage Bracket"})
            chart = alt.Chart(chart_data).mark_line(point=True).encode(
                x=alt.X("YEAR:O", title="Census Year"),
                y=alt.Y("Number of Farms:Q"),
                color=alt.Color("Acreage Bracket:N", legend=alt.Legend(orient="bottom")),
                tooltip=["YEAR", "Acreage Bracket", "Number of Farms"]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
            
    st.divider()
    
    # Direct to Consumer Sales (32-10-0242-01)
    dtc_df = load_census_table("32-10-0242-01")
    if not dtc_df.empty:
        render_metric_header("32-10-0242-01", "Farms Selling Direct to Consumers")
        yr, val = get_latest_year_and_total(dtc_df)
        if yr:
            st.metric(f"Total Direct-to-Consumer Farms ({yr})", f"{val:,.0f}")
            
    st.divider()

    # Machinery Counts (32-10-0163-01)
    mach_df = load_census_table("32-10-0163-01")
    if not mach_df.empty and "YEAR" in mach_df.columns:
        render_metric_header("32-10-0163-01", "Historical Farm Machinery Counts")
        ca_mach = mach_df[mach_df["GEO"].str.startswith("Canada [", na=False)].copy()
        if "Farm machinery and equipment" in ca_mach.columns:
            # Filter to some core items to avoid a messy chart
            core_machinery = ca_mach[ca_mach["Farm machinery and equipment"].str.contains("Tractor|Combine", case=False, na=False)]
            if not core_machinery.empty:
                chart_data = core_machinery.rename(columns={"VALUE": "Count", "Farm machinery and equipment": "Machinery Type"})
                chart = alt.Chart(chart_data).mark_line().encode(
                    x=alt.X("YEAR:O", title="Census Year"),
                    y=alt.Y("Count:Q"),
                    color=alt.Color("Machinery Type:N", legend=alt.Legend(orient="bottom")),
                    tooltip=["YEAR", "Machinery Type", "Count"]
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)


# =============================================================================
# TAB 4: COUNTY-LEVEL DEEP DIVE
# =============================================================================
with tab4:
    st.markdown("### Granular Data for Ontario Counties")
    st.markdown("""
    Use the controls below to dive into Census Division (County) level data. 
    *Note: This view specifically isolates Ontario custom data extracts.*
    """)
    st.divider()
    
    # Create an empty analytics options class for the viewer
    analytics_opts = AnalyticsOptions(
        show_trendline=False,
        moving_average_window=None,
        highlight_outliers=False
    )
    
    # Call the existing county census view logic
    # It renders its own UI filters and charts
    try:
        render_county_census_view(params={}, analytics_options=analytics_opts)
    except Exception as e:
        st.error(f"Could not render the county-level view: {e}")


# =============================================================================
# TAB 5: MASTER DATA EXPLORER
# =============================================================================
with tab5:
    st.markdown("### 🗄️ Master Data Explorer")
    st.markdown("Access **every single data point** from all fetched Census of Agriculture datasets.")
    
    # 1. Discover available parquet files
    data_dir = project_root / "data" / "latest"
    if data_dir.exists():
        parquet_files = list(data_dir.glob("*.parquet"))
        csv_files = list(data_dir.glob("*.csv"))
        
        # Build a unique list of table IDs
        available_tables = set()
        for p in parquet_files:
            available_tables.add(p.stem)
        for c in csv_files:
            if c.stem not in ["manifest", "ontario_county_ceag"]: # skip non-tables
                available_tables.add(c.stem)
                
        available_tables = sorted(list(available_tables))
        
        if not available_tables:
            st.info("No datasets found in data/latest/")
        else:
            # 2. Let user select a table
            st.markdown("#### 1. Select a Dataset")
            
            def format_func(tid):
                desc = DATASET_DESCRIPTIONS.get(tid)
                if desc:
                    return f"{tid} - {desc[:80]}..."
                return tid
                
            selected_table = st.selectbox("Choose a Census Dataset:", available_tables, format_func=format_func)
            
            if selected_table:
                # 3. Load Data
                df = load_census_table(selected_table)
                
                if not df.empty:
                    st.success(f"Successfully loaded {len(df):,} rows and {len(df.columns)} columns.")
                    
                    st.markdown("#### 2. Filter Data")
                    # Auto-detect categorical columns for filtering (object/string type, < 1000 unique values)
                    # And exclude some common continuous/identifier ones
                    filter_cols = []
                    for col in df.columns:
                        if col not in ["VALUE", "YEAR"] and df[col].dtype == "object":
                            if df[col].nunique() < 1000: # allow generous limit for GEO
                                filter_cols.append(col)
                                
                    if filter_cols:
                        st.markdown("Use these dropdowns to slice the dataset. Leave blank to select all.")
                        cols = st.columns(min(len(filter_cols), 4))
                        filters = {}
                        for i, col in enumerate(filter_cols):
                            with cols[i % 4]:
                                unique_vals = sorted(df[col].dropna().astype(str).unique().tolist())
                                selected = st.multiselect(col, unique_vals)
                                if selected:
                                    filters[col] = selected
                                    
                        # Apply filters
                        filtered_df = df.copy()
                        for col, selected_vals in filters.items():
                            filtered_df = filtered_df[filtered_df[col].astype(str).isin(selected_vals)]
                            
                        st.markdown(f"**Showing {len(filtered_df):,} rows after filtering:**")
                        st.dataframe(filtered_df, use_container_width=True)
                        
                        st.markdown("#### 3. Quick Chart (Optional)")
                        with st.expander("Draw a chart from the filtered data"):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                x_axis = st.selectbox("X-Axis", filtered_df.columns, index=filtered_df.columns.get_loc("YEAR") if "YEAR" in filtered_df.columns else 0)
                            with c2:
                                y_axis = st.selectbox("Y-Axis", filtered_df.columns, index=filtered_df.columns.get_loc("VALUE") if "VALUE" in filtered_df.columns else 0)
                            with c3:
                                color_axis = st.selectbox("Color By (Optional)", ["None"] + list(filtered_df.columns))
                                
                            if st.button("Generate Chart"):
                                if color_axis != "None":
                                    chart = alt.Chart(filtered_df).mark_line(point=True).encode(
                                        x=alt.X(f"{x_axis}:O" if filtered_df[x_axis].dtype == 'object' else f"{x_axis}:Q"),
                                        y=alt.Y(f"{y_axis}:Q"),
                                        color=alt.Color(f"{color_axis}:N", legend=alt.Legend(orient="bottom")),
                                        tooltip=[x_axis, y_axis, color_axis]
                                    ).properties(height=500)
                                else:
                                    chart = alt.Chart(filtered_df).mark_bar().encode(
                                        x=alt.X(f"{x_axis}:O" if filtered_df[x_axis].dtype == 'object' else f"{x_axis}:Q"),
                                        y=alt.Y(f"{y_axis}:Q"),
                                        tooltip=[x_axis, y_axis]
                                    ).properties(height=500)
                                st.altair_chart(chart, use_container_width=True)
                    else:
                        st.dataframe(df, use_container_width=True)
                else:
                    st.warning("Selected dataset returned no data.")
    else:
        st.error("Data directory not found. Please run the fetch scripts.")


# =============================================================================
# TAB 6: HEAT MAP EXPLORER
# =============================================================================
with tab6:
    st.markdown("### 🔥 Heat Map Explorer")
    st.markdown("Visualize 240+ Agricultural Census metrics across Ontario counties.")
    
    GEO_JSON_PATH = project_root / "data" / "latest" / "wellbeing" / "ontario_csd_boundaries.geojson"
    DIM_GEO_PATH = project_root / "data" / "latest" / "wellbeing" / "dim_geography.csv"
    CEAG_PATH = project_root / "data" / "latest" / "ontario_county_ceag.csv"
    
    @st.cache_data(max_entries=1)
    def load_ceag_map_data():
        if not CEAG_PATH.exists() or not GEO_JSON_PATH.exists() or not DIM_GEO_PATH.exists():
            return None, None
            
        ceag_df = pd.read_csv(CEAG_PATH)
        ceag_df['YEAR'] = pd.to_numeric(ceag_df['YEAR'], errors='coerce')
        
        gdf = gpd.read_file(GEO_JSON_PATH)
        gdf["sgc_code"] = gdf["sgc_code"].astype(str).str.zfill(7)
        gdf["county_code"] = gdf["sgc_code"].str[:4]
        county_gdf = gdf.dissolve(by="county_code", as_index=False)
        
        dim_geo = pd.read_csv(DIM_GEO_PATH)
        dim_geo["sgc_code"] = dim_geo["sgc_code"].astype(str).str.zfill(7)
        dim_geo["county_code"] = dim_geo["sgc_code"].str[:4]
        county_mapping = dim_geo.drop_duplicates("county_code")[["county_code", "county"]].dropna()
        
        county_gdf = county_gdf.merge(county_mapping, on="county_code", how="left")
        
        def format_ceag_geo(name):
            if not isinstance(name, str): return ""
            return name.replace("-", "_").lower()
            
        def format_gdf_geo(name):
            if not isinstance(name, str): return ""
            name = name.lower().replace("-", "_").replace(" ", "_")
            if "stormont" in name and "dundas" in name: return "stormont"
            if "haldimand" in name and "norfolk" in name: return "haldimand_norfolk"
            if "leeds" in name and "grenville" in name: return "leeds_and_grenville"
            if "prescott" in name and "russell" in name: return "prescott_and_russell"
            if "sudbury" in name and "greater" in name: return "greater_sudbury"
            return name
            
        ceag_df['join_key'] = ceag_df['GEO'].apply(format_ceag_geo)
        county_gdf['join_key'] = county_gdf['county'].apply(format_gdf_geo)
        
        return ceag_df, county_gdf
        
    ceag_df, county_gdf = load_ceag_map_data()
    
    if ceag_df is not None and county_gdf is not None:
        years = sorted(ceag_df['YEAR'].dropna().unique().tolist(), reverse=True)
        exclude_cols = ['YEAR', 'GEO', 'REF_DATE', 'join_key']
        metrics = [c for c in ceag_df.columns if c not in exclude_cols and pd.api.types.is_numeric_dtype(ceag_df[c])]
        
        col1, col2 = st.columns([1, 3])
        with col1:
            selected_year = st.selectbox("Select Census Year", years, index=0)
        with col2:
            selected_metric = st.selectbox("Select Metric to Map", metrics, index=0)
            
        normalize = st.checkbox("Normalize per Total Farm Area (Acres)", value=False)
            
        df_year = ceag_df[ceag_df['YEAR'] == selected_year].copy()
        
        if normalize:
            area_col = next((c for c in metrics if 'Total farm area' in c and 'Acres' in c), None)
            if area_col and selected_metric != area_col:
                df_year[selected_metric] = df_year[selected_metric] / df_year[area_col].replace(0, pd.NA)
                st.caption(f"Showing **{selected_metric}** divided by **{area_col}**.")
            elif not area_col:
                st.warning("Total farm area metric not found for normalization.")
                
        map_gdf = county_gdf.merge(df_year, on='join_key', how='inner')
        
        if not map_gdf.empty:
            valid_vals = map_gdf[selected_metric].dropna()
            min_val = valid_vals.min() if not valid_vals.empty else 0
            max_val = valid_vals.max() if not valid_vals.empty else 0
            
            def get_color(row):
                val = row.get(selected_metric)
                if pd.isna(val) or max_val == min_val:
                    return [150, 150, 150, 150] # Grey for missing data
                ratio = (val - min_val) / (max_val - min_val)
                r = int(255 * (1 - ratio))
                g = int(255 * (0.5 + 0.5 * ratio))
                b = int(255 * 0.2)
                return [r, g, b, 200]
                
            map_gdf['color'] = map_gdf.apply(get_color, axis=1)
            map_gdf['display_value'] = map_gdf[selected_metric].apply(lambda x: f"{x:,.2f}" if pd.notna(x) and isinstance(x, (int, float)) else "Data Suppressed/Missing")
            
            geojson_str = map_gdf.to_json()
            geojson_data = json.loads(geojson_str)
            
            layer = pdk.Layer(
                "GeoJsonLayer",
                geojson_data,
                opacity=0.8,
                stroked=True,
                filled=True,
                wireframe=True,
                get_fill_color="properties.color",
                get_line_color=[255, 255, 255],
                pickable=True,
            )
            
            view_state = pdk.ViewState(longitude=-81.0, latitude=44.0, zoom=5.0, min_zoom=4, max_zoom=10)
            tooltip = {
                "html": "<b>{county}</b><br/>" + selected_metric + ": {display_value}",
                "style": {"backgroundColor": "steelblue", "color": "white"}
            }
            
            r = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="mapbox://styles/mapbox/light-v9")
            st.pydeck_chart(r, height=600)
            
            st.markdown("#### Raw Data")
            display_cols = ['county', selected_metric]
            st.dataframe(map_gdf[display_cols].sort_values(selected_metric, ascending=False).reset_index(drop=True), use_container_width=True)
            
        else:
            st.warning("No data available for the selected metric and year.")
    else:
        st.error("Could not load CEAG data or boundary files.")


from app.utils import global_footer
global_footer()
