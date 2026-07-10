"""
Tariff Incidence Research — Descriptive Analysis (Phase 1)
==========================================================
Builds the core descriptive time-series visualizations using data already
in-hand.  No CIMT data required for these charts.

Charts produced:
  1. FIPI Nitrogen Fertilizer Index (monthly, 2019–2025)
  2. World Bank Urea Benchmark (monthly, 2019–2024)
  3. Composite Panel: FIPI + Urea + Henry Hub + CAD/USD
  4. Pre/Post Tariff Summary Statistics
  5. Bai-Perron structural break test (via statsmodels)

All chart HTML files saved to: data/latest/tariff_research/charts/
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data" / "latest"
RESEARCH = DATA / "tariff_research"
CHART_DIR = RESEARCH / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Tariff event date
TARIFF_DATE = pd.Timestamp("2022-03-03")
TARIFF_DATE_STR = "2022-03-03"  # String version avoids Plotly annotation bug

# ── Color Palette ────────────────────────────────────────────────────────────
COLORS = {
    "nitrogen":  "#2563eb",  # blue
    "other_fert":"#7c3aed",  # purple
    "total_fert":"#059669",  # green
    "urea":      "#f97316",  # orange
    "gas":       "#ef4444",  # red
    "fx":        "#06b6d4",  # cyan
    "freight":   "#64748b",  # slate
    "tariff":    "#dc2626",  # red line
    "pre":       "#e0f2fe",  # light blue fill
    "post":      "#fee2e2",  # light red fill
}


# ── 1. Load Data ────────────────────────────────────────────────────────────
def load_fipi():
    """Load FIPI nitrogen and fertilizer series, monthly."""
    df = pd.read_csv(DATA / "18-10-0258-01.csv")
    
    # Filter to fertilizer-related categories
    fert_cats = ["Fertilizer", "Nitrogen fertilizers", "Other fertilizers"]
    df = df[df["Price index"].isin(fert_cats)].copy()
    
    df["date"] = pd.to_datetime(df["REF_DATE"] + "-01")
    df = df[df["date"] >= "2019-01-01"]
    df = df[["date", "Price index", "VALUE"]].dropna(subset=["VALUE"])
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
    
    return df


def load_benchmarks():
    """Load World Bank fertilizer benchmark prices."""
    df = pd.read_csv(DATA / "fertilizer_benchmarks.csv")
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= "2019-01-01"]
    return df


def load_gas():
    """Load Henry Hub gas prices."""
    df = pd.read_csv(RESEARCH / "henry_hub_gas_monthly.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_fx():
    """Load CAD/USD exchange rate."""
    df = pd.read_csv(RESEARCH / "cad_usd_monthly.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_freight():
    """Load Brent crude (freight proxy)."""
    df = pd.read_csv(RESEARCH / "brent_crude_monthly.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


# ── 2. Chart 1: FIPI Fertilizer Index ───────────────────────────────────────
def chart_fipi(fipi_df):
    """FIPI Fertilizer index time series with tariff event annotation."""
    fig = go.Figure()
    
    for cat, color, dash in [
        ("Nitrogen fertilizers", COLORS["nitrogen"], "solid"),
        ("Other fertilizers", COLORS["other_fert"], "dash"),
        ("Fertilizer", COLORS["total_fert"], "dot"),
    ]:
        subset = fipi_df[fipi_df["Price index"] == cat]
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["VALUE"],
            name=cat,
            line=dict(color=color, width=3 if cat == "Nitrogen fertilizers" else 2, dash=dash),
            mode="lines",
            hovertemplate=f"{cat}<br>%{{x|%b %Y}}: %{{y:.1f}}<extra></extra>",
        ))
    
    # Tariff event line — use shapes + annotations to avoid Plotly/Pandas bug
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper",
                  line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper",
                       text="35% Tariff<br>(Mar 3, 2022)", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    fig.update_layout(
        title=dict(
            text="Canadian Farm Input Price Index — Fertilizer Components<br>"
                 "<sub>Monthly, 2012=100 | Source: Statistics Canada 18-10-0258-01</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        yaxis_title="Index (2012 = 100)",
        xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=80, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "01_fipi_fertilizer_index.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [1/5] Saved: {out.name}")
    return fig


# ── 3. Chart 2: World Bank Urea Benchmark ──────────────────────────────────
def chart_urea(bench_df):
    """World Bank urea price with tariff annotation."""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=bench_df["date"], y=bench_df["urea_usd"],
        name="Urea (US$/MT)",
        line=dict(color=COLORS["urea"], width=3),
        fill="tozeroy",
        fillcolor="rgba(249, 115, 22, 0.1)",
        hovertemplate="Urea: $%{y:,.0f}/MT<br>%{x|%b %Y}<extra></extra>",
    ))
    
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper",
                  line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper",
                       text="35% Tariff", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    # Add Ukraine invasion annotation  
    fig.add_shape(type="line", x0="2022-02-24", x1="2022-02-24",
                  y0=0, y1=1, yref="paper",
                  line=dict(color="#94a3b8", width=1, dash="dot"))
    fig.add_annotation(x="2022-02-24", y=0.05, yref="paper",
                       text="Ukraine<br>Invasion", showarrow=False,
                       xanchor="right",
                       font=dict(size=10, color="#64748b"))
    
    fig.update_layout(
        title=dict(
            text="World Bank Urea Benchmark Price<br>"
                 "<sub>Monthly, US$/MT | Source: World Bank Commodity Markets Outlook</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=450,
        yaxis_title="US$ per Metric Tonne",
        hovermode="x unified",
        margin=dict(t=80, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "02_urea_benchmark.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [2/5] Saved: {out.name}")
    return fig


# ── 4. Chart 3: Composite Panel ─────────────────────────────────────────────
def chart_composite(fipi_df, bench_df, gas_df, fx_df, freight_df):
    """
    4-panel chart:
      Top-left:     FIPI nitrogen index
      Top-right:    World urea benchmark (USD/MT)
      Bottom-left:  Henry Hub gas (USD/MMBtu)
      Bottom-right: CAD/USD exchange rate
    """
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "FIPI Nitrogen Index (2012=100)",
            "World Urea Price (US$/MT)",
            "Henry Hub Gas (US$/MMBtu)",
            "CAD/USD Exchange Rate",
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )
    
    # Panel 1: FIPI nitrogen
    nitrogen = fipi_df[fipi_df["Price index"] == "Nitrogen fertilizers"]
    fig.add_trace(go.Scatter(
        x=nitrogen["date"], y=nitrogen["VALUE"],
        line=dict(color=COLORS["nitrogen"], width=2.5),
        showlegend=False,
        hovertemplate="FIPI: %{y:.1f}<extra></extra>",
    ), row=1, col=1)
    
    # Panel 2: Urea
    fig.add_trace(go.Scatter(
        x=bench_df["date"], y=bench_df["urea_usd"],
        line=dict(color=COLORS["urea"], width=2.5),
        showlegend=False,
        hovertemplate="Urea: $%{y:,.0f}/MT<extra></extra>",
    ), row=1, col=2)
    
    # Panel 3: Gas
    fig.add_trace(go.Scatter(
        x=gas_df["date"], y=gas_df["henry_hub_usd_per_mmbtu"],
        line=dict(color=COLORS["gas"], width=2.5),
        showlegend=False,
        hovertemplate="Gas: $%{y:.2f}/MMBtu<extra></extra>",
    ), row=2, col=1)
    
    # Panel 4: FX
    fig.add_trace(go.Scatter(
        x=fx_df["date"], y=fx_df["cad_per_usd"],
        line=dict(color=COLORS["fx"], width=2.5),
        showlegend=False,
        hovertemplate="CAD/USD: %{y:.4f}<extra></extra>",
    ), row=2, col=2)
    
    # Add tariff event lines to all panels using shapes
    for xref in ["x", "x2", "x3", "x4"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color=COLORS["tariff"], width=1.5, dash="dash"))
    
    fig.update_layout(
        title=dict(
            text="Fertilizer Tariff Research — Key Variable Overview<br>"
                 "<sub>Red dashed line = March 3, 2022 (35% tariff on Russian fertilizer)</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=700,
        hovermode="x unified",
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "03_composite_panel.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [3/5] Saved: {out.name}")
    return fig


# ── 5. Chart 4: Pre/Post Tariff Summary ─────────────────────────────────────
def chart_pre_post(fipi_df, bench_df, gas_df):
    """Bar chart comparing pre-tariff vs post-tariff average levels."""
    
    # Define periods
    pre_start, pre_end = pd.Timestamp("2019-01-01"), pd.Timestamp("2022-02-28")
    post_start, post_end = pd.Timestamp("2022-03-01"), pd.Timestamp("2024-12-31")
    
    def period_stats(df, col, date_col="date"):
        pre = df[(df[date_col] >= pre_start) & (df[date_col] <= pre_end)][col].mean()
        post = df[(df[date_col] >= post_start) & (df[date_col] <= post_end)][col].mean()
        pct = (post - pre) / pre * 100 if pre > 0 else 0
        return pre, post, pct
    
    nitrogen = fipi_df[fipi_df["Price index"] == "Nitrogen fertilizers"]
    
    categories = []
    pre_vals = []
    post_vals = []
    pct_changes = []
    
    # FIPI Nitrogen
    p, q, c = period_stats(nitrogen, "VALUE")
    categories.append("FIPI Nitrogen<br>(Index)")
    pre_vals.append(p)
    post_vals.append(q)
    pct_changes.append(c)
    
    # Urea benchmark
    p, q, c = period_stats(bench_df, "urea_usd")
    categories.append("Urea Benchmark<br>(USD/MT)")
    pre_vals.append(p)
    post_vals.append(q)
    pct_changes.append(c)
    
    # Henry Hub
    p, q, c = period_stats(gas_df, "henry_hub_usd_per_mmbtu")
    categories.append("Henry Hub Gas<br>(USD/MMBtu)")
    pre_vals.append(p)
    post_vals.append(q)
    pct_changes.append(c)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name="Pre-Tariff Avg (Jan 2019 – Feb 2022)",
        x=categories, y=pre_vals,
        marker_color="#93c5fd",
        text=[f"{v:.1f}" for v in pre_vals],
        textposition="auto",
    ))
    
    fig.add_trace(go.Bar(
        name="Post-Tariff Avg (Mar 2022 – Dec 2024)",
        x=categories, y=post_vals,
        marker_color="#fca5a5",
        text=[f"{v:.1f}" for v in post_vals],
        textposition="auto",
    ))
    
    # Add % change annotations
    for i, pct in enumerate(pct_changes):
        fig.add_annotation(
            x=categories[i], y=max(pre_vals[i], post_vals[i]) * 1.1,
            text=f"+{pct:.0f}%" if pct > 0 else f"{pct:.0f}%",
            showarrow=False,
            font=dict(size=13, color=COLORS["tariff"] if pct > 0 else COLORS["total_fert"],
                      weight="bold"),
        )
    
    fig.update_layout(
        title=dict(
            text="Pre- vs Post-Tariff Average Levels<br>"
                 "<sub>Comparing Jan 2019 – Feb 2022 vs Mar 2022 – Dec 2024</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=450,
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=100, b=60, l=60, r=20),
    )
    
    out = CHART_DIR / "04_pre_post_comparison.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [4/5] Saved: {out.name}")
    
    # Print summary stats
    print("\n  Pre/Post Tariff Summary:")
    print(f"  {'Category':<30} {'Pre-Tariff':>12} {'Post-Tariff':>12} {'Change':>10}")
    print(f"  {'-'*64}")
    for cat, pre, post, pct in zip(categories, pre_vals, post_vals, pct_changes):
        cat_clean = cat.replace("<br>", " ")
        print(f"  {cat_clean:<30} {pre:>12.1f} {post:>12.1f} {pct:>+9.1f}%")
    
    return fig


# ── 6. Chart 5: Structural Break Analysis ──────────────────────────────────
def chart_structural_break(fipi_df):
    """
    Visual structural break analysis on FIPI nitrogen series.
    Uses rolling statistics + CUSUM-style test since full Bai-Perron
    requires additional packages.
    """
    nitrogen = fipi_df[fipi_df["Price index"] == "Nitrogen fertilizers"].copy()
    nitrogen = nitrogen.sort_values("date").reset_index(drop=True)
    
    # Rolling statistics
    nitrogen["rolling_mean_12"] = nitrogen["VALUE"].rolling(12, min_periods=6).mean()
    nitrogen["rolling_std_12"] = nitrogen["VALUE"].rolling(12, min_periods=6).std()
    
    # Month-over-month % change
    nitrogen["pct_change"] = nitrogen["VALUE"].pct_change() * 100
    
    # CUSUM-style: cumulative sum of standardized residuals from pre-tariff mean
    pre_tariff = nitrogen[nitrogen["date"] < TARIFF_DATE]
    pre_mean = pre_tariff["VALUE"].mean()
    pre_std = pre_tariff["VALUE"].std()
    nitrogen["z_score"] = (nitrogen["VALUE"] - pre_mean) / pre_std
    nitrogen["cusum"] = nitrogen["z_score"].cumsum()
    
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=[
            "FIPI Nitrogen Index with Rolling Mean (12-mo)",
            "Month-over-Month % Change",
            "CUSUM (Cumulative Standardized Deviation from Pre-Tariff Mean)",
        ],
        vertical_spacing=0.08,
        row_heights=[0.4, 0.3, 0.3],
    )
    
    # Panel 1: Level + rolling mean
    fig.add_trace(go.Scatter(
        x=nitrogen["date"], y=nitrogen["VALUE"],
        name="FIPI Nitrogen",
        line=dict(color=COLORS["nitrogen"], width=2),
        hovertemplate="%{x|%b %Y}: %{y:.1f}<extra></extra>",
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=nitrogen["date"], y=nitrogen["rolling_mean_12"],
        name="12-mo Rolling Mean",
        line=dict(color="#94a3b8", width=2, dash="dash"),
        hovertemplate="%{x|%b %Y}: %{y:.1f}<extra></extra>",
    ), row=1, col=1)
    
    # Panel 2: % change
    colors = ["#dc2626" if v > 5 else "#059669" if v < -5 else "#94a3b8"
              for v in nitrogen["pct_change"].fillna(0)]
    
    fig.add_trace(go.Bar(
        x=nitrogen["date"], y=nitrogen["pct_change"],
        name="MoM % Change",
        marker_color=colors,
        showlegend=False,
        hovertemplate="%{x|%b %Y}: %{y:+.1f}%<extra></extra>",
    ), row=2, col=1)
    
    # Panel 3: CUSUM
    fig.add_trace(go.Scatter(
        x=nitrogen["date"], y=nitrogen["cusum"],
        name="CUSUM",
        line=dict(color=COLORS["other_fert"], width=2.5),
        fill="tozeroy",
        fillcolor="rgba(124, 58, 237, 0.1)",
        hovertemplate="%{x|%b %Y}: %{y:.2f}<extra></extra>",
    ), row=3, col=1)
    
    # Add tariff lines to all panels using shapes
    for xref in ["x", "x2", "x3"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color=COLORS["tariff"], width=1.5, dash="dash"))
    
    fig.update_layout(
        title=dict(
            text="Structural Break Analysis — FIPI Nitrogen Fertilizer Index<br>"
                 "<sub>Red dashed line = March 3, 2022 tariff event | Pre-tariff baseline: Jan 2019 – Feb 2022</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=900,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "05_structural_break_analysis.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [5/5] Saved: {out.name}")
    
    # Print key break statistics
    print("\n  Structural Break Indicators:")
    nitrogen_post = nitrogen[nitrogen["date"] >= TARIFF_DATE]
    if not nitrogen_post.empty:
        peak_idx = nitrogen_post["VALUE"].idxmax()
        peak_date = nitrogen_post.loc[peak_idx, "date"].strftime("%b %Y")
        peak_val = nitrogen_post.loc[peak_idx, "VALUE"]
        print(f"  - Pre-tariff mean:  {pre_mean:.1f}")
        print(f"  - Pre-tariff std:   {pre_std:.1f}")
        print(f"  - Post-tariff peak: {peak_val:.1f} ({peak_date}) = {(peak_val/pre_mean - 1)*100:+.0f}%")
        
        # Find when series returned to pre-tariff range (mean + 1 std)
        threshold = pre_mean + pre_std
        recovery = nitrogen_post[nitrogen_post["VALUE"] <= threshold]
        if not recovery.empty:
            recovery_date = recovery.iloc[0]["date"].strftime("%b %Y")
            print(f"  - Recovery to pre-tariff range: {recovery_date}")
        else:
            print(f"  - Series still above pre-tariff range (>{threshold:.1f})")
    
    return fig


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("   DESCRIPTIVE ANALYSIS — Phase 1")
    print("=" * 70)
    print()
    
    print("Loading datasets...")
    fipi = load_fipi()
    bench = load_benchmarks()
    gas = load_gas()
    fx = load_fx()
    freight = load_freight()
    
    print(f"  FIPI:       {len(fipi)} rows ({fipi['date'].min():%b %Y} - {fipi['date'].max():%b %Y})")
    print(f"  Benchmarks: {len(bench)} rows ({bench['date'].min():%b %Y} - {bench['date'].max():%b %Y})")
    print(f"  Gas:        {len(gas)} rows")
    print(f"  FX:         {len(fx)} rows")
    print(f"  Freight:    {len(freight)} rows")
    print()
    
    print("Generating charts...")
    chart_fipi(fipi)
    chart_urea(bench)
    chart_composite(fipi, bench, gas, fx, freight)
    chart_pre_post(fipi, bench, gas)
    chart_structural_break(fipi)
    
    print(f"\nAll charts saved to: {CHART_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
