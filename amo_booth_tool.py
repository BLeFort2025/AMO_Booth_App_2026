import sys
from pathlib import Path
import base64

# Add project root to sys.path so 'app' imports work
project_root = str(Path(__file__).parent.absolute())
if project_root not in sys.path:
    sys.path.insert(0, project_root)
app_dir = str(Path(__file__).parent.absolute() / "app")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import os
from app.smart_read import smart_read
from app.utils import inject_theme_css, global_footer
from app.farm_tax.farm_tax_report import calculate_ratio_direct
from app.roma_report import (
    generate_roma_pdf,
    save_booth_lead,
    get_booth_leads_df,
    send_roma_report_email,
    generate_mailto_url,
    make_download_button_html,
)

try:
    import pydeck as pdk
    HAS_PYDECK = True
except ImportError:
    HAS_PYDECK = False

st.set_page_config(
    page_title="ROMA 2027 Interactive Tool",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_theme_css()

# Hide Streamlit header/footer for standalone appearance
st.markdown("""
<style>
    header[data-testid="stHeader"] {display: none;}
    footer {display: none;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg, #f0f7f0 0%, #e8f5e9 100%);}
    .stApp h1, .stApp h2 {color: #1b5e20 !important;}
    .stApp h3 {color: #2E7D32 !important;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(max_entries=1, ttl=1800)
def load_fir_data():
    try:
        return smart_read("data/derived/fir_indicators.csv", low_memory=False)
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data(max_entries=1, ttl=1800)
def load_geo_data():
    try:
        return smart_read("data/latest/wellbeing/dim_geography.csv")
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data(max_entries=1, ttl=1800)
def load_boundaries():
    try:
        import geopandas as gpd
        gdf = gpd.read_file("data/latest/wellbeing/ontario_csd_boundaries.geojson")
        gdf["sgc_code"] = gdf["sgc_code"].astype(str).str.zfill(7)
        return gdf
    except Exception:
        return None

@st.cache_data(max_entries=1, ttl=1800)
def load_fam_rscm_data():
    """Load the 2016 FAM/RSCM dataset from the Ministry of Finance."""
    try:
        fam_path = Path(__file__).parent.absolute() / "data" / "derived" / "ompf_fam_rscm_2016.xlsx"
        fam_df = pd.read_excel(fam_path, skiprows=5)
        fam_df = fam_df.rename(columns={
            "MunId": "fir_code",
            "Rural and Small Community Measure (RSCM)*": "RSCM",
            "Farm Area Measure (FAM)**": "FAM",
        })
        fam_df["FAM"] = pd.to_numeric(fam_df["FAM"], errors='coerce').fillna(0.0)
        fam_df["RSCM"] = pd.to_numeric(fam_df["RSCM"], errors='coerce').fillna(0.0)
        return fam_df
    except Exception:
        return pd.DataFrame()


fir_df = load_fir_data()
geo_df = load_geo_data()
boundaries = load_boundaries()
fam_rscm_df = load_fam_rscm_data()

if fir_df.empty or geo_df.empty:
    st.error("Data missing. Please run ETL pipelines.")
    st.stop()

# Ensure SGC codes are strings
fir_df["sgc_code"] = fir_df["sgc_code"].astype(str).str.zfill(7)
geo_df["sgc_code"] = geo_df["sgc_code"].astype(str).str.zfill(7)

# Build FAM/RSCM lookups
rscm_lookup = {}
fam_lookup = {}
region_lookup = {}
if not fam_rscm_df.empty:
    rscm_lookup = dict(zip(fam_rscm_df["fir_code"], fam_rscm_df["RSCM"]))
    fam_lookup = dict(zip(fam_rscm_df["fir_code"], fam_rscm_df["FAM"]))
    region_lookup = dict(zip(fam_rscm_df["fir_code"], fam_rscm_df["Region"]))

def is_eligible(fir_code):
    """Apply the 3-Gate eligibility test."""
    rscm = rscm_lookup.get(fir_code, 0.0)
    fam = fam_lookup.get(fir_code, 0.0)
    region = region_lookup.get(fir_code, "")
    is_northern = region in ["Northeast", "Northwest"]
    return is_northern or rscm >= 0.25 or fam > 0.05

# Precalculate OMPF $1B Scenario denominators
latest_ompf_df = fir_df[fir_df['tier'] != 'upper'].sort_values('year').drop_duplicates('sgc_code', keep='last').copy()
latest_ompf_df['ompf_grant'] = latest_ompf_df['ompf_grant'].fillna(0.0)
TOTAL_CURRENT_OMPF = latest_ompf_df['ompf_grant'].sum()  # ~$497M
SCENARIO_OMPF_TOTAL = 1_000_000_000

# Calculate the "rural-only" pool for the gated scenario
RURAL_CURRENT_OMPF = 0.0
URBAN_LEAKAGE_OMPF = 0.0
for _, row in latest_ompf_df.iterrows():
    grant = float(row.get("ompf_grant", 0.0))
    if is_eligible(row["fir_code"]):
        RURAL_CURRENT_OMPF += grant
    else:
        URBAN_LEAKAGE_OMPF += grant

# Create municipality lookups
community_lookup = {}
csd_type_lookup = {}
county_lookup = {}
for _, row in geo_df.iterrows():
    name = str(row.get("geo_name", "")).strip()
    county = str(row.get("county", "")).strip() if pd.notna(row.get("county")) else ""
    csd_type = str(row.get("csd_type", "")).strip() if pd.notna(row.get("csd_type")) else ""
    code = row["sgc_code"]
    
    csd_type_lookup[code] = csd_type
    county_lookup[code] = county
    
    # Disambiguate when municipality name matches county name (e.g. Town of Essex vs Essex County)
    if county and name.lower() == county.lower() and csd_type:
        label = f"{name} ({csd_type})"
    elif county:
        label = f"{name} ({county})"
    else:
        label = name
    community_lookup[code] = label

reverse_lookup = {v: k for k, v in community_lookup.items()}
available_sgcs = sorted(fir_df["sgc_code"].unique())
available_names = sorted([community_lookup.get(c, c) for c in available_sgcs if c in community_lookup])

with st.sidebar:
    logo_path = Path(__file__).parent / "app" / "data" / "OFA_logo.png"
    if logo_path.exists():
        try:
            with open(logo_path, "rb") as f:
                b64_logo = base64.b64encode(f.read()).decode("utf-8")
            st.markdown(
                f'<div style="text-align: center; margin-bottom: 1rem;">'
                f'<img src="data:image/png;base64,{b64_logo}" width="150" alt="OFA Logo">'
                f'</div>',
                unsafe_allow_html=True
            )
        except Exception:
            st.markdown("### 🌾 OFA")
    else:
        st.markdown("### 🌾 OFA")
    st.markdown("## 🏛️ ROMA 2027")
    st.markdown("**Rural Ontario Municipal Association**")
    st.caption("OFA Fair Farm Taxes & OMPF Briefing Tool")
    
    default_idx = available_names.index("Zorra (Oxford)") if "Zorra (Oxford)" in available_names else 0
    selected_name = st.selectbox("Select Municipality", options=available_names, index=default_idx)
    selected_sgc = reverse_lookup[selected_name]
    
    st.markdown("---")
    st.metric("Municipalities Tracked", len(available_names))
    st.caption("Data source: Ontario Financial Information Return (FIR) 2010-2024")

    # Booth Leads Counter & Export
    leads_df = get_booth_leads_df()
    if not leads_df.empty:
        st.markdown("---")
        st.metric("📋 ROMA Leads Captured", len(leads_df))
        leads_csv = leads_df.to_csv(index=False).encode("utf-8")
        st.markdown(
            make_download_button_html(
                data_bytes=leads_csv,
                filename="ROMA_2027_Booth_Leads.csv",
                mime_type="text/csv",
                button_label="📥 Export Booth Leads (CSV)",
                bg_color="#ffffff",
                text_color="#2E7D32",
                border_color="#2E7D32",
            ),
            unsafe_allow_html=True,
        )

    with st.expander("⚙️ Laptop Email Setup (Optional)", expanded=False):
        st.caption("Configure SMTP to send emails directly from this laptop.")
        smtp_h = st.text_input("SMTP Host", value=os.environ.get("SMTP_HOST", ""), placeholder="smtp.office365.com")
        smtp_p = st.number_input("SMTP Port", value=int(os.environ.get("SMTP_PORT", 587)), min_value=25, max_value=65535)
        smtp_u = st.text_input("Username / Email", value=os.environ.get("SMTP_USER", ""), placeholder="ben.lefort@ofa.on.ca")
        smtp_pwd = st.text_input("Password / App Password", type="password", value=os.environ.get("SMTP_PASS", ""))
        if smtp_h and smtp_u and smtp_pwd:
            st.session_state["smtp_config"] = {
                "host": smtp_h,
                "port": smtp_p,
                "user": smtp_u,
                "password": smtp_pwd,
                "sender": smtp_u,
            }
            st.success("✅ SMTP active for live dispatch.")
        else:
            st.info("When unconfigured, leads are saved locally with 1-click Outlook draft.")

# Get data for selected municipality
muni_df = fir_df[fir_df["sgc_code"] == selected_sgc].sort_values("year")
latest_year = muni_df["year"].max()
latest_row = muni_df[muni_df["year"] == latest_year].iloc[0]
fir_code = latest_row["fir_code"]

muni_type = csd_type_lookup.get(selected_sgc, "")
muni_county = county_lookup.get(selected_sgc, "")
tier_val = latest_row.get("tier", "")
tier_name = "Single-Tier Municipality" if tier_val == "single" else "Lower-Tier Municipality"
type_desc = f"{muni_type} ({tier_name})" if muni_type else tier_name

st.markdown(f"## Fair Farm Taxes & Fully Funded Municipalities")
st.markdown(f"### Key Fiscal Metrics for **{selected_name}**")
st.caption(f"🏛️ **Classification:** {type_desc} · **County/Region:** {muni_county or 'N/A'} · **SGC Code:** `{selected_sgc}` · **FIR Code:** `{fir_code}`")

# --- Eligibility Banner ---
muni_rscm = rscm_lookup.get(fir_code, 0.0)
muni_fam = fam_lookup.get(fir_code, 0.0)
muni_region = region_lookup.get(fir_code, "")
muni_eligible = is_eligible(fir_code)

if muni_eligible:
    reasons = []
    if muni_region in ["Northeast", "Northwest"]:
        reasons.append(f"Northern Ontario ({muni_region})")
    if muni_rscm >= 0.25:
        reasons.append(f"RSCM ≥ 25% ({muni_rscm:.1%})")
    if muni_fam > 0.05:
        reasons.append(f"FAM > 5% ({muni_fam:.1%})")
    st.success(f"✅ **{selected_name}** qualifies under the proposed Rural OMPF Guidelines — {', '.join(reasons)}")
else:
    st.error(f"🚫 **{selected_name}** would NOT qualify under the proposed Rural OMPF Guidelines (RSCM: {muni_rscm:.1%} | FAM: {muni_fam:.1%} | Region: {muni_region or 'N/A'})")

# --- Section 1: Map ---
if HAS_PYDECK and boundaries is not None:
    with st.container():
        col_m1, col_m2 = st.columns([3, 2])
        with col_m1:
            st.markdown("#### Geographic Distribution & Rural Eligibility")
        with col_m2:
            map_view = st.radio(
                "Map Focus",
                options=["Local / County Focus", "Province-Wide Overview"],
                horizontal=True,
                label_visibility="collapsed"
            )

        # Copy to avoid warnings
        map_df = latest_ompf_df.copy()
        
        # Merge with boundaries
        map_geo = boundaries.merge(map_df[["sgc_code", "farmland_tax_ratio", "fir_code"]], on="sgc_code", how="left")
        map_geo["display_name"] = map_geo["sgc_code"].map(lambda c: community_lookup.get(c, c))
        map_geo["county_name"] = map_geo["sgc_code"].map(lambda c: county_lookup.get(c, ""))
        map_geo["muni_type"] = map_geo["sgc_code"].map(lambda c: csd_type_lookup.get(c, ""))
        
        # Colors: Green for eligible, red for filtered, dark green for selected
        def get_color(row):
            if row["sgc_code"] == selected_sgc:
                return [46, 125, 50, 255]  # Dark Green - selected
            elif pd.notna(row.get("fir_code")) and is_eligible(row.get("fir_code", 0)):
                return [200, 230, 200, 160]  # Light Green - eligible
            elif pd.notna(row.get("farmland_tax_ratio")) and row.get("farmland_tax_ratio", 0) > 0:
                return [255, 200, 200, 160]  # Light Red - filtered but has farmland
            else:
                return [220, 220, 220, 80]  # Grey

        def get_line_color(row):
            if row["sgc_code"] == selected_sgc:
                return [255, 165, 0, 255]  # Orange highlight
            return [255, 255, 255, 100]

        def get_status_label(row):
            if row["sgc_code"] == selected_sgc:
                return "Selected Municipality"
            elif pd.notna(row.get("fir_code")) and is_eligible(row.get("fir_code", 0)):
                return "Eligible (Rural/Northern)"
            elif pd.notna(row.get("farmland_tax_ratio")) and row.get("farmland_tax_ratio", 0) > 0:
                return "Filtered Out (Urban)"
            else:
                return "No Data"

        map_geo["fill_color"] = map_geo.apply(get_color, axis=1)
        map_geo["line_color"] = map_geo.apply(get_line_color, axis=1)
        map_geo["status_label"] = map_geo.apply(get_status_label, axis=1)
        
        # Remove geometry from tooltip variables
        export_geo = map_geo[["geometry", "fill_color", "line_color", "display_name", "status_label", "county_name", "muni_type", "sgc_code"]].copy()
        
        selected_feature = export_geo[export_geo["sgc_code"] == selected_sgc]
        if map_view == "Local / County Focus" and not selected_feature.empty:
            centroid = selected_feature.geometry.centroid.iloc[0]
            lat, lon = centroid.y, centroid.x
            zoom_val = 8.8
        else:
            lat, lon = 44.5, -79.5
            zoom_val = 6.2
            
        view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom_val, pitch=0)
        layer = pdk.Layer(
            "GeoJsonLayer",
            data=export_geo.__geo_interface__,
            pickable=True,
            stroked=True,
            filled=True,
            get_fill_color="properties.fill_color",
            get_line_color="properties.line_color",
            get_line_width=300,
            line_width_min_pixels=1,
            auto_highlight=True,
            highlight_color=[255, 200, 0, 150]
        )
        tooltip = {
            "html": "<b>{display_name}</b><br/>Classification: {muni_type}<br/>County: {county_name}<br/>Status: <b>{status_label}</b>",
            "style": {"backgroundColor": "#1b5e20", "color": "white", "font-family": "sans-serif", "font-size": "12px"}
        }
        deck = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="mapbox://styles/mapbox/light-v11")
        st.pydeck_chart(deck, height=360)
        st.caption("🟢 Selected Municipality  ·  🟩 Eligible (Rural/Northern)  ·  🟥 Filtered Out (Urban)  ·  ⬜ No Data")
        if map_view == "Local / County Focus":
            st.caption(f"📍 Showing municipal boundary for **{selected_name}** and neighboring municipalities in **{muni_county}**.")

# --- Calculations ---
TARGET_RATIO = 0.15
current_ratio = latest_row.get("farmland_tax_ratio", 0)
if pd.isna(current_ratio): current_ratio = 0

is_below_or_equal = (current_ratio <= TARGET_RATIO and current_ratio > 0)

def safe_val(v): return float(v) if pd.notna(v) else 0.0

res = None
if not is_below_or_equal and current_ratio > 0:
    res = calculate_ratio_direct(
        chosen_ratio=TARGET_RATIO,
        farm_cva=safe_val(latest_row.get("farmland_cva")),
        res_cva=safe_val(latest_row.get("residential_cva")),
        com_cva=safe_val(latest_row.get("commercial_cva")),
        ind_cva=safe_val(latest_row.get("industrial_cva")),
        ft_ratio=current_ratio,
        ct_ratio=safe_val(latest_row.get("commercial_tax_ratio")),
        it_ratio=safe_val(latest_row.get("industrial_tax_ratio")),
        total_muni_taxes=safe_val(latest_row.get("total_muni_taxes")),
        current_res_taxes=safe_val(latest_row.get("residential_muni_taxes")),
        current_burden=safe_val(latest_row.get("farmland_share_of_taxes")),
        total_households=safe_val(latest_row.get("total_households"))
    )
    if res:
        redistribution_amount = res.farm_savings_total
    else:
        redistribution_amount = 0
else:
    redistribution_amount = 0

# OMPF Calc — Scenario A: $1B Unfettered (current formula)
ompf_grant = safe_val(latest_row.get("ompf_grant"))
total_rev = safe_val(latest_row.get("total_revenue"))
current_share = ompf_grant / TOTAL_CURRENT_OMPF if TOTAL_CURRENT_OMPF > 0 else 0
scenario_grant_unfettered = current_share * SCENARIO_OMPF_TOTAL
additional_ompf_unfettered = scenario_grant_unfettered - ompf_grant

# OMPF Calc — Scenario B: $1B Gated (rural-only formula)
if muni_eligible and RURAL_CURRENT_OMPF > 0:
    gated_share = ompf_grant / RURAL_CURRENT_OMPF
    scenario_grant_gated = gated_share * SCENARIO_OMPF_TOTAL
    additional_ompf_gated = scenario_grant_gated - ompf_grant
else:
    scenario_grant_gated = 0.0
    additional_ompf_gated = -ompf_grant  # They lose their current grant

current_provincial_support_share = ompf_grant / total_rev if total_rev > 0 else 0

# --- Section 2: KPIs ---
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 🌾 Fair Farm Taxes")
    if current_ratio == 0:
        st.info("No farm tax data available for this municipality.")
    elif is_below_or_equal:
        st.success(f"🎉 **{selected_name}** is already at or below OFA's proposed {TARGET_RATIO:.2f} maximum farm tax ratio (Current: {current_ratio:.4f}). Thank you for your leadership on fair farm taxation!")
    else:
        st.markdown(f"Under OFA's proposed **{TARGET_RATIO:.2f}** maximum ratio, the revenue-neutral shift across all property classes:")
        st.metric("Farm Tax Relief", f"${redistribution_amount:,.0f}")
        if res and res.res_increase_per_household_month:
            st.caption(f"Impact to average household: **\\${res.res_increase_per_household_month:,.2f}/month** · Current ratio: {current_ratio:.4f}")
        else:
            st.caption(f"Current farm tax ratio: **{current_ratio:.4f}** ({latest_year} data).")

with col2:
    st.markdown("### 📊 Restored Provincial Funding")
    st.markdown(f"If the OMPF is restored to **\\$1 Billion** under the **current formula**:")
    st.metric("Additional Annual OMPF", f"${additional_ompf_unfettered:,.0f}")
    st.caption(f"Current ({latest_year}): **\\${ompf_grant:,.0f}** → Scenario: **\\${scenario_grant_unfettered:,.0f}**")

with col3:
    st.markdown("### 🛡️ Rural-Targeted Funding")
    if muni_eligible:
        bonus = additional_ompf_gated - additional_ompf_unfettered
        st.markdown(f"If the OMPF is restored to **\\$1 Billion** with **rural-only eligibility**:")
        st.metric("Additional Annual OMPF (Gated)", f"${additional_ompf_gated:,.0f}", delta=f"+${bonus:,.0f} vs current formula")
        st.caption(f"Gated Scenario: **\\${scenario_grant_gated:,.0f}**. Rural gate redirects \\${URBAN_LEAKAGE_OMPF:,.0f} from urban centres.")
    else:
        st.metric("OMPF Under Gated Model", "$0", delta=f"-${ompf_grant:,.0f}")
        st.caption("This municipality does not meet the RSCM, FAM, or Northern eligibility gates.")

# --- Bottom Line Callout ---
net_position = 0.0
if muni_eligible and redistribution_amount > 0:
    net_position = additional_ompf_gated - redistribution_amount
    if net_position >= 0:
        st.success(f"💡 **Bottom Line for {selected_name}:** Your municipality gains **\\${additional_ompf_gated:,.0f}** in new annual OMPF funding — more than covering the **\\${redistribution_amount:,.0f}** farm tax shift. **Net gain: \\${net_position:,.0f}/year.**")
    else:
        gap = abs(net_position)
        coverage_pct = (additional_ompf_gated / redistribution_amount) * 100 if redistribution_amount > 0 else 0
        st.info(f"💡 **Bottom Line for {selected_name}:** Your municipality gains **\\${additional_ompf_gated:,.0f}** in new OMPF funding, covering **{coverage_pct:.0f}%** of the **\\${redistribution_amount:,.0f}** farm tax shift. Remaining gap: **\\${gap:,.0f}/year.**")
elif muni_eligible and is_below_or_equal:
    net_position = additional_ompf_gated
    st.success(f"💡 **{selected_name}** already meets OFA's farm tax target and would receive **\\${additional_ompf_gated:,.0f}** in additional annual OMPF funding under the rural-only model.")

# --- Section 2.5: ROMA 2027 Conference Action Center ---
historical_records = []
if not muni_df.empty:
    for _, h_row in muni_df.iterrows():
        historical_records.append({
            "year": int(h_row.get("year", 0)),
            "farmland_cva": safe_val(h_row.get("farmland_cva")),
            "residential_cva": safe_val(h_row.get("residential_cva")),
            "farmland_tax_ratio": safe_val(h_row.get("farmland_tax_ratio")),
            "farmland_share_of_taxes": safe_val(h_row.get("farmland_share_of_taxes")),
            "ompf_grant": safe_val(h_row.get("ompf_grant")),
            "ompf_dependency": safe_val(h_row.get("ompf_dependency")),
        })

class_breakdown_dict = {}
if res:
    class_breakdown_dict = {
        "Residential": res.res_increase_total,
        "Commercial": res.com_increase_total,
        "Industrial": res.ind_increase_total,
        "Other": res.other_increase_total,
    }

report_payload = {
    "municipality_name": selected_name,
    "county": muni_county,
    "type_desc": type_desc,
    "sgc_code": selected_sgc,
    "fir_code": fir_code,
    "latest_year": latest_year,
    "muni_rscm": muni_rscm,
    "muni_fam": muni_fam,
    "muni_region": muni_region,
    "muni_eligible": muni_eligible,
    "current_ratio": current_ratio,
    "target_ratio": TARGET_RATIO,
    "is_below_or_equal": is_below_or_equal,
    "redistribution_amount": redistribution_amount,
    "res_increase_month": res.res_increase_per_household_month if res else 0.0,
    "res_increase_year": res.res_increase_per_household if res else 0.0,
    "ompf_grant": ompf_grant,
    "scenario_grant_unfettered": scenario_grant_unfettered,
    "additional_ompf_unfettered": additional_ompf_unfettered,
    "scenario_grant_gated": scenario_grant_gated,
    "additional_ompf_gated": additional_ompf_gated,
    "bonus_gated": additional_ompf_gated - additional_ompf_unfettered if muni_eligible else 0.0,
    "urban_leakage": URBAN_LEAKAGE_OMPF,
    "net_position": net_position,
    "class_breakdown": class_breakdown_dict,
    "historical_trends": historical_records,
}

pdf_bytes = generate_roma_pdf(report_payload)
clean_name = "".join(c for c in selected_name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")

st.markdown("---")
st.markdown("### 🏛️ ROMA 2027 Delegate Action Center")

action_col1, action_col2 = st.columns([1, 2])

with action_col1:
    st.markdown("#### 📄 Executive Briefing")
    st.markdown("Customized 2-page OFA briefing document summarizing all fiscal, assessment, and OMPF metrics for council.")
    pdf_filename = f"OFA_ROMA2027_Briefing_{clean_name}.pdf"
    st.markdown(
        make_download_button_html(
            data_bytes=pdf_bytes,
            filename=pdf_filename,
            mime_type="application/pdf",
            button_label="📥 Download 2-Page PDF Report",
            bg_color="#2E7D32",
            text_color="#ffffff",
            border_color="#1b5e20",
        ),
        unsafe_allow_html=True,
    )
    st.caption("Includes OFA branding, 3-gate eligibility audit, revenue-neutral shift table, and longitudinal FIR trends.")

with action_col2:
    st.markdown("#### 📬 Auto-Populate & Email Report to Delegate")
    st.markdown("Enter delegate contact details below to dispatch this municipal briefing and record the booth conversation.")

    with st.form(key=f"roma_email_form_{selected_sgc}"):
        em_c1, em_c2 = st.columns(2)
        with em_c1:
            recip_email = st.text_input("Councilor / Staff Email *", placeholder="councillor@municipality.ca")
        with em_c2:
            recip_name = st.text_input("Name & Title (Optional)", placeholder="e.g. Mayor Jane Smith")

        em_c3, em_c4 = st.columns([1.5, 2.5])
        with em_c3:
            recip_role = st.selectbox(
                "Role",
                ["Councillor / Mayor", "Municipal Staff / CAO", "OFA Member / Farmer", "Other Delegate"],
            )
        with em_c4:
            notes = st.text_input("Booth Notes (Optional)", placeholder="Key priorities or comments...")

        btn_submit = st.form_submit_button("✉️ Send PDF Report to Delegate", use_container_width=True)

    if btn_submit:
        if not recip_email or "@" not in recip_email or "." not in recip_email.split("@")[-1]:
            st.error("Please enter a valid email address.")
        else:
            # 1. Log lead in local CSV
            save_booth_lead(
                municipality_name=selected_name,
                sgc_code=selected_sgc,
                recipient_name=recip_name,
                recipient_email=recip_email,
                recipient_role=recip_role,
                net_position=net_position,
                status="Captured",
                notes=notes,
            )

            # 2. Try SMTP dispatch
            smtp_config = st.session_state.get("smtp_config", {})
            success, msg = send_roma_report_email(
                to_email=recip_email,
                recipient_name=recip_name,
                municipality_name=selected_name,
                pdf_bytes=pdf_bytes,
                net_position=net_position,
                smtp_config=smtp_config,
            )

            if success:
                st.success(f"✅ {msg}")
            else:
                st.success(f"📋 **Lead Captured:** Contact recorded in ROMA 2027 booth log! ({recip_email})")
                mailto_link = generate_mailto_url(
                    to_email=recip_email,
                    recipient_name=recip_name,
                    municipality_name=selected_name,
                    net_position=net_position,
                )
                st.info(f"ℹ️ {msg}")
                st.markdown(
                    f'''
                    <div style="margin-top: 8px;">
                        <a href="{mailto_link}" target="_blank" style="display: inline-block; padding: 7px 16px; background-color: #2E7D32; color: white; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 13px;">
                            ✉️ Click to Open Pre-Filled Draft in Outlook / Mail Client
                        </a>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )

# --- Section 3: Fair Farm Taxes Details ---
def make_chart_config(chart_title: str):
    clean_muni = "".join(c for c in selected_name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    clean_title = "".join(c for c in chart_title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    return {
        "toImageButtonOptions": {
            "format": "png",
            "filename": f"{clean_muni}_{clean_title}",
            "height": 600,
            "width": 1000,
            "scale": 2.5,  # High-DPI crystal-clear presentation resolution
        },
        "displayModeBar": True,
        "displaylogo": False,
    }

with st.expander("📈 Fair Farm Taxes — Details", expanded=True):
    if not muni_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            # Indexed CVA growth
            base_year = muni_df["year"].min()
            cva_df = muni_df[["year", "farmland_cva", "residential_cva"]].copy().dropna(subset=["farmland_cva"])
            if not cva_df.empty:
                base_farm = cva_df.iloc[0]["farmland_cva"]
                base_res = cva_df.iloc[0]["residential_cva"]
                cva_df["Farm CVA Growth"] = (cva_df["farmland_cva"] / base_farm) * 100 if base_farm > 0 else 100
                cva_df["Res CVA Growth"] = (cva_df["residential_cva"] / base_res) * 100 if base_res > 0 else 100
                
                fig = px.line(cva_df, x="year", y=["Farm CVA Growth", "Res CVA Growth"], 
                              title=f"Assessment Growth Since {base_year} (Index=100)",
                              color_discrete_map={"Farm CVA Growth": "#2E7D32", "Res CVA Growth": "#1565C0"})
                fig.update_layout(
                    yaxis_title="Index Value", 
                    xaxis_title="Year", 
                    legend_title=None, 
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
                    margin=dict(l=65, r=65, t=75, b=55),
                )
                st.plotly_chart(fig, use_container_width=True, config=make_chart_config("Assessment_Growth"))
                
        with c2:
            # Tax share over time
            share_df = muni_df[["year", "farmland_share_of_taxes"]].dropna()
            if not share_df.empty:
                share_df["Farm Tax Share (%)"] = share_df["farmland_share_of_taxes"] * 100
                fig2 = px.area(share_df, x="year", y="Farm Tax Share (%)", 
                               title="Farmland Share of Total Municipal Taxes",
                               color_discrete_sequence=["#2E7D32"])
                fig2.update_layout(
                    yaxis_title="Share of Tax Levy (%)", 
                    xaxis_title="Year",
                    margin=dict(l=65, r=65, t=75, b=55),
                )
                st.plotly_chart(fig2, use_container_width=True, config=make_chart_config("Farmland_Tax_Share"))
                
        if res:
            st.markdown("#### Revenue-Neutral Redistribution Breakdown")
            breakdown = pd.DataFrame([
                {"Property Class": "Residential", "Impact": res.res_increase_total},
                {"Property Class": "Commercial", "Impact": res.com_increase_total},
                {"Property Class": "Industrial", "Impact": res.ind_increase_total},
                {"Property Class": "All Other Classes", "Impact": res.other_increase_total},
            ])
            st.dataframe(breakdown.style.format({"Impact": "${:,.0f}"}), hide_index=True)

# --- Section 4: Track 2 & 3 Charts ---
with st.expander("📉 OMPF Funding Details", expanded=True):
    if not muni_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            ompf_df = muni_df[["year", "ompf_grant"]].dropna()
            if not ompf_df.empty:
                fig3 = px.bar(ompf_df, x="year", y="ompf_grant", title="OMPF Grant Allocation Over Time",
                              color_discrete_sequence=["#D32F2F"])
                fig3.update_layout(
                    yaxis_title="Grant Amount ($)", 
                    xaxis_title="Year",
                    yaxis_tickformat="$,.0f",
                    margin=dict(l=85, r=65, t=75, b=55),
                )
                st.plotly_chart(fig3, use_container_width=True, config=make_chart_config("OMPF_Grant_History"))
                
        with c2:
            dep_df = muni_df[["year", "ompf_dependency"]].dropna()
            if not dep_df.empty:
                dep_df["OMPF Share (%)"] = dep_df["ompf_dependency"] * 100
                fig4 = px.line(dep_df, x="year", y="OMPF Share (%)", 
                               title="OMPF Share of Total Revenue",
                               color_discrete_sequence=["#D32F2F"])
                fig4.update_layout(
                    yaxis_title="OMPF Share of Total Revenue (%)", 
                    xaxis_title="Year",
                    margin=dict(l=65, r=65, t=75, b=55),
                )
                st.plotly_chart(fig4, use_container_width=True, config=make_chart_config("OMPF_Revenue_Share"))

        # Comparison bar chart: Current vs $1B Unfettered vs $1B Gated
        st.markdown("#### 💰 OMPF Scenario Comparison")
        
        scenario_data = pd.DataFrame([
            {"Scenario": f"Current ({latest_year})", "OMPF Amount": ompf_grant},
            {"Scenario": "$1B (Current Formula)", "OMPF Amount": scenario_grant_unfettered},
            {"Scenario": "$1B (Rural-Only Gate)", "OMPF Amount": scenario_grant_gated},
        ])
        
        colors = ["#9E9E9E", "#FF8F00", "#2E7D32"]
        fig5 = go.Figure(data=[
            go.Bar(
                x=scenario_data["Scenario"],
                y=scenario_data["OMPF Amount"],
                marker_color=colors,
                text=[f"${v:,.0f}" for v in scenario_data["OMPF Amount"]],
                textposition="outside"
            )
        ])
        fig5.update_layout(
            yaxis_title="OMPF Grant Amount ($)",
            yaxis_tickformat="$,.0f",
            showlegend=False,
            height=420,
            margin=dict(l=85, r=65, t=75, b=55),
        )
        st.plotly_chart(fig5, use_container_width=True, config=make_chart_config("OMPF_Scenario_Comparison"))

        st.markdown(f"""
        **Key Insight:** Under OFA's proposed gated model, the **\\${URBAN_LEAKAGE_OMPF:,.0f}** currently flowing to 73 urban centres
        would be redirected to qualifying rural and northern municipalities. {'This municipality benefits from that redistribution.' if muni_eligible else 'This municipality would no longer qualify for core OMPF grants.'}
        """)

# --- Section 5: Eligibility Details ---
with st.expander("🔍 Rural Eligibility Gate Details", expanded=False):
    st.markdown("#### Proposed 3-Gate Eligibility Model")
    st.markdown("""
    Under OFA's proposed OMPF guideline reform, a municipality must meet **at least one** of the following criteria to qualify for core OMPF grants:
    
    | Gate | Metric | Threshold | Source |
    |------|--------|-----------|--------|
    | 🏔️ Northern | Located in Northern Ontario | Northeast or Northwest district | Ministry of Finance |
    | 🏘️ RSCM | Rural and Small Community Measure | ≥ 25% | Statistics Canada |
    | 🌾 FAM | Farm Area Measure | > 5% | MPAC Assessment Data |
    """)
    
    st.markdown(f"#### {selected_name} — Eligibility Breakdown")
    
    gate_data = pd.DataFrame([
        {"Gate": "🏔️ Northern Ontario", "Value": muni_region if muni_region else "N/A", "Threshold": "Northeast or Northwest", "Pass": "✅" if muni_region in ["Northeast", "Northwest"] else "❌"},
        {"Gate": "🏘️ RSCM", "Value": f"{muni_rscm:.1%}", "Threshold": "≥ 25%", "Pass": "✅" if muni_rscm >= 0.25 else "❌"},
        {"Gate": "🌾 FAM", "Value": f"{muni_fam:.1%}", "Threshold": "> 5%", "Pass": "✅" if muni_fam > 0.05 else "❌"},
    ])
    st.dataframe(gate_data, hide_index=True, use_container_width=True)
    
    if muni_eligible:
        st.success(f"**Result:** {selected_name} **passes** the eligibility gate and would continue receiving OMPF funding under the proposed reform.")
    else:
        st.error(f"**Result:** {selected_name} **fails** all three gates and would be classified as urban, losing access to core OMPF grants.")

    # Summary stats
    st.markdown("---")
    st.markdown("#### Province-Wide Impact Summary")
    
    # Count eligible vs filtered
    eligible_count = sum(1 for _, r in latest_ompf_df.iterrows() if is_eligible(r["fir_code"]))
    filtered_count = len(latest_ompf_df) - eligible_count
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Eligible Municipalities", eligible_count)
    m2.metric("Filtered Out (Urban)", filtered_count)
    m3.metric("Urban Leakage", f"${URBAN_LEAKAGE_OMPF:,.0f}")

global_footer()
