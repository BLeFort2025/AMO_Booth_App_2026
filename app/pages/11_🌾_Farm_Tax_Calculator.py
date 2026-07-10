"""
Farm Tax Calculator — Standalone Page
======================================
Direct-access version of the Farm Tax Story tool for OFA field staff.
Identical functionality to the Farmland Taxation tab in Rural Community Data,
but accessible via its own shareable URL without navigating the full dashboard.
"""

import sys
from pathlib import Path

# ── Project setup ── must run BEFORE any app.* or farm_tax.* imports ──────────
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]          # app/pages/ → app/ → project root
app_dir = current_file.parents[1]               # app/pages/ → app/
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

import numpy as np
import pandas as pd
import streamlit as st
from app.smart_read import smart_read
from farm_tax.farm_tax_story import render_farm_tax_story

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Farm Tax Calculator — OFA",
    page_icon="🌾",
    layout="wide",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .farm-tax-header {
        background: linear-gradient(135deg, #1b5e20 0%, #43a047 100%);
        padding: 1.8rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .farm-tax-header h1 {
        color: white;
        margin: 0;
        font-size: 1.8rem;
    }
    .farm-tax-header p {
        color: #c8e6c9;
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)

from app.utils import inject_theme_css
inject_theme_css()

import streamlit.components.v1 as components

# Hide Streamlit navigation (but keep sidebar controls) when ?standalone=true is in URL
# We use client-side JavaScript to ensure it works regardless of Streamlit backend caching/routing quirks.
components.html(
    """
    <script>
        // Read the query parameters from the parent window (the main Streamlit app)
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (urlParams.get('standalone') === 'true') {
            // Inject CSS directly into the parent document's head
            const style = window.parent.document.createElement('style');
            style.innerHTML = `
                /* Broadly hide the page navigation list */
                [data-testid="stSidebarNav"] { display: none !important; }
                div[data-testid="stSidebarNav"] { display: none !important; }
                
                /* Hide the top header bar */
                header[data-testid="stHeader"] { display: none !important; }
                
                /* Compensate for missing header padding */
                .block-container { padding-top: 2rem !important; }
            `;
            window.parent.document.head.appendChild(style);
        }
    </script>
    """,
    height=0,
    width=0,
)

st.markdown("""
<div class="farm-tax-header">
    <h1>🌾 Farm Tax Calculator</h1>
    <p>Revenue-neutral farm tax ratio analysis using Ontario Financial Information Return (FIR) data</p>
</div>
""", unsafe_allow_html=True)


# ── Data loading ─────────────────────────────────────────────────────────────
DERIVED_DIR = Path("data/derived")
FIR_FILE = DERIVED_DIR / "fir_indicators.csv"
GEO_FILE = Path("data/latest/wellbeing") / "dim_geography.csv"


@st.cache_data(max_entries=3, ttl=1800)
def load_fir_wide():
    """Load FIR data in wide format (one row per municipality-year)."""
    if not FIR_FILE.exists():
        return pd.DataFrame()
    fir = smart_read(FIR_FILE)
    if "sgc_code" not in fir.columns:
        return pd.DataFrame()
    fir["sgc_code"] = pd.to_numeric(fir["sgc_code"], errors="coerce")
    fir = fir.dropna(subset=["sgc_code"])
    fir["sgc_code"] = fir["sgc_code"].astype(int).astype(str).str.zfill(7)
    fir = fir[fir["sgc_code"].str.startswith("35")].copy()
    return fir


PROVINCIAL_CODE = "PROVINCE"
PROVINCIAL_NAME = "🌾 All Ontario (Provincial)"

_PROV_AGG_COLS = {
    "farmland_cva": "sum", "residential_cva": "sum",
    "commercial_cva": "sum", "industrial_cva": "sum",
    "total_taxable_cva": "sum",
    "farmland_muni_taxes": "sum", "farmland_edu_taxes": "sum",
    "farmland_total_taxes": "sum",
    "residential_muni_taxes": "sum", "commercial_muni_taxes": "sum",
    "industrial_muni_taxes": "sum",
    "total_muni_taxes": "sum", "total_taxes": "sum",
    "total_households": "sum",
}


@st.cache_data(max_entries=3, ttl=1800)
def build_provincial_aggregate(fir_df):
    """Aggregate FIR data province-wide with ffill LOCF imputation.

    Uses only lower/single-tier rows to avoid double-counting CVA and taxes
    with upper-tier entries. Late-filing municipalities are forward-filled
    from their last known year to prevent artificial data cliffs.
    """
    non_upper = fir_df[fir_df["tier"] != "upper"].copy()

    # ── Panel LOCF imputation (red-team approved ffill approach) ──────────
    all_years = range(int(non_upper["year"].min()), int(non_upper["year"].max()) + 1)
    all_codes = non_upper["sgc_code"].unique()
    idx = pd.MultiIndex.from_product([all_codes, all_years], names=["sgc_code", "year"])

    panel = non_upper.set_index(["sgc_code", "year"]).reindex(idx)
    panel["_imputed"] = panel["farmland_cva"].isna()
    panel = panel.groupby(level="sgc_code").ffill().reset_index()
    panel = panel.dropna(subset=["farmland_cva"])

    # ── Aggregate by year ─────────────────────────────────────────────────
    agg_spec = {col: func for col, func in _PROV_AGG_COLS.items() if col in panel.columns}
    agg_spec["_imputed"] = "sum"  # count of imputed rows
    agg = panel.groupby("year").agg(**{k: (k, v) for k, v in agg_spec.items()}).reset_index()
    agg["n_filed"] = panel.groupby("year").size().values
    agg.rename(columns={"_imputed": "n_imputed"}, inplace=True)

    # ── Derived metrics ───────────────────────────────────────────────────
    agg["farmland_share_of_taxes"] = agg["farmland_muni_taxes"] / agg["total_muni_taxes"]
    agg["farmland_share_of_total_taxes"] = agg["farmland_total_taxes"] / agg["total_taxes"]

    # Effective Provincial Farm Tax Ratio (C3)
    # Use CVA-weighted average of individual municipality ratios, NOT the
    # rate-quotient formula (Σ farm_taxes/Σ farm_cva) / (Σ res_taxes/Σ res_cva).
    # The rate-quotient is invalidated by Simpson's Paradox: large cities like
    # Toronto/Ottawa have massive res CVA but negligible farmland, pulling the
    # aggregate res_rate down and inflating the quotient above the legal max.
    ratio_valid = panel[(panel["farmland_cva"] > 0) & (panel["farmland_tax_ratio"].notna())]
    weighted_ratio = (
        ratio_valid.groupby("year")
        .apply(lambda g: (g["farmland_tax_ratio"] * g["farmland_cva"]).sum() / g["farmland_cva"].sum(),
               include_groups=False)
        .reset_index(name="effective_provincial_ratio")
    )
    agg = agg.merge(weighted_ratio, on="year", how="left")

    # CVA share metric (R3)
    agg["farmland_cva_share"] = agg["farmland_cva"] / agg["total_taxable_cva"]

    # Metadata columns for compatibility with story module
    agg["municipality_name"] = PROVINCIAL_NAME
    agg["sgc_code"] = PROVINCIAL_CODE
    agg["tier"] = "provincial"
    agg["total_ut_taxes"] = 0  # prevents two-tier detection

    return agg


@st.cache_data(max_entries=3, ttl=1800)
def simulate_mandated_ratio(fir_df, mandated_ratio: float):
    """Simulate province-wide impact of a mandated farm tax ratio.

    For each municipality where current ratio > mandated_ratio, computes:
    - Farm tax savings using True W / Model-vs-Model approach
    - Redistribution to residential, commercial, industrial classes

    Revenue-neutral per municipality (respects ring-fenced tax pools).
    """
    latest = fir_df.sort_values("year").drop_duplicates("sgc_code", keep="last")

    # Filter to municipalities with valid ratio data
    valid = latest[
        (latest["farmland_tax_ratio"].notna())
        & (latest["farmland_tax_ratio"] > 0)
        & (latest["residential_cva"].notna())
        & (latest["residential_cva"] > 0)
        & (latest["residential_muni_taxes"].notna())
        & (latest["residential_muni_taxes"] > 0)
        & (latest["total_muni_taxes"].notna())
        & (latest["total_muni_taxes"] > 0)
        & (latest["farmland_cva"].notna())
        & (latest["farmland_cva"] > 0)
    ].copy()

    # Only affect municipalities ABOVE the mandated ratio
    affected = valid[valid["farmland_tax_ratio"] > mandated_ratio].copy()
    unaffected = valid[valid["farmland_tax_ratio"] <= mandated_ratio]

    if affected.empty:
        return {
            "n_affected": 0, "n_unaffected": len(unaffected),
            "farm_savings_total": 0, "res_increase_total": 0,
            "com_increase_total": 0, "ind_increase_total": 0,
            "other_increase_total": 0,
            "avg_res_per_household": 0,
            "affected_details": pd.DataFrame(),
        }

    # ── True W approach per municipality (vectorized) ──
    # Derive actual residential base rate
    a = affected
    a["res_rate"] = a["residential_muni_taxes"] / a["residential_cva"]
    a["true_W"] = a["total_muni_taxes"] / a["res_rate"]

    # Old model farm taxes (per True W)
    a["model_farm_old"] = a["farmland_tax_ratio"] * a["res_rate"] * a["farmland_cva"]

    # New True W with mandated ratio
    a["new_W"] = a["true_W"] - a["farmland_cva"] * (a["farmland_tax_ratio"] - mandated_ratio)
    a["new_res_rate"] = a["total_muni_taxes"] / a["new_W"]

    # New model farm taxes
    a["model_farm_new"] = mandated_ratio * a["new_res_rate"] * a["farmland_cva"]
    a["farm_savings"] = a["model_farm_old"] - a["model_farm_new"]

    # Increases by class (model-vs-model)
    a["model_res_old"] = a["res_rate"] * a["residential_cva"]
    a["model_res_new"] = a["new_res_rate"] * a["residential_cva"]
    a["res_increase"] = a["model_res_new"] - a["model_res_old"]

    com_ratio = a["commercial_tax_ratio"].fillna(0)
    a["com_increase"] = np.where(
        com_ratio > 0,
        com_ratio * (a["new_res_rate"] - a["res_rate"]) * a["commercial_cva"].fillna(0),
        0,
    )

    ind_ratio = a["industrial_tax_ratio"].fillna(0)
    a["ind_increase"] = np.where(
        ind_ratio > 0,
        ind_ratio * (a["new_res_rate"] - a["res_rate"]) * a["industrial_cva"].fillna(0),
        0,
    )

    # Other increase = farm_savings - res - com - ind (guarantees zero-sum)
    a["other_increase"] = a["farm_savings"] - a["res_increase"] - a["com_increase"] - a["ind_increase"]

    # Per-household impact
    total_hh = a["total_households"].sum()
    res_increase_total = a["res_increase"].sum()
    avg_per_hh = res_increase_total / total_hh if total_hh > 0 else 0

    return {
        "n_affected": len(a),
        "n_unaffected": len(unaffected),
        "n_total": len(valid),
        "current_weighted_ratio": (valid["farmland_tax_ratio"] * valid["farmland_cva"]).sum() / valid["farmland_cva"].sum(),
        "mandated_ratio": mandated_ratio,
        "farm_savings_total": a["farm_savings"].sum(),
        "res_increase_total": res_increase_total,
        "com_increase_total": a["com_increase"].sum(),
        "ind_increase_total": a["ind_increase"].sum(),
        "other_increase_total": a["other_increase"].sum(),
        "avg_res_per_household": avg_per_hh,
        "avg_res_per_household_month": avg_per_hh / 12,
        "total_households_affected": total_hh,
        "affected_details": a[["municipality_name", "farmland_tax_ratio", "farm_savings",
                                "res_increase", "total_households"]].copy(),
    }


def _normalize_upper_tier_name(name: str) -> str:
    """Normalize county/region names for professional display (V46)."""
    import re
    # UCo → United Counties, Co → County, R → Region, D → District
    name = re.sub(r'\bUCo$', 'United Counties', name)
    name = re.sub(r'\bCo$', 'County', name)
    name = re.sub(r'\bR$', 'Region', name)
    name = re.sub(r'\bD$', 'District', name)
    return name


@st.cache_data(max_entries=3, ttl=1800)
def build_muni_lookup(fir_df):
    """Build municipality name lookup from FIR data, enriched with county from geo table if available."""
    # Start from FIR municipality_name column
    latest = fir_df.sort_values("year").drop_duplicates("sgc_code", keep="last")
    lookup = dict(zip(latest["sgc_code"], latest["municipality_name"]))

    # Build tier lookup (V35/V38: distinguish upper-tier entries)
    tier_lookup = {}
    if "tier" in latest.columns:
        tier_lookup = dict(zip(latest["sgc_code"], latest["tier"]))

    # Try to enrich with county name from dim_geography.csv
    if GEO_FILE.exists():
        geo = smart_read(GEO_FILE)
        if "sgc_code" in geo.columns and "county" in geo.columns:
            geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)
            county_map = dict(zip(geo["sgc_code"], geo["county"]))
            enriched = {}
            for code, name in lookup.items():
                county = county_map.get(code)
                if county and pd.notna(county) and str(county).strip():
                    enriched[code] = f"{name} ({county})"
                else:
                    enriched[code] = name
            lookup = enriched

    # V38: Prefix upper-tier entries with 🏛️ icon and normalize names (V46)
    for code, name in lookup.items():
        if tier_lookup.get(code) == "upper":
            normalized = _normalize_upper_tier_name(name)
            lookup[code] = f"🏛️ {normalized} [Upper-Tier]"

    return lookup, tier_lookup


# Load data
fir_wide = load_fir_wide()

if fir_wide.empty:
    st.error(
        "⚠️ No FIR data available. Please ensure the FIR ETL pipeline has been "
        "run and `data/derived/fir_indicators.csv` exists."
    )
    st.stop()

muni_lookup, tier_lookup = build_muni_lookup(fir_wide)

# ── Sidebar: Municipality selector ───────────────────────────────────────────
with st.sidebar:
    st.header("🏘️ Select Municipality")
    st.caption(
        "Type a name below to search, or scroll to browse. "
        "Only municipalities with farmland CVA data are shown."
    )

    # Only show municipalities that have farmland data
    munis_with_farm = fir_wide[fir_wide["farmland_cva"].notna() & (fir_wide["farmland_cva"] > 0)]
    valid_codes = set(munis_with_farm["sgc_code"].unique())
    filtered_lookup = {k: v for k, v in muni_lookup.items() if k in valid_codes}

    # Sort by display name, then prepend provincial option
    options_sorted = sorted(filtered_lookup.items(), key=lambda x: x[1])
    option_names = [PROVINCIAL_NAME] + [name for _, name in options_sorted]
    option_codes = [PROVINCIAL_CODE] + [code for code, _ in options_sorted]

    # Default to a well-known rural municipality if available
    default_idx = 0
    for i, name in enumerate(option_names):
        if "Zorra" in name:
            default_idx = i
            break

    selected_name = st.selectbox(
        "🔎 Municipality",
        options=option_names,
        index=default_idx,
        help="Start typing a municipality name to filter the list",
    )

    # Resolve code
    idx = option_names.index(selected_name)
    selected_code = option_codes[idx]
    is_provincial = selected_code == PROVINCIAL_CODE

    st.divider()
    st.metric("Municipalities with Farm Data", f"{len(filtered_lookup):,}")
    st.caption(
        f"Data range: {int(fir_wide['year'].min())}–{int(fir_wide['year'].max())}"
    )

    st.divider()
    if is_provincial:
        st.caption(
            "**Source:** Ontario Financial Information Return (FIR)  \n"
            "Provincial view includes municipal **and** education taxes."
        )
    else:
        st.caption(
            "**Source:** Ontario Financial Information Return (FIR)  \n"
            "Municipal taxes only (excluding provincial education levy)."
        )


# ── Identify municipalities with farm tax ratio below 0.25 ───────────────────
# In two-tier systems, all constituent lower-tier municipalities share the
# county's ratio. When highlighted on the CSD boundary map, they visually
# "fill in" the county/region shape — giving the user a county-level view
# without needing a separate upper-tier boundary file.

@st.cache_data(max_entries=3, ttl=1800)
def get_below_max_ratio_codes(_fir_df):
    """Return set of sgc_codes where farmland_tax_ratio < 0.25 (latest year)."""
    latest = _fir_df.sort_values("year").drop_duplicates("sgc_code", keep="last")
    below = latest[
        (latest["farmland_tax_ratio"].notna())
        & (latest["farmland_tax_ratio"] > 0)
        & (latest["farmland_tax_ratio"] < 0.25)
    ]
    return set(below["sgc_code"].unique())

below_max_codes = get_below_max_ratio_codes(fir_wide)


# ── Ontario Municipality Map ─────────────────────────────────────────────────
BOUNDARY_FILE = Path("data/latest/wellbeing") / "ontario_csd_boundaries.geojson"

try:
    import pydeck as pdk
    HAS_PYDECK = True
except ImportError:
    HAS_PYDECK = False


@st.cache_data(max_entries=3, ttl=3600)
def load_boundaries():
    """Load Ontario CSD boundary GeoJSON for the map."""
    if not BOUNDARY_FILE.exists():
        return None
    import geopandas as gpd
    gdf = gpd.read_file(BOUNDARY_FILE)
    gdf["sgc_code"] = gdf["sgc_code"].astype(str).str.zfill(7)
    return gdf


boundaries_gdf = load_boundaries()

if not is_provincial and boundaries_gdf is not None and HAS_PYDECK:
    st.markdown("---")

    # Map header + ratio highlight checkbox
    map_header_cols = st.columns([3, 2])
    with map_header_cols[0]:
        st.subheader("🗺️ Selected Municipality")
    with map_header_cols[1]:
        show_below_025 = st.checkbox(
            "Show ratio < 0.25",
            value=False,
            help=(
                "Highlight municipalities where the farm tax ratio is below "
                "the provincial maximum (0.25). In two-tier systems, all "
                "lower-tier municipalities share the county ratio, so the "
                "entire county will be highlighted."
            ),
            key="show_ratio_below_025",
        )

    map_gdf = boundaries_gdf.copy()

    # Add display name + ratio info for tooltip
    latest_ratios = (
        fir_wide.sort_values("year")
        .drop_duplicates("sgc_code", keep="last")
        .set_index("sgc_code")["farmland_tax_ratio"]
    )
    map_gdf["display_name"] = map_gdf["sgc_code"].map(
        lambda c: muni_lookup.get(c, c)
    )
    map_gdf["farm_ratio"] = map_gdf["sgc_code"].map(latest_ratios).fillna(0)
    map_gdf["ratio_label"] = map_gdf["farm_ratio"].apply(
        lambda r: f"{r:.4f}" if r > 0 else "N/A"
    )

    # Build fill colors
    def _base_fill(row):
        code = row["sgc_code"]
        if code == selected_code:
            return [46, 125, 50, 200]    # OFA green for selected
        elif show_below_025 and code in below_max_codes:
            return [173, 216, 230, 160]  # Light blue tint for below-max ratio
        elif code in valid_codes:
            return [200, 230, 200, 120]  # Light green for farm municipalities
        else:
            return [220, 220, 220, 80]   # Grey for non-farm

    map_gdf["fill_color"] = map_gdf.apply(_base_fill, axis=1)

    # Build border colors and widths
    def _line_color(row):
        code = row["sgc_code"]
        if code == selected_code:
            return [255, 165, 0, 255]     # Orange border for selected
        elif show_below_025 and code in below_max_codes:
            return [30, 80, 180, 220]     # Blue border for ratio < 0.25
        else:
            return [0, 0, 0, 30]

    def _line_width(row):
        code = row["sgc_code"]
        if code == selected_code:
            return 4
        elif show_below_025 and code in below_max_codes:
            return 2
        else:
            return 0

    map_gdf["line_color"] = map_gdf.apply(_line_color, axis=1)
    map_gdf["line_width"] = map_gdf.apply(_line_width, axis=1)

    # Convert to GeoJSON for pydeck
    geojson_data = map_gdf.__geo_interface__

    # Centre on Southern Ontario
    view_state = pdk.ViewState(
        latitude=44.0,
        longitude=-80.0,
        zoom=5.8,
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
        line_width_min_pixels=0,
        line_width_scale=500,
        auto_highlight=True,
        highlight_color=[255, 200, 0, 100],
    )

    # Tooltip shows name + ratio when ratio overlay is on
    if show_below_025:
        tooltip_html = "<b>{display_name}</b><br/>Farm ratio: {ratio_label}"
    else:
        tooltip_html = "<b>{display_name}</b>"

    tooltip = {
        "html": tooltip_html,
        "style": {
            "backgroundColor": "#1b5e20",
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

    st.pydeck_chart(deck, height=450)

    # Dynamic legend
    legend_items = [
        "■ <span style='color:#2E7D32'><b>Selected</b></span>",
        "■ <span style='color:#ffa500'>Orange border</span> = selected",
    ]
    if show_below_025:
        legend_items.append(
            "■ <span style='color:#1E50B4'><b>Blue border</b></span> = ratio &lt; 0.25"
        )
        legend_items.append(
            "■ <span style='color:#add8e6'>Light blue</span> = ratio &lt; 0.25"
        )
    legend_items.extend([
        "■ <span style='color:#b0d8b0'>Has farm data</span>",
        "■ <span style='color:#c8c8c8'>No farm data</span>",
    ])

    st.markdown(
        "<div style='display:flex; flex-wrap:wrap; align-items:center; gap:16px; margin:8px 0; font-size:0.85rem; color:var(--text-color); opacity: 0.8;'>"
        + "".join(f"<span>{item}</span>" for item in legend_items)
        + "</div>",
        unsafe_allow_html=True,
    )

    if show_below_025:
        st.caption(
            f"ℹ️ **{len(below_max_codes)}** municipalities currently have a farm "
            f"tax ratio below the provincial maximum of 0.25. In two-tier systems, "
            f"all lower-tier municipalities share the county ratio — so entire "
            f"counties/regions are highlighted."
        )

        # ── CSV download: municipalities with ratio < 0.25 ──
        # Build a dataframe of all municipalities below 0.25 with tier info
        latest_fir = fir_wide.sort_values("year").drop_duplicates("sgc_code", keep="last")
        below_df = latest_fir[
            (latest_fir["farmland_tax_ratio"].notna())
            & (latest_fir["farmland_tax_ratio"] > 0)
            & (latest_fir["farmland_tax_ratio"] < 0.25)
        ][["sgc_code", "municipality_name", "farmland_tax_ratio", "tier"]].copy()

        below_df["farmland_tax_ratio"] = below_df["farmland_tax_ratio"].round(4)

        # Split into lower-tier vs upper/single-tier
        lower_tier = below_df[below_df["tier"] == "lower"][
            ["municipality_name", "farmland_tax_ratio"]
        ].rename(columns={
            "municipality_name": "Municipality",
            "farmland_tax_ratio": "Farm Tax Ratio",
        }).sort_values("Municipality").reset_index(drop=True)

        upper_single = below_df[below_df["tier"] != "lower"][
            ["municipality_name", "farmland_tax_ratio"]
        ].rename(columns={
            "municipality_name": "Municipality",
            "farmland_tax_ratio": "Farm Tax Ratio",
        }).sort_values("Municipality").reset_index(drop=True)

        # Build a combined CSV with section headers
        import io as _io
        csv_buf = _io.StringIO()
        csv_buf.write("Lower-Tier & Single-Tier Municipalities with Farm Tax Ratio Below 0.25\n")
        lower_tier.to_csv(csv_buf, index=False)
        csv_buf.write("\n")
        csv_buf.write("Upper-Tier Municipalities with Farm Tax Ratio Below 0.25\n")
        upper_single.to_csv(csv_buf, index=False)

        st.download_button(
            label=f"📥 Download Ratio < 0.25 List ({len(below_df)} municipalities)",
            data=csv_buf.getvalue().encode("utf-8"),
            file_name="municipalities_below_025_ratio.csv",
            mime="text/csv",
            key="download_below_025_csv",
        )

st.markdown("---")

# ── Phase 5A: Municipality Comparison Table ──────────────────────────────────
if not is_provincial:
    with st.expander("📊 Compare Municipalities", expanded=False):
        st.markdown("Select up to **10 municipalities** to compare side-by-side.")

        # Get the latest FIR data for each municipality
        _latest_fir = (
            fir_wide[fir_wide["farmland_cva"].notna() & (fir_wide["farmland_cva"] > 0)]
            .sort_values("year")
            .drop_duplicates("sgc_code", keep="last")
        )

        # Build comparison options (exclude the already-selected municipality)
        _comp_options = {
            code: name for code, name in muni_lookup.items()
            if code in set(_latest_fir["sgc_code"]) and code != selected_code
        }
        _comp_sorted = sorted(_comp_options.items(), key=lambda x: x[1])
        _comp_names = [name for _, name in _comp_sorted]
        _comp_codes_map = {name: code for code, name in _comp_sorted}

        # Multi-select with default neighbours (same county if available)
        _default_peers = []
        if GEO_FILE.exists():
            _geo_df = smart_read(GEO_FILE)
            if "sgc_code" in _geo_df.columns and "county" in _geo_df.columns:
                _geo_df["sgc_code"] = _geo_df["sgc_code"].astype(str).str.zfill(7)
                _my_county = _geo_df.loc[_geo_df["sgc_code"] == selected_code, "county"]
                if not _my_county.empty:
                    _county_codes = set(
                        _geo_df.loc[_geo_df["county"] == _my_county.iloc[0], "sgc_code"]
                    )
                    _default_peers = [
                        name for name, code in _comp_codes_map.items()
                        if code in _county_codes
                    ][:5]  # Cap default to 5 neighbours

        _selected_peers = st.multiselect(
            "Add municipalities to compare",
            options=_comp_names,
            default=_default_peers,
            max_selections=10,
            key="_muni_compare_select",
        )

        # Build comparison codes: selected + peers
        _compare_codes = [selected_code] + [_comp_codes_map[n] for n in _selected_peers]

        if len(_compare_codes) >= 2:
            _comp_data = _latest_fir[_latest_fir["sgc_code"].isin(_compare_codes)].copy()
            _comp_data["Municipality"] = _comp_data["sgc_code"].map(muni_lookup)

            # Compute derived columns
            _comp_data["Farm Tax Share (%)"] = (
                _comp_data["farmland_muni_taxes"] / _comp_data["total_muni_taxes"] * 100
            ).fillna(0).round(2)

            # Build display table
            _display_cols = {
                "Municipality": "Municipality",
                "farmland_tax_ratio": "Farm Tax Ratio",
                "farmland_cva": "Farmland CVA ($)",
                "residential_cva": "Residential CVA ($)",
                "Farm Tax Share (%)": "Farm Tax Share (%)",
                "farmland_muni_taxes": "Farm Muni Taxes ($)",
            }
            _available = [c for c in _display_cols if c in _comp_data.columns]
            _table = _comp_data[_available].rename(columns=_display_cols).copy()
            _table = _table.sort_values("Farm Tax Ratio", ascending=True)

            # Highlight current municipality
            def _highlight_selected(row):
                if selected_name in str(row.get("Municipality", "")):
                    return ["background-color: #d1fae5"] * len(row)
                return [""] * len(row)

            _styled_table = _table.style.apply(_highlight_selected, axis=1).format({
                "Farm Tax Ratio": "{:.4f}",
                "Farmland CVA ($)": "${:,.0f}",
                "Residential CVA ($)": "${:,.0f}",
                "Farm Tax Share (%)": "{:.2f}%",
                "Farm Muni Taxes ($)": "${:,.0f}",
            })

            st.dataframe(_styled_table, hide_index=True, use_container_width=True)
            st.caption(
                f"Showing latest FIR year for each municipality. "
                f"**{selected_name}** highlighted in green. "
                f"Sorted by farm tax ratio (ascending)."
            )
        else:
            st.info("Select at least one municipality above to see a comparison.")

st.markdown("---")


if is_provincial:
    prov_df = build_provincial_aggregate(fir_wide)
    render_farm_tax_story(
        fir_wide_df=prov_df,
        sgc_code=PROVINCIAL_CODE,
        muni_name=PROVINCIAL_NAME,
        is_upper_tier=False,
        is_provincial=True,
        fir_raw_df=fir_wide,
    )
else:
    # Determine if this is an upper-tier entry (V45: for disclaimer)
    is_upper_tier = tier_lookup.get(selected_code) == "upper"
    render_farm_tax_story(
        fir_wide_df=fir_wide,
        sgc_code=selected_code,
        muni_name=selected_name,
        is_upper_tier=is_upper_tier,
        fir_raw_df=fir_wide,
    )

from app.utils import global_footer
global_footer()
