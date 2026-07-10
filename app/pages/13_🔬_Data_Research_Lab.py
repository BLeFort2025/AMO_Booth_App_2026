"""
🔬 Data Research Lab — page 13.

Cross-dataset scatter explorer with variable registry, preset questions,
Spearman/Pearson toggle, multi-variable regression, and YoY alert system.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# ── path bootstrap ──────────────────────────────────────
_PROJECT = Path(__file__).resolve().parents[2]
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))
try:
    from app.smart_read import smart_read
except ImportError:
    smart_read = pd.read_csv

# ── page config ─────────────────────────────────────────
st.set_page_config(page_title="Data Research Lab", page_icon="🔬", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()


PAL = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899",
       "#14B8A6", "#F97316", "#6366F1", "#84CC16"]

DATA_DIR = _PROJECT / "data"

# ────────────────────────────────────────────────────────
#  DATA LOADERS
# ────────────────────────────────────────────────────────

@st.cache_data(max_entries=3, ttl=600)
def load_geography() -> pd.DataFrame:
    return smart_read(DATA_DIR / "latest" / "wellbeing" / "dim_geography.csv")

@st.cache_data(max_entries=3, ttl=600)
def load_census() -> pd.DataFrame:
    return smart_read(DATA_DIR / "latest" / "wellbeing" / "census_indicators.csv")

@st.cache_data(max_entries=3, ttl=600)
def load_fir() -> pd.DataFrame:
    return smart_read(DATA_DIR / "derived" / "fir_indicators.csv")

@st.cache_data(max_entries=3, ttl=600)
def load_broadband() -> pd.DataFrame:
    return smart_read(DATA_DIR / "derived" / "broadband_coverage.csv")

@st.cache_data(max_entries=3, ttl=600)
def load_confidence_panel() -> pd.DataFrame:
    fp = DATA_DIR / "surveys" / "confidence_panel.csv"
    if fp.exists():
        return smart_read(fp)
    return pd.DataFrame()


# ────────────────────────────────────────────────────────
#  VARIABLE REGISTRY (expanded #3)
# ────────────────────────────────────────────────────────
def _build_census_vars(df: pd.DataFrame) -> Dict[str, str]:
    indicators = sorted(df["indicator"].dropna().unique())
    return {f"census__{ind}": ind.replace("_", " ").title() for ind in indicators}

def _build_fir_vars(df: pd.DataFrame) -> Dict[str, str]:
    skip = {"sgc_code", "year", "municipality_name", "fir_code", "tier", "is_invalid_tax_sum"}
    cols = [c for c in df.columns if c not in skip and df[c].dtype in ("float64", "int64", "float32", "int32")]
    return {f"fir__{c}": c.replace("_", " ").title() for c in cols}

def _build_broadband_vars(df: pd.DataFrame) -> Dict[str, str]:
    indicators = sorted(df["indicator"].dropna().unique())
    return {f"bb__{ind}": ind.replace("_", " ").title() for ind in indicators}

CONFIDENCE_MAP = {
    "Extremely confident": 5, "Very confident": 4, "Somewhat confident": 3,
    "Not so confident": 2, "Not at all confident": 1,
}

def _build_survey_vars(df: pd.DataFrame) -> Dict[str, str]:
    """Expanded survey variable list (#3)."""
    return {
        "survey__confidence_score": "Avg Confidence Score (1-5)",
        "survey__pct_expanding": "% Planning to Expand",
        "survey__pct_contracting": "% Planning to Contract",
        "survey__pct_not_confident": "% Not/Not-at-all Confident",
        "survey__pct_machinery_invest": "% Invested in Machinery",
        "survey__pct_energy_invest": "% Invested in Energy Efficiency",
        "survey__respondent_count": "Survey Respondent Count",
    }


# ────────────────────────────────────────────────────────
#  DATA EXTRACTION
# ────────────────────────────────────────────────────────
def _extract_variable(
    key: str, census: pd.DataFrame, fir: pd.DataFrame,
    broadband: pd.DataFrame, survey: pd.DataFrame,
    geo: pd.DataFrame, census_year: int, fir_year: int,
) -> pd.DataFrame:
    """Extract a variable as DataFrame [county, value]."""
    if key.startswith("census__"):
        indicator = key.replace("census__", "")
        sub = census[(census["indicator"] == indicator) & (census["census_year"] == census_year)]
        merged = sub.merge(geo[["sgc_code", "county"]], on="sgc_code", how="left")
        return merged.groupby("county")["value"].mean().reset_index()

    elif key.startswith("fir__"):
        col = key.replace("fir__", "")
        if col not in fir.columns:
            return pd.DataFrame(columns=["county", "value"])
        sub = fir[fir["year"] == fir_year][["sgc_code", col]].copy()
        sub = sub.rename(columns={col: "value"})
        merged = sub.merge(geo[["sgc_code", "county"]], on="sgc_code", how="left")
        return merged.groupby("county")["value"].mean().reset_index()

    elif key.startswith("bb__"):
        indicator = key.replace("bb__", "")
        sub = broadband[broadband["indicator"] == indicator][["sgc_code", "value"]].copy()
        merged = sub.merge(geo[["sgc_code", "county"]], on="sgc_code", how="left")
        return merged.groupby("county")["value"].mean().reset_index()

    elif key.startswith("survey__"):
        if survey.empty:
            return pd.DataFrame(columns=["county", "value"])
        metric = key.replace("survey__", "")
        sc = survey.copy()
        sc["score"] = sc["confidence_outlook"].map(CONFIDENCE_MAP)
        sc["growth_num"] = sc["growth_expectation"].map({
            "Expand": 3, "Expanded": 3, "Stay the same": 2, "Stayed the same": 2,
            "Contract": 1, "Contracted": 1,
        })

        if metric == "confidence_score":
            agg = sc.groupby("county")["score"].mean().reset_index()
        elif metric == "pct_expanding":
            sc["flag"] = (sc["growth_num"] >= 3).astype(int)
            agg = sc.groupby("county")["flag"].mean().reset_index()
            agg["flag"] *= 100
            agg = agg.rename(columns={"flag": "score"})
        elif metric == "pct_contracting":
            sc["flag"] = (sc["growth_num"] <= 1).astype(int)
            agg = sc.groupby("county")["flag"].mean().reset_index()
            agg["flag"] *= 100
            agg = agg.rename(columns={"flag": "score"})
        elif metric == "pct_not_confident":
            sc["flag"] = (sc["score"] <= 2).astype(int)
            agg = sc.groupby("county")["flag"].mean().reset_index()
            agg["flag"] *= 100
            agg = agg.rename(columns={"flag": "score"})
        elif metric == "pct_machinery_invest":
            sc["flag"] = sc["machinery_investment"].astype(str).str.lower().eq("yes").astype(int)
            agg = sc.groupby("county")["flag"].mean().reset_index()
            agg["flag"] *= 100
            agg = agg.rename(columns={"flag": "score"})
        elif metric == "pct_energy_invest":
            sc["flag"] = sc["energy_investment"].astype(str).str.lower().eq("yes").astype(int)
            agg = sc.groupby("county")["flag"].mean().reset_index()
            agg["flag"] *= 100
            agg = agg.rename(columns={"flag": "score"})
        elif metric == "respondent_count":
            agg = sc.groupby("county").size().reset_index(name="score")
        else:
            return pd.DataFrame(columns=["county", "value"])
        agg.columns = ["county", "value"]
        return agg

    return pd.DataFrame(columns=["county", "value"])


# ────────────────────────────────────────────────────────
#  PRESET RESEARCH QUESTIONS (fixed #4)
# ────────────────────────────────────────────────────────
PRESETS = [
    {
        "name": "Broadband Coverage vs Farmland Assessed Value",
        "x": "bb__broadband_50_10_pct",
        "y": "fir__farmland_cva",
        "desc": "Does broadband access (50/10 Mbps coverage %) correlate with farmland assessed value? Counties with better connectivity may see higher property values.",
    },
    {
        "name": "Aging Communities & Farm Tax Ratios",
        "x": "census__median_age",
        "y": "fir__farmland_tax_ratio",
        "desc": "Do older-skewing communities face higher farm tax ratios? An aging population may indicate fewer new entrants supporting the tax base.",
    },
    {
        "name": "Population Change vs Farmer Confidence",
        "x": "census__pop_change_pct",
        "y": "survey__confidence_score",
        "desc": "Is population growth linked to farmer confidence? Growing communities may offer more market opportunity.",
    },
    {
        "name": "Housing Values & Building Permits",
        "x": "census__median_dwelling_value",
        "y": "fir__res_building_permits_value",
        "desc": "Do communities with higher dwelling values also see more building permit activity? Housing pressure may reflect development trends.",
    },
    {
        "name": "Municipal Debt vs Farm Tax Burden",
        "x": "fir__debt_to_revenue",
        "y": "fir__farmland_tax_per_hectare",
        "desc": "Do municipalities with higher debt-to-revenue ratios pass higher farmland taxes? Fiscal pressure may translate into agricultural tax increases.",
    },
    {
        "name": "Farm Size (CVA) vs Farmer Confidence",
        "x": "fir__farmland_cva",
        "y": "survey__confidence_score",
        "desc": "Are counties with higher total farmland assessed values home to more confident farmers?",
    },
    {
        "name": "Unemployment Rate vs Farm Tax Share",
        "x": "census__unemployment_rate",
        "y": "fir__farmland_share_of_taxes",
        "desc": "Do counties with higher unemployment place a heavier tax burden on farmland as a share of total taxes?",
    },
]


# ════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════
def main():
    st.title("🔬 Data Research Lab")
    st.markdown(
        "Explore **cross-dataset correlations** by pairing any variable from "
        "Census, FIR, Broadband, or Survey data. Each dot is an Ontario county."
    )

    geo = load_geography()
    census = load_census()
    fir = load_fir()
    broadband = load_broadband()
    survey = load_confidence_panel()

    # Build variable registry
    census_vars = _build_census_vars(census)
    fir_vars = _build_fir_vars(fir)
    bb_vars = _build_broadband_vars(broadband)
    survey_vars = _build_survey_vars(survey) if not survey.empty else {}

    all_vars = {}
    all_vars.update({k: f"📊 Census: {v}" for k, v in census_vars.items()})
    all_vars.update({k: f"🏛️ FIR: {v}" for k, v in fir_vars.items()})
    all_vars.update({k: f"📡 Broadband: {v}" for k, v in bb_vars.items()})
    all_vars.update({k: f"📋 Survey: {v}" for k, v in survey_vars.items()})

    mode = st.radio("Mode", [
        "📝 Preset Research Questions",
        "🔧 Custom Explorer",
        "📈 Multi-Variable Regression",
    ], horizontal=True, label_visibility="collapsed")

    if mode.startswith("📝"):
        _render_preset_mode(all_vars, census, fir, broadband, survey, geo)
    elif mode.startswith("🔧"):
        _render_custom_mode(all_vars, census, fir, broadband, survey, geo)
    elif mode.startswith("📈"):
        _render_multi_regression(all_vars, census, fir, broadband, survey, geo)


# ────────────────────────────────────────────────────────
#  Preset Mode
# ────────────────────────────────────────────────────────
def _render_preset_mode(all_vars, census, fir, broadband, survey, geo):
    preset_names = [p["name"] for p in PRESETS]
    sel = st.selectbox("Select a research question", preset_names)
    preset = next(p for p in PRESETS if p["name"] == sel)

    st.info(f"**{preset['name']}** — {preset['desc']}")

    x_label = all_vars.get(preset["x"], preset["x"])
    y_label = all_vars.get(preset["y"], preset["y"])

    yc1, yc2, yc3 = st.columns(3)
    with yc1:
        census_year = st.selectbox("Census year", [2021, 2016, 2011, 2006], index=0, key="preset_cy")
    with yc2:
        fir_years = sorted(fir["year"].dropna().unique(), reverse=True)
        fir_year = st.selectbox("FIR year", fir_years, index=0, key="preset_fy")
    with yc3:
        corr_method = st.selectbox("Correlation", ["Pearson", "Spearman"], key="preset_corr")

    x_data = _extract_variable(preset["x"], census, fir, broadband, survey, geo, census_year, fir_year)
    y_data = _extract_variable(preset["y"], census, fir, broadband, survey, geo, census_year, fir_year)

    _render_scatter(x_data, y_data, x_label, y_label, corr_method)


# ────────────────────────────────────────────────────────
#  Custom Mode
# ────────────────────────────────────────────────────────
def _render_custom_mode(all_vars, census, fir, broadband, survey, geo):
    sorted_keys = sorted(all_vars.keys(), key=lambda k: all_vars[k])
    var_labels = {k: all_vars[k] for k in sorted_keys}

    c1, c2 = st.columns(2)
    with c1:
        x_key = st.selectbox("X-axis variable", sorted_keys, format_func=lambda k: var_labels[k],
                              index=0, key="custom_x")
    with c2:
        y_key = st.selectbox("Y-axis variable", sorted_keys, format_func=lambda k: var_labels[k],
                              index=min(1, len(sorted_keys) - 1), key="custom_y")

    yc1, yc2, yc3 = st.columns(3)
    with yc1:
        census_year = st.selectbox("Census year", [2021, 2016, 2011, 2006], index=0, key="custom_cy")
    with yc2:
        fir_years = sorted(fir["year"].dropna().unique(), reverse=True)
        fir_year = st.selectbox("FIR year", fir_years, index=0, key="custom_fy")
    with yc3:
        corr_method = st.selectbox("Correlation", ["Pearson", "Spearman"], key="custom_corr")

    x_data = _extract_variable(x_key, census, fir, broadband, survey, geo, census_year, fir_year)
    y_data = _extract_variable(y_key, census, fir, broadband, survey, geo, census_year, fir_year)

    _render_scatter(x_data, y_data, var_labels.get(x_key, x_key), var_labels.get(y_key, y_key), corr_method)


# ────────────────────────────────────────────────────────
#  Scatter Plot with Pearson/Spearman toggle (#8)
# ────────────────────────────────────────────────────────
def _render_scatter(x_data, y_data, x_label, y_label, method="Pearson"):
    if x_data.empty or y_data.empty:
        st.warning("One or both variables returned no data. Try different selections or year.")
        return

    merged = x_data.merge(y_data, on="county", suffixes=("_x", "_y"))
    merged = merged.dropna(subset=["value_x", "value_y"])
    merged = merged.rename(columns={"value_x": "x", "value_y": "y"})

    if len(merged) < 3:
        st.warning(f"Only {len(merged)} counties matched. Need at least 3.")
        return

    # Compute correlation (#8 Spearman toggle)
    try:
        from scipy import stats as sp_stats
        if method == "Spearman":
            r, p = sp_stats.spearmanr(merged["x"], merged["y"])
        else:
            r, p = sp_stats.pearsonr(merged["x"], merged["y"])
    except ImportError:
        r = merged["x"].corr(merged["y"])
        p = None

    # KPI row
    k1, k2, k3 = st.columns(3)
    with k1:
        strength = "Strong" if abs(r) >= 0.6 else "Moderate" if abs(r) >= 0.3 else "Weak"
        direction = "Positive" if r > 0 else "Negative"
        st.metric(f"{method} Correlation (r)", f"{r:.3f}", f"{strength} {direction}")
    with k2:
        if p is not None:
            sig = "✅ Significant" if p < 0.05 else "❌ Not significant"
            st.metric("p-value", f"{p:.4f}", sig)
        else:
            st.metric("p-value", "N/A")
    with k3:
        st.metric("Counties Matched", f"{len(merged)}")

    # Scatter
    scatter = (
        alt.Chart(merged).mark_circle(size=80, opacity=0.7, color=PAL[0])
        .encode(
            x=alt.X("x:Q", title=x_label),
            y=alt.Y("y:Q", title=y_label),
            tooltip=[
                alt.Tooltip("county:N", title="County"),
                alt.Tooltip("x:Q", title=x_label, format=",.2f"),
                alt.Tooltip("y:Q", title=y_label, format=",.2f"),
            ],
        )
    )
    reg_line = scatter.transform_regression("x", "y").mark_line(
        color=PAL[3], strokeDash=[4, 4], strokeWidth=2)
    labels = (
        alt.Chart(merged)
        .mark_text(align="left", dx=8, dy=-4, fontSize=10, color="#666")
        .encode(x="x:Q", y="y:Q", text="county:N")
    )
    chart = (scatter + reg_line + labels).properties(height=500).interactive()
    st.altair_chart(chart, use_container_width=True)

    # Download + table
    col_dl, col_tbl = st.columns([1, 3])
    with col_dl:
        st.download_button(
            "📥 Download data",
            data=merged[["county", "x", "y"]].rename(
                columns={"x": x_label, "y": y_label}
            ).to_csv(index=False).encode(),
            file_name="research_lab_data.csv", mime="text/csv",
        )
    with col_tbl:
        with st.expander("📊 View data table"):
            display = merged[["county", "x", "y"]].copy()
            display.columns = ["County", x_label, y_label]
            st.dataframe(display.sort_values("County"), use_container_width=True, hide_index=True)


# ────────────────────────────────────────────────────────
#  Multi-Variable Regression (#11)
# ────────────────────────────────────────────────────────
def _render_multi_regression(all_vars, census, fir, broadband, survey, geo):
    st.subheader("Multi-Variable Regression")
    st.markdown(
        "Add a **control variable** to see partial correlations. "
        "This answers: *'Is X correlated with Y, after controlling for Z?'*"
    )

    sorted_keys = sorted(all_vars.keys(), key=lambda k: all_vars[k])
    var_labels = {k: all_vars[k] for k in sorted_keys}

    c1, c2, c3 = st.columns(3)
    with c1:
        dep_key = st.selectbox("Dependent (Y)", sorted_keys,
                                format_func=lambda k: var_labels[k], index=0, key="mr_y")
    with c2:
        ind_key = st.selectbox("Independent (X)", sorted_keys,
                                format_func=lambda k: var_labels[k],
                                index=min(1, len(sorted_keys) - 1), key="mr_x")
    with c3:
        ctrl_key = st.selectbox("Control (Z)", sorted_keys,
                                 format_func=lambda k: var_labels[k],
                                 index=min(2, len(sorted_keys) - 1), key="mr_z")

    yc1, yc2 = st.columns(2)
    with yc1:
        census_year = st.selectbox("Census year", [2021, 2016, 2011, 2006], index=0, key="mr_cy")
    with yc2:
        fir_years = sorted(fir["year"].dropna().unique(), reverse=True)
        fir_year = st.selectbox("FIR year", fir_years, index=0, key="mr_fy")

    y_data = _extract_variable(dep_key, census, fir, broadband, survey, geo, census_year, fir_year)
    x_data = _extract_variable(ind_key, census, fir, broadband, survey, geo, census_year, fir_year)
    z_data = _extract_variable(ctrl_key, census, fir, broadband, survey, geo, census_year, fir_year)

    if x_data.empty or y_data.empty or z_data.empty:
        st.warning("One or more variables returned no data.")
        return

    merged = (
        x_data.rename(columns={"value": "x"})
        .merge(y_data.rename(columns={"value": "y"}), on="county")
        .merge(z_data.rename(columns={"value": "z"}), on="county")
        .dropna()
    )

    if len(merged) < 5:
        st.warning(f"Only {len(merged)} counties matched. Need at least 5.")
        return

    try:
        from scipy import stats as sp_stats

        # Simple correlations
        r_xy, p_xy = sp_stats.pearsonr(merged["x"], merged["y"])
        r_xz, p_xz = sp_stats.pearsonr(merged["x"], merged["z"])
        r_yz, p_yz = sp_stats.pearsonr(merged["y"], merged["z"])

        # Partial correlation: r_xy.z = (r_xy - r_xz*r_yz) / sqrt((1-r_xz^2)*(1-r_yz^2))
        denom = np.sqrt((1 - r_xz**2) * (1 - r_yz**2))
        partial_r = (r_xy - r_xz * r_yz) / denom if denom > 0 else 0

        # Approximate t-test for partial correlation
        n = len(merged)
        t_stat = partial_r * np.sqrt((n - 3) / (1 - partial_r**2)) if abs(partial_r) < 1 else 0
        partial_p = 2 * sp_stats.t.sf(abs(t_stat), df=n - 3)

    except ImportError:
        st.error("scipy is required for multi-variable regression. Install with `pip install scipy`.")
        return

    # Results
    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Simple r(X,Y)", f"{r_xy:.3f}",
                  "✅ Sig" if p_xy < 0.05 else "❌ Not sig")
    with k2:
        st.metric("Partial r(X,Y|Z)", f"{partial_r:.3f}",
                  "✅ Sig" if partial_p < 0.05 else "❌ Not sig")
    with k3:
        change = partial_r - r_xy
        if abs(change) > 0.1:
            interp = "🔄 Z is a confound" if abs(partial_r) < abs(r_xy) else "📈 Z strengthens link"
        else:
            interp = "➡️ Z has little effect"
        st.metric("Change when controlling", f"{change:+.3f}", interp)

    st.markdown(f"""
    **Interpretation**: The simple correlation between X and Y is **{r_xy:.3f}**. 
    After controlling for Z, it {'weakens' if abs(partial_r) < abs(r_xy) else 'strengthens'} 
    to **{partial_r:.3f}** (p={partial_p:.4f}).
    {'This suggests Z partially explains the X-Y relationship.' if abs(partial_r) < abs(r_xy) * 0.7 else ''}
    """)

    # Show scatter anyway (X vs Y, coloured by Z)
    merged["z_bin"] = pd.qcut(merged["z"], q=3, labels=["Low Z", "Mid Z", "High Z"], duplicates="drop")
    scatter = (
        alt.Chart(merged)
        .mark_circle(size=80, opacity=0.7)
        .encode(
            x=alt.X("x:Q", title=var_labels.get(ind_key, ind_key)),
            y=alt.Y("y:Q", title=var_labels.get(dep_key, dep_key)),
            color=alt.Color("z_bin:N", title=var_labels.get(ctrl_key, "Control"),
                           scale=alt.Scale(range=[PAL[0], PAL[2], PAL[3]])),
            tooltip=[
                alt.Tooltip("county:N", title="County"),
                alt.Tooltip("x:Q", format=",.2f"),
                alt.Tooltip("y:Q", format=",.2f"),
                alt.Tooltip("z:Q", format=",.2f"),
            ],
        ).properties(height=450).interactive()
    )
    st.altair_chart(scatter, use_container_width=True)


main()

from app.utils import global_footer
global_footer()
