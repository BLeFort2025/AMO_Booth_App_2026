"""
Tariff Incidence Research — Regional Comparison Analysis
=========================================================
Compares fertilizer price impacts across:
  - Ontario vs Western Canada (FIPI nitrogen, quarterly)
  - Ontario vs US (FIPI vs NASS, quarterly alignment)
  - Eastern Canada vs Western Canada
  - Individual prairie provinces (AB, SK, MB)

Uses the quarterly provincial FIPI breakdown from 18-10-0258-01.

Charts produced:
  15. Ontario vs Western Canada Nitrogen Index
  16. Regional Heat Map — All provinces pre/post tariff
  17. Ontario vs US Fertilizer Index (quarterly aligned)
  18. Regional DiD — Ontario as Treatment, West as Control
  19. Eastern vs Western Canada Asymmetry Deep-Dive

All outputs saved to: data/latest/tariff_research/charts/
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import statsmodels.formula.api as smf

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data" / "latest"
RESEARCH = DATA / "tariff_research"
CHART_DIR = RESEARCH / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

TARIFF_DATE = pd.Timestamp("2022-03-01")
TARIFF_DATE_STR = "2022-03-01"

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

REGION_COLORS = {
    "Ontario":        "#dc2626",  # red
    "Western Canada": "#2563eb",  # blue
    "Eastern Canada": "#059669",  # green
    "Alberta":        "#7c3aed",  # purple
    "Saskatchewan":   "#f97316",  # orange
    "Manitoba":       "#06b6d4",  # cyan
    "Quebec":         "#ec4899",  # pink
    "Canada":         "#64748b",  # slate
    "US":             "#1e40af",  # dark blue
}


# ── Data Loading ─────────────────────────────────────────────────────────────
def load_fipi_regional(price_index="Nitrogen fertilizers"):
    """Load quarterly provincial FIPI for a given price index category."""
    df = pd.read_csv(DATA / "18-10-0258-01.csv")
    df = df[df["Price index"] == price_index].copy()
    df["date"] = pd.to_datetime(df["REF_DATE"] + "-01")
    df["value"] = pd.to_numeric(df["VALUE"], errors="coerce")
    df = df[df["date"] >= "2019-01-01"]
    df = df[["date", "GEO", "value"]].dropna()
    return df


def load_us_nass_quarterly():
    """Load USDA NASS index and aggregate to quarterly for comparison."""
    df = pd.read_csv(RESEARCH / "usda_nass_fertilizer_index.csv")
    df = df[df["Period"] != "YEAR"].copy()
    df["month"] = df["Period"].map(MONTH_MAP)
    df["date"] = pd.to_datetime(df["Year"].astype(str) + "-" + df["month"].astype(str) + "-01")
    df["value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df[["date", "value"]].dropna().sort_values("date")
    
    # Aggregate to quarterly (Jan, Apr, Jul, Oct midpoints)
    df["quarter"] = df["date"].dt.to_period("Q")
    quarterly = df.groupby("quarter")["value"].mean().reset_index()
    quarterly["date"] = quarterly["quarter"].dt.to_timestamp()
    quarterly["GEO"] = "US"
    return quarterly[["date", "GEO", "value"]]


def load_controls():
    """Load gas and FX, aggregate to quarterly."""
    gas = pd.read_csv(RESEARCH / "henry_hub_gas_monthly.csv")
    gas["date"] = pd.to_datetime(gas["date"])
    gas["quarter"] = gas["date"].dt.to_period("Q")
    gas_q = gas.groupby("quarter")["henry_hub_usd_per_mmbtu"].mean().reset_index()
    gas_q["date"] = gas_q["quarter"].dt.to_timestamp()
    gas_q = gas_q.rename(columns={"henry_hub_usd_per_mmbtu": "gas"})
    
    fx = pd.read_csv(RESEARCH / "cad_usd_monthly.csv")
    fx["date"] = pd.to_datetime(fx["date"])
    fx["quarter"] = fx["date"].dt.to_period("Q")
    fx_q = fx.groupby("quarter")["cad_per_usd"].mean().reset_index()
    fx_q["date"] = fx_q["quarter"].dt.to_timestamp()
    fx_q = fx_q.rename(columns={"cad_per_usd": "fx"})
    
    return gas_q[["date", "gas"]], fx_q[["date", "fx"]]


def rebase(series, dates, base_start="2019-01-01", base_end="2019-12-31"):
    """Rebase to 2019 avg = 100."""
    mask = (dates >= base_start) & (dates <= base_end)
    base = series[mask].mean()
    if base == 0 or pd.isna(base):
        return series
    return series / base * 100


# ── Chart 15: Ontario vs Western Canada ──────────────────────────────────────
def chart_ont_vs_west(df):
    """Ontario vs Western Canada nitrogen fertilizer index."""
    regions = ["Ontario", "Western Canada", "Canada"]
    
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.65, 0.35],
        subplot_titles=[
            "Nitrogen Fertilizer Price Index — Ontario vs Western Canada",
            "Ontario–West Gap (positive = Ontario more expensive)",
        ],
        vertical_spacing=0.10,
    )
    
    # Rebase each to 2019 = 100
    for geo in regions:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = rebase(subset["value"], subset["date"])
        color = REGION_COLORS.get(geo, "#94a3b8")
        width = 3 if geo != "Canada" else 2
        dash = "solid" if geo != "Canada" else "dot"
        
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["idx"],
            name=geo,
            line=dict(color=color, width=width, dash=dash),
            mode="lines+markers",
            marker=dict(size=5 if geo != "Canada" else 3),
            hovertemplate=f"{geo}<br>%{{x|%b %Y}}: %{{y:.1f}}<extra></extra>",
        ), row=1, col=1)
    
    # Compute gap
    ont = df[df["GEO"] == "Ontario"].sort_values("date").copy()
    west = df[df["GEO"] == "Western Canada"].sort_values("date").copy()
    ont["idx"] = rebase(ont["value"], ont["date"])
    west["idx"] = rebase(west["value"], west["date"])
    
    merged = pd.merge(ont[["date", "idx"]], west[["date", "idx"]],
                       on="date", suffixes=("_ont", "_west"))
    merged["gap"] = merged["idx_ont"] - merged["idx_west"]
    
    gap_colors = ["#dc2626" if v > 0 else "#2563eb" for v in merged["gap"]]
    fig.add_trace(go.Bar(
        x=merged["date"], y=merged["gap"],
        marker_color=gap_colors, showlegend=False,
        hovertemplate="Gap: %{y:+.1f} pts<br>%{x|%b %Y}<extra></extra>",
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1, row=2, col=1)
    
    # Tariff line
    for xref in ["x", "x2"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color="#dc2626", width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper", xref="x",
                       text="35% Tariff<br>(Mar 2022)", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color="#dc2626"))
    
    fig.update_layout(
        template="plotly_white", height=700,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=80, b=40, l=60, r=20),
    )
    fig.update_yaxes(title_text="Index (2019 = 100)", row=1, col=1)
    fig.update_yaxes(title_text="Gap (index pts)", row=2, col=1)
    
    out = CHART_DIR / "15_ontario_vs_west.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [15] Saved: {out.name}")
    
    # Stats
    pre = merged[merged["date"] < TARIFF_DATE]["gap"]
    post = merged[merged["date"] >= TARIFF_DATE]["gap"]
    print(f"       Ontario-West gap pre-tariff:  {pre.mean():+.1f} pts")
    print(f"       Ontario-West gap post-tariff: {post.mean():+.1f} pts")
    print(f"       Widening: {post.mean() - pre.mean():+.1f} pts")
    
    return merged


# ── Chart 16: Regional Heat Map ──────────────────────────────────────────────
def chart_regional_heatmap(df):
    """Bar chart comparing pre/post tariff levels across all provinces."""
    regions = ["Ontario", "Quebec", "Eastern Canada",
               "Manitoba", "Saskatchewan", "Alberta", "Western Canada", "Canada"]
    
    pre_vals = []
    post_vals = []
    peak_vals = []
    recovery_vals = []
    
    for geo in regions:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = rebase(subset["value"], subset["date"])
        
        pre = subset[subset["date"] < TARIFF_DATE]["idx"].mean()
        post = subset[subset["date"] >= TARIFF_DATE]["idx"].mean()
        peak = subset[subset["date"] >= TARIFF_DATE]["idx"].max()
        
        # Latest value as "recovery" indicator
        latest = subset["idx"].iloc[-1] if not subset.empty else 0
        
        pre_vals.append(pre)
        post_vals.append(post)
        peak_vals.append(peak)
        recovery_vals.append(latest)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name="Pre-Tariff Avg (2019 – Feb 2022)",
        x=regions, y=pre_vals,
        marker_color="#93c5fd",
        text=None, # Removed to declutter
        textposition="none",
    ))
    
    fig.add_trace(go.Bar(
        name="Post-Tariff Avg (Mar 2022 – Present)",
        x=regions, y=post_vals,
        marker_color="#fca5a5",
        text=None, # Removed to declutter
        textposition="none",
    ))
    
    fig.add_trace(go.Bar(
        name="Peak Post-Tariff",
        x=regions, y=peak_vals,
        marker_color="#dc2626",
        text=[f"{v:.0f}" for v in peak_vals],
        textposition="outside",
        textfont=dict(color="#dc2626")
    ))
    
    # Add % change annotations
    for i, (pre, post) in enumerate(zip(pre_vals, post_vals)):
        pct = (post / pre - 1) * 100 if pre > 0 else 0
        fig.add_annotation(
            x=regions[i], y=max(peak_vals[i], post) + 18,
            text=f"+{pct:.0f}%",
            showarrow=False,
            font=dict(size=12, color="#dc2626", weight="bold"),
        )
    
    fig.update_layout(
        title=dict(
            text="Regional Nitrogen Fertilizer Price Comparison<br>"
                 "<sub>FIPI Nitrogen Index (2019 = 100) | Quarterly | Source: StatsCan 18-10-0258-01</sub>",
            font=dict(size=16),
            y=0.95
        ),
        template="plotly_white",
        height=550,
        barmode="group",
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
        margin=dict(t=80, b=80, l=60, r=20),
    )
    
    out = CHART_DIR / "16_regional_heatmap.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [16] Saved: {out.name}")
    
    # Print table
    print(f"\n       {'Region':<20} {'Pre':>8} {'Post':>8} {'Peak':>8} {'Change':>8}")
    print(f"       {'-'*52}")
    for i, geo in enumerate(regions):
        pct = (post_vals[i] / pre_vals[i] - 1) * 100
        print(f"       {geo:<20} {pre_vals[i]:>8.1f} {post_vals[i]:>8.1f} {peak_vals[i]:>8.1f} {pct:>+7.1f}%")
    
    return fig


# ── Chart 17: Ontario vs US ─────────────────────────────────────────────────
def chart_ont_vs_us(df_regional, us_quarterly):
    """Ontario FIPI nitrogen vs US NASS index, quarterly aligned."""
    
    ont = df_regional[df_regional["GEO"] == "Ontario"].sort_values("date").copy()
    us = us_quarterly.sort_values("date").copy()
    
    ont["idx"] = rebase(ont["value"], ont["date"])
    us["idx"] = rebase(us["value"], us["date"])
    
    # Merge on closest quarter
    ont["quarter"] = ont["date"].dt.to_period("Q")
    us["quarter"] = us["date"].dt.to_period("Q")
    
    merged = pd.merge(
        ont[["quarter", "idx"]].rename(columns={"idx": "ont"}),
        us[["quarter", "idx"]].rename(columns={"idx": "us"}),
        on="quarter", how="inner",
    )
    merged["date"] = merged["quarter"].dt.to_timestamp()
    merged["gap"] = merged["ont"] - merged["us"]
    
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.65, 0.35],
        subplot_titles=[
            "Ontario vs US Nitrogen / Fertilizer Price Index (2019 = 100)",
            "Ontario–US Gap (positive = Ontario more expensive)",
        ],
        vertical_spacing=0.10,
    )
    
    fig.add_trace(go.Scatter(
        x=merged["date"], y=merged["ont"],
        name="Ontario (FIPI Nitrogen)",
        line=dict(color=REGION_COLORS["Ontario"], width=3),
        mode="lines+markers", marker=dict(size=6),
        hovertemplate="Ontario: %{y:.1f}<br>%{x|%b %Y}<extra></extra>",
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=merged["date"], y=merged["us"],
        name="United States (NASS Index)",
        line=dict(color=REGION_COLORS["US"], width=3),
        mode="lines+markers", marker=dict(size=6),
        hovertemplate="US: %{y:.1f}<br>%{x|%b %Y}<extra></extra>",
    ), row=1, col=1)
    
    # Gap bars
    gap_colors = ["#dc2626" if v > 0 else "#2563eb" for v in merged["gap"]]
    fig.add_trace(go.Bar(
        x=merged["date"], y=merged["gap"],
        marker_color=gap_colors, showlegend=False,
        hovertemplate="Gap: %{y:+.1f} pts<br>%{x|%b %Y}<extra></extra>",
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1, row=2, col=1)
    
    # Tariff line
    for xref in ["x", "x2"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color="#dc2626", width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper", xref="x",
                       text="35% Tariff<br>(Mar 2022)", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color="#dc2626"))
    
    fig.update_layout(
        template="plotly_white", height=700,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=80, b=40, l=60, r=20),
    )
    fig.update_yaxes(title_text="Index (2019 = 100)", row=1, col=1)
    fig.update_yaxes(title_text="Gap (index pts)", row=2, col=1)
    
    out = CHART_DIR / "17_ontario_vs_us.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [17] Saved: {out.name}")
    
    pre = merged[merged["date"] < TARIFF_DATE]["gap"]
    post = merged[merged["date"] >= TARIFF_DATE]["gap"]
    print(f"       Ontario-US gap pre-tariff:  {pre.mean():+.1f} pts")
    print(f"       Ontario-US gap post-tariff: {post.mean():+.1f} pts")
    print(f"       DiD raw estimate:           {post.mean() - pre.mean():+.1f} pts")
    
    return merged


# ── Chart 18: Regional DiD ──────────────────────────────────────────────────
def chart_regional_did(df):
    """
    Regional DiD: Ontario (treatment) vs Western Canada (control).
    
    Hypothesis: Ontario relies more on imported fertilizer (including
    Russian) while Western Canada has domestic production (Saskatchewan
    potash, Alberta nitrogen). The tariff should therefore hit Ontario
    harder than the West.
    """
    ont = df[df["GEO"] == "Ontario"].sort_values("date").copy()
    west = df[df["GEO"] == "Western Canada"].sort_values("date").copy()
    
    ont["idx"] = rebase(ont["value"], ont["date"])
    west["idx"] = rebase(west["value"], west["date"])
    
    # Build DiD panel
    ont_panel = ont[["date", "idx"]].assign(region="Ontario", treated=1)
    west_panel = west[["date", "idx"]].assign(region="West", treated=0)
    panel = pd.concat([ont_panel, west_panel], ignore_index=True)
    
    panel["post"] = (panel["date"] >= TARIFF_DATE).astype(int)
    panel["did"] = panel["post"] * panel["treated"]
    panel["trend"] = panel.groupby("region").cumcount()
    
    # Add controls
    gas_q, fx_q = load_controls()
    panel = panel.merge(gas_q, on="date", how="left")
    panel = panel.merge(fx_q, on="date", how="left")
    panel = panel.dropna(subset=["gas", "fx"])
    
    # Estimate
    model = smf.ols("idx ~ post + treated + did + gas + fx + trend", data=panel).fit(
        cov_type="HC3")
    
    did_coef = model.params.get("did", 0)
    did_pval = model.pvalues.get("did", 1)
    did_se = model.bse.get("did", 0)
    
    print(f"\n  REGIONAL DiD: Ontario vs Western Canada")
    print(f"  {'-'*50}")
    print(model.summary2().tables[1].to_string())
    print(f"\n  DiD Estimator:  {did_coef:+.2f} index points")
    print(f"  Std Error:      {did_se:.2f}")
    print(f"  P-value:        {did_pval:.4f}")
    print(f"  95% CI:         [{did_coef - 1.96*did_se:.2f}, {did_coef + 1.96*did_se:.2f}]")
    
    if did_coef > 0:
        print(f"  → Ontario nitrogen prices were {did_coef:.1f} index points HIGHER")
        print(f"    than Western Canada post-tariff, relative to pre-tariff baseline.")
    else:
        print(f"  → Ontario nitrogen prices were {abs(did_coef):.1f} index points LOWER")
        print(f"    than Western Canada post-tariff, relative to pre-tariff baseline.")
    
    pre_ont = ont[ont["date"] < TARIFF_DATE]["idx"].mean()
    pct_effect = did_coef / pre_ont * 100
    print(f"  As % of pre-tariff Ontario level: {pct_effect:+.1f}%")
    
    return model


# ── Chart 19: East vs West Deep-Dive ────────────────────────────────────────
def chart_east_west_deepdive(df):
    """Detailed comparison with all provinces and East/West aggregates."""
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "Eastern Canada: Ontario vs Quebec",
            "Western Canada: AB vs SK vs MB",
            "East vs West Aggregate",
            "Provincial Peak Comparison",
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.10,
    )
    
    # Panel 1: Eastern provinces
    for geo in ["Ontario", "Quebec"]:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = rebase(subset["value"], subset["date"])
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["idx"],
            name=geo, line=dict(color=REGION_COLORS[geo], width=2.5),
            mode="lines+markers", marker=dict(size=4),
            hovertemplate=f"{geo}: %{{y:.1f}}<extra></extra>",
        ), row=1, col=1)
    
    # Panel 2: Western provinces
    for geo in ["Alberta", "Saskatchewan", "Manitoba"]:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = rebase(subset["value"], subset["date"])
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["idx"],
            name=geo, line=dict(color=REGION_COLORS[geo], width=2.5),
            mode="lines+markers", marker=dict(size=4),
            hovertemplate=f"{geo}: %{{y:.1f}}<extra></extra>",
        ), row=1, col=2)
    
    # Panel 3: East vs West aggregate
    for geo in ["Eastern Canada", "Western Canada"]:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = rebase(subset["value"], subset["date"])
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["idx"],
            name=geo, line=dict(color=REGION_COLORS[geo], width=3),
            mode="lines+markers", marker=dict(size=5),
            hovertemplate=f"{geo}: %{{y:.1f}}<extra></extra>",
            showlegend=True,
        ), row=2, col=1)
    
    # Panel 4: Peak comparison bars
    regions_bar = ["Ontario", "Quebec", "Manitoba", "Saskatchewan", "Alberta"]
    peaks = []
    pre_avgs = []
    for geo in regions_bar:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = rebase(subset["value"], subset["date"])
        peak = subset[subset["date"] >= TARIFF_DATE]["idx"].max()
        pre = subset[subset["date"] < TARIFF_DATE]["idx"].mean()
        peaks.append(peak)
        pre_avgs.append(pre)
    
    bar_colors = [REGION_COLORS.get(g, "#94a3b8") for g in regions_bar]
    fig.add_trace(go.Bar(
        x=regions_bar, y=peaks,
        marker_color=bar_colors, showlegend=False,
        text=[f"{p:.0f}" for p in peaks],
        textposition="outside",
        hovertemplate="%{x}: peak %{y:.1f}<extra></extra>",
    ), row=2, col=2)
    
    # Add tariff lines to panels 1-3
    for xref in ["x", "x2", "x3"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color="#dc2626", width=1.5, dash="dash"))
    
    fig.update_layout(
        title=dict(
            text="Eastern vs Western Canada — Nitrogen Fertilizer Price Deep-Dive<br>"
                 "<sub>Quarterly FIPI Nitrogen Index (2019 = 100) | Red dashed line = tariff event</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=800,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "19_east_west_deepdive.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [19] Saved: {out.name}")
    
    # Print provincial comparison
    print(f"\n       Provincial Peak Comparison (2019 = 100):")
    for i, geo in enumerate(regions_bar):
        pct = (peaks[i] / pre_avgs[i] - 1) * 100
        print(f"       {geo:<20s}: peak {peaks[i]:.1f} ({pct:+.0f}% above pre-tariff avg)")
    
    return fig


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("   REGIONAL COMPARISON ANALYSIS")
    print("=" * 70)
    print()
    
    # Load regional FIPI
    print("Loading regional data...")
    df = load_fipi_regional("Nitrogen fertilizers")
    us_q = load_us_nass_quarterly()
    
    geos = df["GEO"].unique()
    print(f"  Regions: {sorted(geos.tolist())}")
    print(f"  Quarters: {df['date'].nunique()} ({df['date'].min():%b %Y} – {df['date'].max():%b %Y})")
    print(f"  US NASS quarters: {len(us_q)}")
    print()
    
    print("Generating charts...")
    
    # Chart 15: Ontario vs Western Canada
    ont_west_gap = chart_ont_vs_west(df)
    print()
    
    # Chart 16: Regional heat map
    chart_regional_heatmap(df)
    print()
    
    # Chart 17: Ontario vs US
    ont_us_gap = chart_ont_vs_us(df, us_q)
    print()
    
    # Chart 18: Regional DiD
    print("\n  Running Regional DiD estimation...")
    did_model = chart_regional_did(df)
    
    # Chart 19: East-West deep-dive
    print()
    chart_east_west_deepdive(df)
    
    print(f"\n{'='*70}")
    print(f"  REGIONAL ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"  All charts saved to: {CHART_DIR}")


if __name__ == "__main__":
    main()
