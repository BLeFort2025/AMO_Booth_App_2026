"""
📋 OFA Member Surveys — page 12.

Visualises OFA member survey data with polished, dashboard-grade views
for every survey dataset, plus cross-cutting analysis tools.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
from app.smart_read import smart_read
import streamlit as st

# ── path bootstrap ──────────────────────────────────────
_PROJECT = Path(__file__).resolve().parents[2]
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

SURVEY_DIR = _PROJECT / "data" / "surveys"

st.set_page_config(page_title="OFA Member Surveys", page_icon="📋", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()



# ── data loading ────────────────────────────────────────
@st.cache_data(max_entries=3, ttl=600)
def load_confidence_panel() -> pd.DataFrame:
    fp = SURVEY_DIR / "confidence_panel.csv"
    return smart_read(fp) if fp.exists() else pd.DataFrame()

@st.cache_data(max_entries=3, ttl=600)
def load_insurance() -> pd.DataFrame:
    fp = SURVEY_DIR / "insurance_2025.csv"
    return smart_read(fp) if fp.exists() else pd.DataFrame()

@st.cache_data(max_entries=3, ttl=600)
def load_giant_bucket() -> pd.DataFrame:
    fp = SURVEY_DIR / "giant_bucket_cleaned.csv"
    return smart_read(fp) if fp.exists() else pd.DataFrame()


# ── constants ───────────────────────────────────────────
CONFIDENCE_SCORES = {
    "Extremely confident": 5, "Very confident": 4, "Somewhat confident": 3,
    "Not so confident": 2, "Not at all confident": 1,
}
GROWTH_SCORES = {
    "Expand": 3, "Expanded": 3, "Stay the same": 2, "Stayed the same": 2,
    "Contract": 1, "Contracted": 1,
}
INCOME_ORDER = [
    "Under $10,000", "$10,000 to $49,999", "$10,000 to $49,000",
    "$50,000 to $99,999", "$100,000 to $249,999", "$250,000 to $499,999",
    "$500,000 to $999,999", "$1,000,000 and above",
    "$1,000,000 to $1,999,999", "$2,000,000 and above",
]
PAL = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899",
       "#14B8A6", "#F97316", "#6366F1", "#84CC16"]


def _score(s: pd.Series, m: dict) -> pd.Series:
    return s.map(m)

def _pct(series: pd.Series, condition) -> float:
    clean = series.dropna()
    if len(clean) == 0:
        return 0.0
    return condition(clean).sum() / len(clean) * 100

def _bar(df: pd.DataFrame, x: str, y: str, color=PAL[0], height=350) -> alt.Chart:
    """Standard horizontal bar chart."""
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=color)
        .encode(
            x=alt.X(f"{x}:Q", title=""),
            y=alt.Y(f"{y}:N", sort="-x", title=""),
            tooltip=[f"{y}:N", f"{x}:Q"],
        ).properties(height=height)
    )

def _donut(df: pd.DataFrame, theta: str, color_col: str, height=350) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_arc(innerRadius=60, cornerRadius=4)
        .encode(
            theta=alt.Theta(f"{theta}:Q"),
            color=alt.Color(f"{color_col}:N", scale=alt.Scale(range=PAL)),
            tooltip=[f"{color_col}:N", f"{theta}:Q"],
        ).properties(height=height)
    )

def _yes_no_pct(s: pd.Series) -> float:
    """% of Yes answers, handling YES/Yes/yes variations."""
    clean = s.dropna().astype(str).str.strip().str.lower()
    clean = clean[clean.isin(["yes", "no"])]
    if len(clean) == 0:
        return 0.0
    return (clean == "yes").sum() / len(clean) * 100


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_numeric_only(val: str) -> bool:
    """True if string is purely numeric (row-number artifact)."""
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


# ────────────────────────────────────────────────────────
#  GIANT BUCKET: Parse sub-survey
# ────────────────────────────────────────────────────────
def _parse_sub_survey(gb: pd.DataFrame, anchor_col: str) -> pd.DataFrame:
    idx = gb.columns.get_loc(anchor_col)
    cols = [anchor_col]
    for j in range(idx + 1, len(gb.columns)):
        if str(gb.columns[j]).startswith("Unnamed:"):
            cols.append(gb.columns[j])
        else:
            break
    sub = gb[cols].copy()
    if len(sub) > 1:
        new_names = sub.iloc[0].fillna("").astype(str).tolist()
        seen = {}
        unique_names = []
        for n in new_names:
            n = n[:120]
            if n in seen:
                seen[n] += 1
                unique_names.append(f"{n}_{seen[n]}")
            else:
                seen[n] = 0
                unique_names.append(n)
        sub.columns = unique_names
        sub = sub.iloc[1:].reset_index(drop=True)
    # Drop rows that are all empty
    sub = sub.dropna(how="all").reset_index(drop=True)
    return sub


# ────────────────────────────────────────────────────────
#  Rich sub-survey renderer
# ────────────────────────────────────────────────────────
def _render_rich_survey(sub: pd.DataFrame, title: str, icon: str = "📊"):
    """Render any sub-survey with the same quality as the confidence tab."""

    # Strip HTML from column names
    rename_map = {c: _strip_html(c) for c in sub.columns}
    sub = sub.rename(columns=rename_map)

    # Identify question columns (non-trivial names)
    q_cols = [c for c in sub.columns if c and len(c) > 8
              and c not in ("", "nan") and not c.startswith("Unnamed")]

    if not q_cols:
        st.info("No question data available.")
        return

    # Classify columns: yes/no categorical, multi-choice, or free-text
    yn_cols = []  # Yes/No questions
    cat_cols = []  # Categorical with few unique values
    free_cols = []  # Free text / many unique
    county_col = None

    for c in q_cols:
        vals = sub[c].dropna().astype(str).str.strip()
        # Filter out numeric-only values (row-number artifacts from parsing)
        vals = vals[~vals.apply(_is_numeric_only)]
        vals = vals[~vals.isin(["", "nan", "Response", "Open-Ended Response"])]
        if len(vals) == 0:
            continue
        n_uniq = vals.nunique()

        # Detect county column
        lower_vals = vals.str.lower()
        if n_uniq > 20 and any(k in c.lower() for k in ["county", "federation", "region"]):
            county_col = c
            continue

        # Detect income/gross farm income column
        if any(k in c.lower() for k in ["gross farm income", "farm sales", "income range"]):
            cat_cols.append(c)
            continue

        if n_uniq <= 2:
            yeses = lower_vals.isin(["yes", "no"]).sum()
            if yeses / len(vals) > 0.7:
                yn_cols.append(c)
            else:
                cat_cols.append(c)
        elif n_uniq <= 15:
            cat_cols.append(c)
        else:
            free_cols.append(c)

    # ── KPI Cards Row ──
    n_respondents = len(sub)
    n_questions = len(yn_cols) + len(cat_cols) + len(free_cols)
    n_counties = sub[county_col].nunique() if county_col else 0

    kc1, kc2, kc3 = st.columns(3)
    with kc1:
        st.metric("Total Respondents", f"{n_respondents:,}")
    with kc2:
        st.metric("Questions Analyzed", f"{n_questions}")
    with kc3:
        if n_counties > 0:
            st.metric("Counties Represented", f"{n_counties}")
        else:
            st.metric("Yes/No Questions", f"{len(yn_cols)}")

    st.divider()

    # ── Yes/No Summary Panel ──
    if yn_cols:
        st.subheader("📊 Key Findings (Yes/No Questions)")
        # Show yes/no questions as a summary bar chart
        yn_data = []
        for c in yn_cols:
            pct_yes = _yes_no_pct(sub[c])
            short_name = c[:80]
            yn_data.append({"Question": short_name, "% Yes": round(pct_yes, 1)})

        yn_df = pd.DataFrame(yn_data).sort_values("% Yes", ascending=False)

        chart = (
            alt.Chart(yn_df)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("% Yes:Q", scale=alt.Scale(domain=[0, 100]), title="% Yes"),
                y=alt.Y("Question:N", sort="-x", title=""),
                color=alt.Color("% Yes:Q",
                    scale=alt.Scale(scheme="blueorange", domain=[0, 100]),
                    legend=None),
                tooltip=["Question:N", alt.Tooltip("% Yes:Q", format=".1f")],
            ).properties(height=max(200, len(yn_df) * 30))
        )
        st.altair_chart(chart, use_container_width=True)
        st.divider()

    # ── Categorical Question Charts ──
    if cat_cols:
        st.subheader("📋 Detailed Breakdowns")

        # Render in pairs (2 columns)
        pairs = [(cat_cols[i], cat_cols[i + 1] if i + 1 < len(cat_cols) else None)
                 for i in range(0, len(cat_cols), 2)]

        for left_col, right_col in pairs:
            cols_layout = st.columns(2) if right_col else [st.columns(1)[0]]

            for col_layout, q_col in zip(cols_layout, [left_col, right_col]):
                if q_col is None:
                    break
                with col_layout:
                    vals = sub[q_col].dropna().astype(str).str.strip()
                    vals = vals[~vals.apply(_is_numeric_only)]
                    vals = vals[~vals.isin(["", "nan", "Response", "Open-Ended Response"])]
                    if vals.empty:
                        continue

                    dist = vals.value_counts().head(12).reset_index()
                    dist.columns = ["Response", "Count"]
                    n_uniq = len(dist)

                    short_title = _strip_html(q_col[:65] + ("..." if len(q_col) > 65 else ""))
                    st.markdown(f"**{short_title}**")

                    if n_uniq <= 5:
                        # Donut chart for small number of categories
                        ch = _donut(dist, "Count", "Response", height=250)
                    else:
                        ch = _bar(dist, "Count", "Response",
                                  color=PAL[cat_cols.index(q_col) % len(PAL)],
                                  height=min(280, max(150, n_uniq * 28)))
                    st.altair_chart(ch, use_container_width=True)

        st.divider()

    # ── County Breakdown (if county column exists) ──
    if county_col:
        st.subheader("🗺️ Responses by County")
        county_dist = sub[county_col].dropna().value_counts().head(25).reset_index()
        county_dist.columns = ["County", "Responses"]
        chart = _bar(county_dist, "Responses", "County", color=PAL[4],
                     height=max(250, len(county_dist) * 22))
        st.altair_chart(chart, use_container_width=True)
        st.divider()


    # ── Download ──
    st.download_button(
        f"📥 Download {title} data (CSV)",
        data=sub.to_csv(index=False).encode("utf-8"),
        file_name=f"ofa_{title.lower().replace(' ','_')}.csv",
        mime="text/csv",
    )


# ════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════

# Giant Bucket survey display names & config
GB_SURVEYS = {
    "business_advisory.csv": ("🏢 Business Advisory Services",
        "Advisory services usage among OFA members — accounting, business planning, succession, and HR."),
    "demand_response": ("⚡ Energy Demand Response",
        "Backup generator ownership and interest in grid contribution among Ontario farms."),
    "farm_rental.csv": ("🌾 Farmland Rental",
        "Land rental practices — lease terms, rental rates, and farming practice impacts."),
    "internet_telecommunications.csv": ("🌐 Internet & Telecom",
        "Rural internet connectivity quality, provider satisfaction, and telecommuting capability."),
    "precision_tech.csv": ("🤖 Precision Agriculture",
        "Technology adoption — GPS guidance, variable-rate application, drones, robotics, and data analytics."),
    "property_assessment.csv": ("🏠 Property Assessment (MPAC)",
        "MPAC property assessment experiences — accuracy, appeal rates, and satisfaction."),
    "risk_management_10.csv": ("🛡️ Risk Management (BRM Programs)",
        "Business Risk Management program participation — AgriStability, AgriInsurance, AgriInvest."),
    "risk_management_14.csv": ("🛡️ Risk Management (Detailed)",
        "Extended risk management data — coverage adequacy, claims experience, program improvements."),
    "Building the ideal relationship survey 2020": ("🤝 Ideal Relationship (2020)",
        "Member satisfaction with OFA services, communication, and advocacy."),
}


def main():
    st.title("📋 OFA Member Surveys")
    st.markdown(
        "Explore OFA member survey data with **detailed dashboards** for each survey topic, "
        "**cross-segment analysis** across any survey, and **methodology notes** for all datasets."
    )

    gb = load_giant_bucket()
    named_cols = [c for c in gb.columns if not c.startswith("Unnamed:")] if not gb.empty else []

    # Build tab list: Confidence, Insurance, each sub-survey, Cross-Segment, Methodology
    tab_names = ["🔵 Farm Business Confidence", "🟢 Farm Insurance"]
    sub_survey_map = {}  # tab_index -> anchor_col
    for anchor in named_cols:
        if anchor in GB_SURVEYS:
            label, _ = GB_SURVEYS[anchor]
            tab_names.append(label)
            sub_survey_map[len(tab_names) - 1] = anchor

    tab_names.extend(["🔀 Cross-Segment Analysis", "📐 Methodology & Notes"])
    tabs = st.tabs(tab_names)

    # ── Tab 0: Confidence ──
    with tabs[0]:
        _render_confidence_tab()

    # ── Tab 1: Insurance ──
    with tabs[1]:
        _render_insurance_tab()

    # ── Sub-survey tabs ──
    for tab_idx, anchor in sub_survey_map.items():
        with tabs[tab_idx]:
            title, desc = GB_SURVEYS[anchor]
            st.subheader(title)
            st.markdown(desc)
            if gb.empty:
                st.warning("Giant_Bucket_CLEANED.csv not found.")
                continue
            sub = _parse_sub_survey(gb, anchor)
            if sub.empty:
                st.info("No data available.")
                continue
            _render_rich_survey(sub, title.split(" ", 1)[-1])

    # ── Cross-Segment Analysis ──
    with tabs[-2]:
        _render_segment_tab()

    # ── Methodology ──
    with tabs[-1]:
        _render_methodology_tab()


# ────────────────────────────────────────────────────────
#  CONFIDENCE TAB
# ────────────────────────────────────────────────────────
def _render_confidence_tab():
    panel = load_confidence_panel()
    if panel.empty:
        st.warning("Confidence panel data not found. Run `python scripts/etl_surveys.py` first.")
        return

    # ── Filters ──
    f1, f2, f3 = st.columns(3)
    with f1:
        years = sorted(panel["year"].unique())
        sel_years = st.multiselect("Survey Year", years, default=years, key="conf_years")
    with f2:
        counties = sorted(panel["county"].dropna().unique())
        sel_counties = st.multiselect("County", counties, default=[], key="conf_counties",
                                      placeholder="All counties")
    with f3:
        incomes = [i for i in INCOME_ORDER if i in panel["gross_income"].unique()]
        sel_incomes = st.multiselect("Gross Farm Income", incomes, default=[], key="conf_income",
                                     placeholder="All income brackets")

    filt = panel[panel["year"].isin(sel_years)]
    if sel_counties:
        filt = filt[filt["county"].isin(sel_counties)]
    if sel_incomes:
        filt = filt[filt["gross_income"].isin(sel_incomes)]

    st.caption(f"Showing **{len(filt):,}** responses across **{filt['county'].nunique()}** counties")
    if filt.empty:
        st.info("No data matches the current filters.")
        return

    # ── KPIs with YoY deltas ──
    filt_scored = filt.copy()
    filt_scored["conf_score"] = _score(filt_scored["confidence_outlook"], CONFIDENCE_SCORES)
    filt_scored["growth_score"] = _score(filt_scored["growth_expectation"], GROWTH_SCORES)
    conf_s = filt_scored["conf_score"].dropna()
    growth_s = filt_scored["growth_score"].dropna()
    avg_conf = conf_s.mean() if len(conf_s) else 0
    pct_confident = _pct(conf_s, lambda s: s >= 4)
    pct_expand = _pct(growth_s, lambda s: s >= 3)

    latest = max(sel_years)
    prev = latest - 1
    delta_conf = delta_expand = None
    if prev in filt["year"].unique():
        p_data = filt_scored[filt_scored["year"] == prev]
        c_data = filt_scored[filt_scored["year"] == latest]
        p_conf = _score(p_data["confidence_outlook"], CONFIDENCE_SCORES).dropna().mean()
        c_conf = _score(c_data["confidence_outlook"], CONFIDENCE_SCORES).dropna().mean()
        delta_conf = c_conf - p_conf if (p_conf and c_conf) else None
        p_exp = _pct(p_data["growth_score"].dropna(), lambda s: s >= 3)
        c_exp = _pct(c_data["growth_score"].dropna(), lambda s: s >= 3)
        delta_expand = c_exp - p_exp

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Avg Confidence Score", f"{avg_conf:.2f} / 5.0",
                  f"{delta_conf:+.2f} vs {prev}" if delta_conf is not None else None)
    with k2:
        st.metric("% Very/Extremely Confident", f"{pct_confident:.0f}%")
    with k3:
        st.metric("% Planning to Expand", f"{pct_expand:.0f}%",
                  f"{delta_expand:+.0f}pp vs {prev}" if delta_expand is not None else None)
    with k4:
        st.metric("Total Respondents", f"{len(filt):,}")

    st.divider()

    # ── Confidence trend + distribution ──
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        st.subheader("Confidence Trend (2023–2025)")
        yearly = filt_scored.groupby("year")["conf_score"].mean().reset_index()
        yearly.columns = ["Year", "Avg Confidence"]
        ch = (
            alt.Chart(yearly).mark_line(point=True, strokeWidth=3, color=PAL[0])
            .encode(
                x=alt.X("Year:O", title="Survey Year"),
                y=alt.Y("Avg Confidence:Q", scale=alt.Scale(domain=[1, 5]), title="Avg Score (1-5)"),
                tooltip=["Year:O", alt.Tooltip("Avg Confidence:Q", format=".2f")],
            ).properties(height=320)
        )
        st.altair_chart(ch, use_container_width=True)

    with r1c2:
        st.subheader("Confidence Distribution")
        conf_dist = (filt["confidence_outlook"].dropna().value_counts()
                     .reindex(list(CONFIDENCE_SCORES.keys())).dropna().reset_index())
        conf_dist.columns = ["Outlook", "Count"]
        ch2 = (
            alt.Chart(conf_dist).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("Outlook:N", sort=list(CONFIDENCE_SCORES.keys()), title=""),
                y=alt.Y("Count:Q", title="Respondents"),
                color=alt.Color("Outlook:N", scale=alt.Scale(
                    domain=list(CONFIDENCE_SCORES.keys()),
                    range=["#1E40AF", "#2563EB", "#F59E0B", "#EF4444", "#991B1B"]),
                    legend=None),
                tooltip=["Outlook:N", "Count:Q"],
            ).properties(height=320)
        )
        st.altair_chart(ch2, use_container_width=True)

    st.divider()

    # ── Age & Structure ──
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        st.subheader("Respondent Age Distribution")
        ages = filt["age"].dropna()
        ages = ages[~ages.isin(["Response", ""])]
        if not ages.empty:
            age_dist = ages.value_counts().reset_index()
            age_dist.columns = ["Age Range", "Count"]
            st.altair_chart(_bar(age_dist, "Count", "Age Range", PAL[6], 250),
                           use_container_width=True)

    with r2c2:
        st.subheader("Farm Business Structure")
        structs = filt["farm_structure"].dropna()
        structs = structs[~structs.isin(["Response", ""])]
        if not structs.empty:
            sd = structs.value_counts().reset_index()
            sd.columns = ["Structure", "Count"]
            st.altair_chart(_donut(sd, "Count", "Structure", 280), use_container_width=True)

    st.divider()

    # ── Challenges + Policies ──
    r3c1, r3c2 = st.columns(2)
    with r3c1:
        st.subheader("Top Challenges")
        ch_data = filt["challenges"].dropna().str.split(";").explode().str.strip()
        ch_data = ch_data[ch_data != ""]
        if not ch_data.empty:
            top = ch_data.value_counts().head(12).reset_index()
            top.columns = ["Challenge", "Mentions"]
            st.altair_chart(_bar(top, "Mentions", "Challenge", PAL[3], 400),
                           use_container_width=True)
    with r3c2:
        st.subheader("Policy Priorities")
        pol = filt["policy_priorities"].dropna().str.split(";").explode().str.strip()
        pol = pol[pol != ""]
        if not pol.empty:
            top = pol.value_counts().head(12).reset_index()
            top.columns = ["Policy", "Mentions"]
            st.altair_chart(_bar(top, "Mentions", "Policy", PAL[0], 400),
                           use_container_width=True)

    st.divider()

    # ── Heatmap + Tax ──
    r4c1, r4c2 = st.columns([3, 2])
    with r4c1:
        st.subheader("Confidence Heatmap: County × Year")
        heat = filt_scored.groupby(["county", "year"])["conf_score"].mean().reset_index()
        heat.columns = ["County", "Year", "Score"]
        if not heat.empty:
            hm = (
                alt.Chart(heat).mark_rect(cornerRadius=3)
                .encode(
                    x=alt.X("Year:O", title=""),
                    y=alt.Y("County:N", sort=alt.EncodingSortField("Score", order="descending"), title=""),
                    color=alt.Color("Score:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[1, 5]),
                                    legend=alt.Legend(title="Score")),
                    tooltip=["County:N", "Year:O", alt.Tooltip("Score:Q", format=".2f")],
                ).properties(height=max(400, heat["County"].nunique() * 16))
            )
            st.altair_chart(hm, use_container_width=True)

    with r4c2:
        st.subheader("Most Impactful Tax Type")
        tax = filt["tax_impact"].dropna()
        tax = tax[~tax.str.lower().isin(["response", ""])]
        if not tax.empty:
            td = tax.value_counts().reset_index()
            td.columns = ["Tax Type", "Respondents"]
            st.altair_chart(_donut(td, "Respondents", "Tax Type", 400), use_container_width=True)
        else:
            st.info("Tax impact data only available for select years.")

    # ── Commodities ──
    st.divider()
    st.subheader("Commodity Production Mix")
    comm = filt["commodities"].dropna().str.split(";").explode().str.strip()
    comm = comm[~comm.isin(["", "nan", "Response", "Open-Ended Response"])]
    if not comm.empty:
        top = comm.value_counts().head(20).reset_index()
        top.columns = ["Commodity", "Producers"]
        st.altair_chart(_bar(top, "Producers", "Commodity", PAL[1], 500),
                       use_container_width=True)

    # ── YoY Alert Scanner ──
    st.divider()
    _render_confidence_alert_scanner(panel, sel_years)

    st.divider()
    st.download_button("📥 Download filtered confidence data (CSV)",
        data=filt.to_csv(index=False).encode("utf-8"),
        file_name="ofa_confidence_filtered.csv", mime="text/csv")


# ────────────────────────────────────────────────────────
#  YoY ALERT SCANNER (moved from Research Lab)
# ────────────────────────────────────────────────────────
def _render_confidence_alert_scanner(panel: pd.DataFrame, sel_years: list):
    """Flag counties with significant YoY confidence shifts."""
    st.subheader("🚨 Year-over-Year Confidence Alerts")
    st.markdown(
        "Automatically flags counties where confidence **dropped significantly** "
        "or where **key challenges spiked** between survey years."
    )

    if panel.empty:
        st.warning("No confidence panel data available.")
        return

    survey_c = panel.copy()
    survey_c["score"] = survey_c["confidence_outlook"].map(CONFIDENCE_SCORES)
    years = sorted(survey_c["year"].unique())

    if len(years) < 2:
        st.info("Need at least 2 survey years for YoY comparison.")
        return

    c1, c2 = st.columns(2)
    with c1:
        yr_from = st.selectbox("Compare from", years[:-1], index=0, key="alert_from")
    with c2:
        yr_to = st.selectbox("Compare to", [y for y in years if y > yr_from],
                              index=0, key="alert_to")

    threshold = st.slider("Alert threshold (score drop)", 0.1, 2.0, 0.5, 0.1)

    from_data = survey_c[survey_c["year"] == yr_from].groupby("county").agg(
        avg_score=("score", "mean"), n=("score", "count")).reset_index()
    to_data = survey_c[survey_c["year"] == yr_to].groupby("county").agg(
        avg_score=("score", "mean"), n=("score", "count")).reset_index()

    compare = from_data.merge(to_data, on="county", suffixes=("_from", "_to"))
    compare["delta"] = compare["avg_score_to"] - compare["avg_score_from"]
    compare["min_sample"] = compare[["n_from", "n_to"]].min(axis=1)

    # Filter to counties with reasonable samples
    compare = compare[compare["min_sample"] >= 5]

    # Alerts: significant drops
    alerts = compare[compare["delta"] <= -threshold].sort_values("delta")
    improving = compare[compare["delta"] >= threshold].sort_values("delta", ascending=False)

    ac1, ac2 = st.columns(2)

    with ac1:
        st.markdown(f"### 🔴 Declining ({len(alerts)} counties)")
        if not alerts.empty:
            for _, row in alerts.iterrows():
                st.error(
                    f"**{row['county']}** — "
                    f"{row['avg_score_from']:.2f} → {row['avg_score_to']:.2f} "
                    f"({row['delta']:+.2f}) "
                    f"[n={row['n_from']:.0f}→{row['n_to']:.0f}]"
                )
        else:
            st.success(f"No counties dropped by ≥ {threshold:.1f} points.")

    with ac2:
        st.markdown(f"### 🟢 Improving ({len(improving)} counties)")
        if not improving.empty:
            for _, row in improving.iterrows():
                st.success(
                    f"**{row['county']}** — "
                    f"{row['avg_score_from']:.2f} → {row['avg_score_to']:.2f} "
                    f"({row['delta']:+.2f}) "
                    f"[n={row['n_from']:.0f}→{row['n_to']:.0f}]"
                )
        else:
            st.info(f"No counties improved by ≥ {threshold:.1f} points.")

    # Summary chart
    if not compare.empty:
        st.divider()
        st.subheader(f"All County Changes ({yr_from} → {yr_to})")
        compare_sorted = compare.sort_values("delta")
        chart = (
            alt.Chart(compare_sorted)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("delta:Q", title=f"Change in Avg Confidence ({yr_from}→{yr_to})"),
                y=alt.Y("county:N", sort=alt.EncodingSortField("delta", order="ascending"), title=""),
                color=alt.condition(
                    alt.datum.delta < 0,
                    alt.value(PAL[3]),  # red for decline
                    alt.value(PAL[1]),  # green for improvement
                ),
                tooltip=[
                    "county:N",
                    alt.Tooltip("avg_score_from:Q", title=f"{yr_from} Score", format=".2f"),
                    alt.Tooltip("avg_score_to:Q", title=f"{yr_to} Score", format=".2f"),
                    alt.Tooltip("delta:Q", title="Change", format="+.2f"),
                ],
            ).properties(height=max(400, len(compare_sorted) * 16))
        )
        st.altair_chart(chart, use_container_width=True)


# ────────────────────────────────────────────────────────
#  INSURANCE TAB
# ────────────────────────────────────────────────────────
def _render_insurance_tab():
    ins = load_insurance()
    if ins.empty:
        st.warning("Insurance data not found. Run `python scripts/etl_surveys.py` first.")
        return

    st.subheader("Farm Insurance Survey 2025")
    st.caption(f"**{len(ins):,}** respondents across **{ins['county'].nunique()}** counties")

    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Total Respondents", f"{len(ins):,}")
    with k2:
        if "drao_received" in ins:
            st.metric("% Received DRAO", f"{_yes_no_pct(ins['drao_received']):.1f}%")
    with k3:
        if "has_agritourism" in ins:
            st.metric("% Has Agritourism", f"{_yes_no_pct(ins['has_agritourism']):.1f}%")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Insurance Coverage Types")
        ins_types = ins["insurance_types"].dropna().str.split(";").explode().str.strip()
        ins_types = ins_types[~ins_types.isin(["", "nan", "Response"])]
        if not ins_types.empty:
            top = ins_types.value_counts().head(12).reset_index()
            top.columns = ["Type", "Count"]
            st.altair_chart(_bar(top, "Count", "Type", PAL[1], 400), use_container_width=True)
    with c2:
        st.subheader("Responses by County")
        cd = ins["county"].value_counts().head(20).reset_index()
        cd.columns = ["County", "Responses"]
        st.altair_chart(_bar(cd, "Responses", "County", PAL[4], 400), use_container_width=True)

    st.divider()
    st.download_button("📥 Download insurance data (CSV)",
        data=ins.to_csv(index=False).encode("utf-8"),
        file_name="ofa_insurance_2025.csv", mime="text/csv")


# ────────────────────────────────────────────────────────
#  CROSS-SEGMENT ANALYSIS (works across ALL surveys)
# ────────────────────────────────────────────────────────
def _render_segment_tab():
    st.subheader("Cross-Segment Comparison")
    st.markdown(
        "Compare responses between two farmer segments across **any survey dataset**. "
        "Select a survey, choose how to segment, and compare."
    )

    # Survey selector
    panel = load_confidence_panel()
    ins = load_insurance()
    gb = load_giant_bucket()

    survey_options = []
    if not panel.empty:
        survey_options.append("Farm Business Confidence (2023-2025)")
    if not ins.empty:
        survey_options.append("Farm Insurance (2025)")

    if not survey_options:
        st.warning("No survey data available.")
        return

    selected_survey = st.selectbox("Select survey to analyze", survey_options, key="seg_survey")

    if selected_survey.startswith("Farm Business Confidence"):
        data = panel
        seg_options = {"gross_income": "Gross Farm Income", "age": "Respondent Age",
                       "farm_structure": "Farm Business Structure", "year": "Survey Year"}
        metric_fn = lambda d: {
            "Avg Confidence": f"{_score(d['confidence_outlook'], CONFIDENCE_SCORES).dropna().mean():.2f}",
            "% Expanding": f"{_pct(_score(d['growth_expectation'], GROWTH_SCORES).dropna(), lambda s: s >= 3):.0f}%",
            "Respondents": f"{len(d):,}",
        }
        compare_cols = {"challenges": "Top Challenges", "policy_priorities": "Policy Priorities"}
    else:
        data = ins
        seg_options = {"county": "County", "gross_income": "Gross Farm Income", "age": "Respondent Age"}
        metric_fn = lambda d: {
            "Respondents": f"{len(d):,}",
            "% DRAO": f"{_yes_no_pct(d.get('drao_received', pd.Series())):.1f}%",
            "% Agritourism": f"{_yes_no_pct(d.get('has_agritourism', pd.Series())):.1f}%",
        }
        compare_cols = {"insurance_types": "Insurance Types"}

    seg_var = st.selectbox("Segment by", list(seg_options.keys()),
                            format_func=lambda k: seg_options[k], key="seg_var")

    vals = data[seg_var].dropna()
    vals = vals[~vals.astype(str).isin(["", "Response"])]
    unique_vals = sorted(vals.unique(), key=str)

    if len(unique_vals) < 2:
        st.info("Not enough segments to compare.")
        return

    c1, c2 = st.columns(2)
    with c1:
        grp_a = st.multiselect("Group A", unique_vals,
                                default=[unique_vals[0]], key="seg_grp_a")
    with c2:
        rem = [v for v in unique_vals if v not in grp_a]
        grp_b = st.multiselect("Group B", unique_vals,
                                default=[rem[-1]] if rem else [], key="seg_grp_b")

    if not grp_a or not grp_b:
        st.info("Select at least one value for each group.")
        return

    a_data = data[data[seg_var].isin(grp_a)]
    b_data = data[data[seg_var].isin(grp_b)]
    a_label = f"Group A ({', '.join(str(v) for v in grp_a)})"
    b_label = f"Group B ({', '.join(str(v) for v in grp_b)})"

    st.divider()

    # Side-by-side KPIs
    mc1, mc2 = st.columns(2)
    for col, d, label in [(mc1, a_data, a_label), (mc2, b_data, b_label)]:
        with col:
            st.markdown(f"**{label}**")
            metrics = metric_fn(d)
            for name, val in metrics.items():
                st.metric(name, val)

    st.divider()

    # Side-by-side charts for comparable columns
    for col_key, title in compare_cols.items():
        if col_key not in data.columns:
            continue
        st.subheader(f"{title} Comparison")
        cc1, cc2 = st.columns(2)
        for col_layout, d, label in [(cc1, a_data, a_label), (cc2, b_data, b_label)]:
            with col_layout:
                vals_data = d[col_key].dropna().str.split(";").explode().str.strip()
                vals_data = vals_data[vals_data != ""]
                if not vals_data.empty:
                    top = vals_data.value_counts().head(8).reset_index()
                    top.columns = [title, "Mentions"]
                    st.altair_chart(
                        _bar(top, "Mentions", title, PAL[3], 280).properties(title=label),
                        use_container_width=True
                    )


# ────────────────────────────────────────────────────────
#  METHODOLOGY (covers ALL surveys)
# ────────────────────────────────────────────────────────
def _render_methodology_tab():
    st.subheader("Methodology & Data Quality Notes")

    st.markdown("""
    #### Survey Design
    All surveys below are administered by the Ontario Federation of Agriculture (OFA)
    to its members. Respondents self-select by completing online surveys distributed
    via email and OFA communications.

    #### Important Caveats

    > **⚠️ Self-Selection Bias**: Respondents are OFA members who chose to participate.
    > Results may not be representative of all Ontario farmers.

    > **⚠️ Small Sample Sizes**: Some surveys and counties have very few respondents.
    > Interpret averages from small samples with caution.

    #### Confidence Scoring (Business Confidence Survey)
    - **5** = Extremely confident &nbsp;•&nbsp; **4** = Very confident &nbsp;•&nbsp;
      **3** = Somewhat confident &nbsp;•&nbsp; **2** = Not so confident &nbsp;•&nbsp;
      **1** = Not at all confident
    """)

    st.divider()
    st.subheader("📊 Survey Inventory & Sample Sizes")

    # Build inventory table
    inventory = []

    panel = load_confidence_panel()
    if not panel.empty:
        for yr, grp in panel.groupby("year"):
            inventory.append({
                "Survey": f"Farm Business Confidence {yr}",
                "Respondents": len(grp),
                "Counties": grp["county"].nunique(),
                "Year": int(yr),
            })

    ins = load_insurance()
    if not ins.empty:
        inventory.append({
            "Survey": "Farm Insurance",
            "Respondents": len(ins),
            "Counties": ins["county"].nunique(),
            "Year": 2025,
        })

    gb = load_giant_bucket()
    if not gb.empty:
        named = [c for c in gb.columns if not c.startswith("Unnamed:")]
        for anchor in named:
            sub = _parse_sub_survey(gb, anchor)
            title = GB_SURVEYS.get(anchor, (anchor, ""))[0]
            inventory.append({
                "Survey": title,
                "Respondents": len(sub),
                "Counties": "–",
                "Year": "Various",
            })

    if inventory:
        inv_df = pd.DataFrame(inventory)
        inv_df["Counties"] = inv_df["Counties"].astype(str)
        inv_df["Year"] = inv_df["Year"].astype(str)
        st.dataframe(inv_df, use_container_width=True, hide_index=True)

    # County × Year matrix for confidence
    if not panel.empty:
        st.divider()
        st.subheader("Confidence Survey: Sample Size by County & Year")
        pivot = panel.groupby(["county", "year"]).size().unstack(fill_value=0)
        pivot["Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("Total", ascending=False)
        pivot.columns = pivot.columns.astype(str)
        st.dataframe(
            pivot.style.map(
                lambda v: "background-color: #FEE2E2" if isinstance(v, (int, float)) and 0 < v < 10 else ""
            ),
            use_container_width=True,
        )
        st.caption("🔴 Red cells = fewer than 10 respondents (interpret with caution)")


main()

from app.utils import global_footer
global_footer()
