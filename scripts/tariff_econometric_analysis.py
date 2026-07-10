"""
Tariff Incidence Research — Econometric Analysis (Phase 2)
==========================================================
Builds the Difference-in-Differences (DiD) framework and pass-through
regression using all available data.

Models:
  1. Canada vs US Index Comparison (DiD visual)
  2. Pass-Through Regression: FIPI ~ Urea + Gas + FX + Tariff
  3. DiD Estimation: Index ~ Post + Treated + Post×Treated + Controls

Charts produced:
  11. Canada vs US Fertilizer Index Comparison
  12. DiD Event Study — Dynamic Treatment Effects
  13. Pass-Through Regression Diagnostics
  14. Full Research Summary Dashboard

All outputs saved to: data/latest/tariff_research/charts/
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import statsmodels.api as sm
import statsmodels.formula.api as smf

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data" / "latest"
RESEARCH = DATA / "tariff_research"
CIMT_DIR = DATA / "cimt_trade"
CHART_DIR = RESEARCH / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

TARIFF_DATE = pd.Timestamp("2022-03-01")
TARIFF_DATE_STR = "2022-03-01"

COLORS = {
    "canada":    "#dc2626",  # red
    "us":        "#2563eb",  # blue
    "diff":      "#7c3aed",  # purple
    "tariff":    "#dc2626",
    "ci":        "rgba(37, 99, 235, 0.15)",
    "nitrogen":  "#2563eb",
    "urea":      "#f97316",
    "gas":       "#ef4444",
    "fx":        "#06b6d4",
    "residual":  "#7c3aed",
}

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


# ── Data Loading ─────────────────────────────────────────────────────────────
def load_canada_fipi():
    """Load FIPI nitrogen fertilizer index (monthly).
    
    Uses 'Nitrogen fertilizers' specifically because the tariff targets
    Russian nitrogen imports (HS 3102). The aggregate 'Fertilizer' index
    includes potash (where Canada is the world's #1 producer), which
    dilutes the tariff signal.
    """
    df = pd.read_csv(DATA / "18-10-0258-01.csv")
    df = df[df["Price index"] == "Nitrogen fertilizers"].copy()
    df["date"] = pd.to_datetime(df["REF_DATE"] + "-01")
    df = df[df["date"] >= "2019-01-01"]
    df["value"] = pd.to_numeric(df["VALUE"], errors="coerce")
    df = df[["date", "value"]].dropna().sort_values("date").reset_index(drop=True)
    return df


def load_us_nass():
    """Load USDA NASS fertilizer prices paid index (monthly)."""
    df = pd.read_csv(RESEARCH / "usda_nass_fertilizer_index.csv")
    # Filter to monthly only (exclude YEAR)
    df = df[df["Period"] != "YEAR"].copy()
    df["month"] = df["Period"].map(MONTH_MAP)
    df["date"] = pd.to_datetime(df["Year"].astype(str) + "-" + df["month"].astype(str) + "-01")
    df["value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df[["date", "value"]].dropna().sort_values("date").reset_index(drop=True)
    return df


def load_controls():
    """Load gas, FX, and freight control variables."""
    gas = pd.read_csv(RESEARCH / "henry_hub_gas_monthly.csv")
    gas["date"] = pd.to_datetime(gas["date"])
    
    fx = pd.read_csv(RESEARCH / "cad_usd_monthly.csv")
    fx["date"] = pd.to_datetime(fx["date"])
    
    freight = pd.read_csv(RESEARCH / "brent_crude_monthly.csv")
    freight["date"] = pd.to_datetime(freight["date"])
    
    bench = pd.read_csv(DATA / "fertilizer_benchmarks.csv")
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench[bench["date"] >= "2019-01-01"]
    
    return gas, fx, freight, bench


# ── Rebase Index ─────────────────────────────────────────────────────────────
def rebase_index(series, base_start="2019-01-01", base_end="2019-12-31", dates=None):
    """Rebase an index series so that the base period average = 100."""
    if dates is not None:
        mask = (dates >= base_start) & (dates <= base_end)
        base_mean = series[mask].mean()
    else:
        base_mean = series.mean()
    return series / base_mean * 100


# ── Chart 11: Canada vs US Index ─────────────────────────────────────────────
def chart_did_comparison(ca_df, us_df):
    """Side-by-side comparison of Canadian FIPI vs US NASS fertilizer index."""
    
    # Rebase both to 2019 avg = 100 for comparability
    ca = ca_df.copy()
    us = us_df.copy()
    ca["index_100"] = rebase_index(ca["value"], dates=ca["date"])
    us["index_100"] = rebase_index(us["value"], dates=us["date"])
    
    # Merge to compute difference
    merged = pd.merge(ca[["date", "index_100"]], us[["date", "index_100"]],
                       on="date", suffixes=("_ca", "_us"), how="inner")
    merged["gap"] = merged["index_100_ca"] - merged["index_100_us"]
    
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.65, 0.35],
        subplot_titles=[
            "Fertilizer Price Index — Canada vs United States (2019 = 100)",
            "Canada–US Gap (positive = Canada more expensive)",
        ],
        vertical_spacing=0.10,
    )
    
    # Panel 1: Both indexes
    fig.add_trace(go.Scatter(
        x=ca["date"], y=ca["index_100"],
        name="Canada (FIPI Nitrogen)",
        line=dict(color=COLORS["canada"], width=3),
        hovertemplate="Canada: %{y:.1f}<br>%{x|%b %Y}<extra></extra>",
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=us["date"], y=us["index_100"],
        name="United States (NASS Index)",
        line=dict(color=COLORS["us"], width=3),
        hovertemplate="US: %{y:.1f}<br>%{x|%b %Y}<extra></extra>",
    ), row=1, col=1)
    
    # Panel 2: Gap
    gap_colors = ["#dc2626" if v > 0 else "#2563eb" for v in merged["gap"]]
    fig.add_trace(go.Bar(
        x=merged["date"], y=merged["gap"],
        name="Canada–US Gap",
        marker_color=gap_colors,
        showlegend=False,
        hovertemplate="Gap: %{y:+.1f} pts<br>%{x|%b %Y}<extra></extra>",
    ), row=2, col=1)
    
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1, row=2, col=1)
    
    # Tariff event lines
    for xref in ["x", "x2"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper", xref="x",
                       text="35% Tariff<br>(Mar 2022)", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    fig.update_layout(
        template="plotly_white",
        height=700,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=80, b=40, l=60, r=20),
    )
    fig.update_yaxes(title_text="Index (2019 avg = 100)", row=1, col=1)
    fig.update_yaxes(title_text="Gap (index pts)", row=2, col=1)
    
    out = CHART_DIR / "11_canada_vs_us_did.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [11] Saved: {out.name}")
    
    # Stats
    pre_gap = merged[merged["date"] < TARIFF_DATE]["gap"].mean()
    post_gap = merged[merged["date"] >= TARIFF_DATE]["gap"].mean()
    print(f"       Avg gap pre-tariff:  {pre_gap:+.1f} index pts")
    print(f"       Avg gap post-tariff: {post_gap:+.1f} index pts")
    print(f"       DiD raw estimate:    {post_gap - pre_gap:+.1f} index pts")
    
    return merged


# ── Chart 12: DiD Event Study ────────────────────────────────────────────────
def chart_event_study(merged):
    """Dynamic DiD — plot treatment effect by quarter relative to tariff."""
    
    merged = merged.copy()
    merged["months_since"] = ((merged["date"].dt.year - 2022) * 12 + 
                               merged["date"].dt.month - 3)  # March 2022 = 0
    merged["quarter_rel"] = (merged["months_since"] / 3).apply(np.floor).astype(int)
    
    # Compute average gap by relative quarter
    qtr_stats = merged.groupby("quarter_rel").agg(
        gap_mean=("gap", "mean"),
        gap_se=("gap", lambda x: x.std() / np.sqrt(len(x)) if len(x) > 1 else 0),
        n=("gap", "count"),
    ).reset_index()
    
    qtr_stats["ci_upper"] = qtr_stats["gap_mean"] + 1.96 * qtr_stats["gap_se"]
    qtr_stats["ci_lower"] = qtr_stats["gap_mean"] - 1.96 * qtr_stats["gap_se"]
    
    fig = go.Figure()
    
    # Confidence interval band
    fig.add_trace(go.Scatter(
        x=pd.concat([qtr_stats["quarter_rel"], qtr_stats["quarter_rel"][::-1]]),
        y=pd.concat([qtr_stats["ci_upper"], qtr_stats["ci_lower"][::-1]]),
        fill="toself",
        fillcolor="rgba(124, 58, 237, 0.15)",
        line=dict(color="rgba(0,0,0,0)"),
        name="95% CI",
        showlegend=True,
        hoverinfo="skip",
    ))
    
    # Point estimates
    pre_color = [COLORS["us"] if q < 0 else COLORS["canada"] for q in qtr_stats["quarter_rel"]]
    fig.add_trace(go.Scatter(
        x=qtr_stats["quarter_rel"], y=qtr_stats["gap_mean"],
        mode="markers+lines",
        marker=dict(size=10, color=pre_color, line=dict(width=2, color="white")),
        line=dict(color=COLORS["diff"], width=2),
        name="Avg Canada–US Gap",
        hovertemplate="Q%{x}: %{y:+.1f} pts<extra></extra>",
    ))
    
    # Zero line
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1)
    
    # Treatment line
    fig.add_vline(x=-0.5, line_dash="dash", line_color=COLORS["tariff"], line_width=2)
    fig.add_annotation(x=-0.5, y=1, yref="paper",
                       text="Tariff<br>Imposed", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    fig.update_layout(
        title=dict(
            text="DiD Event Study — Canada vs US Fertilizer Price Gap by Quarter<br>"
                 "<sub>Quarter 0 = Mar–May 2022 (tariff imposition) | Gap = Canada index − US index (2019=100)</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        xaxis_title="Quarters Relative to Tariff (Q0 = Mar 2022)",
        yaxis_title="Canada–US Gap (index points)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=100, b=60, l=60, r=20),
    )
    
    out = CHART_DIR / "12_did_event_study.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [12] Saved: {out.name}")
    
    # Parallel trends test (pre-treatment gap stability)
    pre_qtrs = qtr_stats[qtr_stats["quarter_rel"] < 0]
    if len(pre_qtrs) > 2:
        from scipy import stats as scipy_stats
        slope, intercept, r, p, se = scipy_stats.linregress(
            pre_qtrs["quarter_rel"], pre_qtrs["gap_mean"])
        print(f"       Pre-trend test: slope={slope:.2f}, p={p:.3f} "
              f"({'PASS ✓' if p > 0.05 else 'FAIL ✗'} parallel trends)")
    
    return fig


# ── Model 1: Pass-Through Regression ────────────────────────────────────────
def model_passthrough(ca_df, gas_df, fx_df, bench_df):
    """
    FIPI_t = α + β₁·Urea_t + β₂·Gas_t + β₃·FX_t + β₄·Tariff_t + ε_t
    
    Tests how much of the FIPI movement is explained by global factors
    vs the tariff dummy.
    """
    print("\n" + "=" * 70)
    print("   MODEL 1: PASS-THROUGH REGRESSION")
    print("=" * 70)
    
    # Build panel
    ca = ca_df[["date", "value"]].rename(columns={"value": "fipi"})
    
    gas = gas_df[["date", "henry_hub_usd_per_mmbtu"]].rename(
        columns={"henry_hub_usd_per_mmbtu": "gas"})
    
    fx = fx_df[["date", "cad_per_usd"]].rename(columns={"cad_per_usd": "fx"})
    
    bench = bench_df[["date", "urea_usd"]].rename(columns={"urea_usd": "urea"})
    
    panel = ca.merge(gas, on="date", how="inner")\
              .merge(fx, on="date", how="inner")\
              .merge(bench, on="date", how="inner")
    
    # Add tariff dummy
    panel["tariff"] = (panel["date"] >= TARIFF_DATE).astype(int)
    
    # Add time trend
    panel["trend"] = np.arange(len(panel))
    
    # Log-log specification for elasticities
    panel["ln_fipi"] = np.log(panel["fipi"])
    panel["ln_urea"] = np.log(panel["urea"])
    panel["ln_gas"] = np.log(panel["gas"])
    panel["ln_fx"] = np.log(panel["fx"])
    
    # Run regression
    model = smf.ols("ln_fipi ~ ln_urea + ln_gas + ln_fx + tariff + trend", data=panel).fit(
        cov_type="HAC", cov_kwds={"maxlags": 6})  # Newey-West for autocorrelation
    
    print(model.summary())
    
    # Key interpretation
    tariff_coef = model.params.get("tariff", 0)
    tariff_pval = model.pvalues.get("tariff", 1)
    tariff_pct = (np.exp(tariff_coef) - 1) * 100
    
    print(f"\n  KEY RESULTS:")
    print(f"  R² = {model.rsquared:.3f} (R²-adj = {model.rsquared_adj:.3f})")
    print(f"  Tariff coefficient (log-log): {tariff_coef:.4f} (p = {tariff_pval:.4f})")
    print(f"  Tariff effect: {tariff_pct:+.1f}% on FIPI, controlling for global factors")
    
    urea_coef = model.params.get("ln_urea", 0)
    print(f"  Urea pass-through elasticity: {urea_coef:.3f}")
    print(f"    → A 10% global urea price increase → {urea_coef*10:.1f}% FIPI increase")
    
    # Build diagnostic chart
    panel["predicted"] = model.fittedvalues
    panel["residual"] = model.resid
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "Actual vs Predicted (ln FIPI)",
            "Residuals Over Time",
            "Coefficient Magnitudes",
            "Tariff Impact Decomposition",
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.10,
    )
    
    # Panel 1: Actual vs predicted
    fig.add_trace(go.Scatter(
        x=panel["date"], y=np.exp(panel["ln_fipi"]),
        name="Actual FIPI", line=dict(color=COLORS["canada"], width=2),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=panel["date"], y=np.exp(panel["predicted"]),
        name="Predicted", line=dict(color=COLORS["us"], width=2, dash="dash"),
    ), row=1, col=1)
    
    # Panel 2: Residuals
    res_colors = ["#dc2626" if r > 0 else "#2563eb" for r in panel["residual"]]
    fig.add_trace(go.Bar(
        x=panel["date"], y=panel["residual"],
        name="Residuals", marker_color=res_colors, showlegend=False,
    ), row=1, col=2)
    
    # Panel 3: Coefficients
    coef_names = ["ln_urea", "ln_gas", "ln_fx", "tariff"]
    coef_labels = ["Urea (global)", "Gas (input)", "FX (CAD/USD)", "Tariff (35%)"]
    coef_vals = [model.params.get(c, 0) for c in coef_names]
    coef_ses = [model.bse.get(c, 0) for c in coef_names]
    coef_colors = [COLORS["urea"], COLORS["gas"], COLORS["fx"], COLORS["tariff"]]
    
    fig.add_trace(go.Bar(
        x=coef_labels, y=coef_vals,
        error_y=dict(type="data", array=[1.96 * se for se in coef_ses], visible=True),
        marker_color=coef_colors, showlegend=False,
        text=[f"{v:.3f}" for v in coef_vals],
        textposition="outside",
    ), row=2, col=1)
    
    # Panel 4: Decomposition bar chart
    # How much of post-tariff FIPI increase is explained by each factor?
    post = panel[panel["tariff"] == 1]
    pre = panel[panel["tariff"] == 0]
    
    if not post.empty and not pre.empty:
        total_change = post["ln_fipi"].mean() - pre["ln_fipi"].mean()
        urea_contrib = model.params.get("ln_urea", 0) * (post["ln_urea"].mean() - pre["ln_urea"].mean())
        gas_contrib = model.params.get("ln_gas", 0) * (post["ln_gas"].mean() - pre["ln_gas"].mean())
        fx_contrib = model.params.get("ln_fx", 0) * (post["ln_fx"].mean() - pre["ln_fx"].mean())
        tariff_contrib = model.params.get("tariff", 0)
        residual_contrib = total_change - urea_contrib - gas_contrib - fx_contrib - tariff_contrib
        
        decomp_labels = ["Total\nChange", "Urea\n(Global)", "Gas\n(Input)", "FX\n(CAD/USD)", 
                         "Tariff\n(Policy)", "Residual"]
        decomp_vals = [total_change * 100, urea_contrib * 100, gas_contrib * 100, 
                       fx_contrib * 100, tariff_contrib * 100, residual_contrib * 100]
        decomp_colors = ["#1e293b", COLORS["urea"], COLORS["gas"], COLORS["fx"], 
                         COLORS["tariff"], COLORS["residual"]]
        
        fig.add_trace(go.Bar(
            x=decomp_labels, y=decomp_vals,
            marker_color=decomp_colors, showlegend=False,
            text=[f"{v:+.1f}%" for v in decomp_vals],
            textposition="outside",
        ), row=2, col=2)
        
        print(f"\n  DECOMPOSITION (% of ln FIPI change):")
        print(f"    Total change:     {total_change*100:+.1f}%")
        print(f"    Urea (global):    {urea_contrib*100:+.1f}%")
        print(f"    Gas (input cost): {gas_contrib*100:+.1f}%")
        print(f"    FX (CAD/USD):     {fx_contrib*100:+.1f}%")
        print(f"    Tariff (policy):  {tariff_contrib*100:+.1f}%")
        print(f"    Residual:         {residual_contrib*100:+.1f}%")
    
    # Tariff lines
    for xref in ["x", "x2"]:
        fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                      y0=0, y1=1, yref="paper", xref=xref,
                      line=dict(color=COLORS["tariff"], width=1.5, dash="dash"))
    
    fig.update_layout(
        title=dict(
            text="Pass-Through Regression Diagnostics<br>"
                 f"<sub>ln(FIPI) ~ ln(Urea) + ln(Gas) + ln(FX) + Tariff | R² = {model.rsquared:.3f} | Tariff effect: {tariff_pct:+.1f}%</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=700,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
        margin=dict(t=100, b=60, l=60, r=20),
    )
    
    out = CHART_DIR / "13_passthrough_regression.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"\n  [13] Saved: {out.name}")
    
    return model, panel


# ── Model 2: Difference-in-Differences ──────────────────────────────────────
def model_did(ca_df, us_df, gas_df, fx_df):
    """
    Y_it = α + β₁·Post_t + β₂·Canada_i + β₃·(Post×Canada)_it + γ·X_t + ε_it
    
    β₃ is the DiD estimator — the causal tariff effect.
    """
    print("\n" + "=" * 70)
    print("   MODEL 2: DIFFERENCE-IN-DIFFERENCES")
    print("=" * 70)
    
    # Rebase both indexes to 2019 = 100
    ca = ca_df.copy()
    us = us_df.copy()
    ca["index_100"] = rebase_index(ca["value"], dates=ca["date"])
    us["index_100"] = rebase_index(us["value"], dates=us["date"])
    
    # Stack into panel
    ca_panel = ca[["date", "index_100"]].assign(country="Canada", treated=1)
    us_panel = us[["date", "index_100"]].assign(country="US", treated=0)
    panel = pd.concat([ca_panel, us_panel], ignore_index=True)
    
    # Add regressors
    panel["post"] = (panel["date"] >= TARIFF_DATE).astype(int)
    panel["did"] = panel["post"] * panel["treated"]
    
    # Merge in controls (same for both countries since they're global variables)
    gas = gas_df[["date", "henry_hub_usd_per_mmbtu"]].rename(
        columns={"henry_hub_usd_per_mmbtu": "gas"})
    fx = fx_df[["date", "cad_per_usd"]].rename(columns={"cad_per_usd": "fx"})
    
    panel = panel.merge(gas, on="date", how="left")
    panel = panel.merge(fx, on="date", how="left")
    panel = panel.dropna(subset=["gas", "fx"])
    
    # Add time trend
    panel["trend"] = panel.groupby("country").cumcount()
    
    # Estimate DiD
    model = smf.ols("index_100 ~ post + treated + did + gas + fx + trend", data=panel).fit(
        cov_type="cluster", cov_kwds={"groups": panel["country"]})
    
    print(model.summary())
    
    did_coef = model.params.get("did", 0)
    did_pval = model.pvalues.get("did", 1)
    did_se = model.bse.get("did", 0)
    
    print(f"\n  KEY RESULTS:")
    print(f"  DiD Estimator (β₃):  {did_coef:+.2f} index points")
    print(f"  Standard Error:      {did_se:.2f}")
    print(f"  P-value:             {did_pval:.4f}")
    print(f"  95% CI:              [{did_coef - 1.96*did_se:.2f}, {did_coef + 1.96*did_se:.2f}]")
    print(f"  Interpretation:      The tariff caused Canadian fertilizer prices to be")
    print(f"                       {abs(did_coef):.1f} index points {'higher' if did_coef > 0 else 'lower'}")
    print(f"                       than they would have been absent the tariff,")
    print(f"                       controlling for global market conditions.")
    
    # Translate to % of pre-tariff mean
    pre_ca_mean = ca[ca["date"] < TARIFF_DATE]["index_100"].mean()
    pct_effect = did_coef / pre_ca_mean * 100
    print(f"\n  As % of pre-tariff Canadian level: {pct_effect:+.1f}%")
    
    return model, panel


# ── Chart 14: Summary Dashboard ─────────────────────────────────────────────
def chart_summary(ca_df, us_df, pt_model, did_model, merged):
    """Final summary dashboard with key findings."""
    
    # Rebase
    ca = ca_df.copy()
    us = us_df.copy()
    ca["idx"] = rebase_index(ca["value"], dates=ca["date"])
    us["idx"] = rebase_index(us["value"], dates=us["date"])
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "Canada vs US Nitrogen Fertilizer Index (2019=100)",
            "Tariff Effect Decomposition",
            "Key Econometric Results",
            "Trade Diversion Evidence",
        ],
        specs=[[{"type": "scatter"}, {"type": "bar"}],
               [{"type": "table"}, {"type": "bar"}]],
        vertical_spacing=0.12,
        horizontal_spacing=0.10,
    )
    
    # Panel 1: Index comparison
    fig.add_trace(go.Scatter(
        x=ca["date"], y=ca["idx"],
        name="Canada", line=dict(color=COLORS["canada"], width=2.5),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=us["date"], y=us["idx"],
        name="US", line=dict(color=COLORS["us"], width=2.5),
    ), row=1, col=1)
    
    # Panel 2: Effect decomposition
    pt_tariff = (np.exp(pt_model.params.get("tariff", 0)) - 1) * 100
    did_coef = did_model.params.get("did", 0)
    pre_ca = ca[ca["date"] < TARIFF_DATE]["idx"].mean()
    did_pct = did_coef / pre_ca * 100
    
    labels = ["Pass-Through\nModel", "DiD\nModel"]
    values = [pt_tariff, did_pct]
    colors = [COLORS["canada"], COLORS["diff"]]
    
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=[f"{v:+.1f}%" for v in values],
        textposition="outside",
        showlegend=False,
    ), row=1, col=2)
    
    # Panel 3: Results table
    pt_r2 = pt_model.rsquared
    pt_pval = pt_model.pvalues.get("tariff", 1)
    did_pval = did_model.pvalues.get("did", 1)
    did_se = did_model.bse.get("did", 0)
    
    fig.add_trace(go.Table(
        header=dict(
            values=["<b>Metric</b>", "<b>Value</b>"],
            fill_color="#1e293b",
            font_color="white",
            align="left",
        ),
        cells=dict(
            values=[
                ["Pass-Through R²", "Tariff Coeff (log)", "Tariff p-value",
                 "DiD Estimator", "DiD Std Error", "DiD p-value",
                 "Tariff % Effect (PT)", "Tariff % Effect (DiD)"],
                [f"{pt_r2:.3f}", f"{pt_model.params.get('tariff', 0):.4f}", 
                 f"{pt_pval:.4f}",
                 f"{did_coef:+.2f} pts", f"{did_se:.2f}",
                 f"{did_pval:.4f}",
                 f"{pt_tariff:+.1f}%", f"{did_pct:+.1f}%"],
            ],
            fill_color=[["#f8fafc", "#f1f5f9"] * 4],
            align="left",
        ),
    ), row=2, col=1)
    
    # Panel 4: Trade diversion bars
    trade_labels = ["Russia\n(Pre)", "Russia\n(Post)", "US\n(Pre)", "US\n(Post)"]
    trade_values = [6.1, 0.0, 30.4, 74.0]  # from CIMT analysis
    trade_colors = ["#fca5a5", "#dc2626", "#93c5fd", "#2563eb"]
    
    fig.add_trace(go.Bar(
        x=trade_labels, y=trade_values,
        marker_color=trade_colors,
        text=[f"${v:.1f}M" for v in trade_values],
        textposition="outside",
        showlegend=False,
    ), row=2, col=2)
    
    # Tariff line on panel 1
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper", xref="x",
                  line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    
    fig.update_layout(
        title=dict(
            text="Fertilizer Tariff Incidence Research — Summary Dashboard<br>"
                 "<sub>Canada's 35% tariff on Russian fertilizer (March 2022) | Two-model estimation</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=800,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "14_research_summary.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"\n  [14] Saved: {out.name}")
    return fig


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("   ECONOMETRIC ANALYSIS — Phase 2")
    print("=" * 70)
    print()
    
    # Load data
    print("Loading datasets...")
    ca = load_canada_fipi()
    us = load_us_nass()
    gas, fx, freight, bench = load_controls()
    
    print(f"  Canada FIPI:  {len(ca)} months ({ca['date'].min():%b %Y} – {ca['date'].max():%b %Y})")
    print(f"  US NASS:      {len(us)} months ({us['date'].min():%b %Y} – {us['date'].max():%b %Y})")
    print()
    
    # Chart 11: Canada vs US comparison
    print("Generating DiD comparison...")
    merged = chart_did_comparison(ca, us)
    
    # Chart 12: Event study
    print("\nGenerating event study...")
    chart_event_study(merged)
    
    # Model 1: Pass-through regression
    pt_model, pt_panel = model_passthrough(ca, gas, fx, bench)
    
    # Model 2: DiD
    did_model, did_panel = model_did(ca, us, gas, fx)
    
    # Chart 14: Summary dashboard
    print("\nGenerating summary dashboard...")
    chart_summary(ca, us, pt_model, did_model, merged)
    
    print("\n" + "=" * 70)
    print("   ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"  All charts saved to: {CHART_DIR}")


if __name__ == "__main__":
    main()
