"""
Tariff Incidence Research — CIMT Trade Data Analysis
====================================================
Analyzes the Canadian International Merchandise Trade data the user
downloaded from the CIMT Web Application.

Files available:
  - cimt_3102_all_countries_canada.csv  (HS 3102, Canada total, all countries)
  - cimt_3102_all_countries_ontario.csv (HS 3102, Ontario, all countries)
  - cimt_3105_all_countries_ontario.csv (HS 3105, Ontario, all countries)

Charts produced:
  6. Russia Import Collapse — HS 3102 Canada-wide
  7. Trade Diversion — Top suppliers pre/post tariff
  8. Ontario Import Mix — HS 3102 by country
  9. CIF Unit Value Trends — $/kg by major supplier
  10. Ontario HS 3105 Compound Fertilizer Trade

All chart HTML files saved to: data/latest/tariff_research/charts/
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data" / "latest"
CIMT_DIR = DATA / "cimt_trade"
CHART_DIR = DATA / "tariff_research" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

TARIFF_DATE = pd.Timestamp("2022-03-03")
TARIFF_DATE_STR = "2022-03-03"

COLORS = {
    "russia":    "#dc2626",
    "us":        "#2563eb",
    "trinidad":  "#059669",
    "morocco":   "#f97316",
    "other":     "#94a3b8",
    "tariff":    "#dc2626",
    "pre":       "#93c5fd",
    "post":      "#fca5a5",
}

COUNTRY_COLORS = {
    "Russian Federation": "#dc2626",
    "United States": "#2563eb",
    "Trinidad and Tobago": "#059669",
    "Morocco": "#f97316",
    "Egypt": "#a855f7",
    "Qatar": "#06b6d4",
    "Belarus": "#ec4899",
    "Oman": "#eab308",
    "Lithuania": "#22c55e",
    "Algeria": "#78716c",
    "Saudi Arabia": "#84cc16",
    "Germany": "#f43f5e",
    "Mexico": "#14b8a6",
    "Other": "#94a3b8",
}


# ── Data Loading ─────────────────────────────────────────────────────────────
def load_cimt(filename):
    """Load a CIMT CSV file, clean it up."""
    path = CIMT_DIR / filename
    if not path.exists():
        print(f"  WARNING: {filename} not found, skipping")
        return pd.DataFrame()
    
    df = pd.read_csv(path, skiprows=1)  # First row is "Imports"
    
    # Clean up — drop footer rows (contain URL)
    df = df[df["Period"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)].copy()
    
    df["date"] = pd.to_datetime(df["Period"])
    df["value_cad"] = pd.to_numeric(df["Value ($)"].astype(str).str.replace(",", ""), errors="coerce")
    df["quantity_kg"] = pd.to_numeric(df["Quantity"].astype(str).str.replace(",", ""), errors="coerce")
    
    # Extract HS4 code from commodity description
    df["hs4"] = df["Commodity"].str[:7]  # e.g., "3102.90"
    
    # Calculate unit value ($/kg)
    df["unit_value"] = df["value_cad"] / df["quantity_kg"]
    df.loc[df["unit_value"].isin([np.inf, -np.inf]), "unit_value"] = np.nan
    
    return df


def aggregate_monthly(df, group_col="Country"):
    """Aggregate to monthly totals by country."""
    agg = df.groupby(["date", group_col]).agg(
        value_cad=("value_cad", "sum"),
        quantity_kg=("quantity_kg", "sum"),
    ).reset_index()
    agg["unit_value"] = agg["value_cad"] / agg["quantity_kg"]
    agg.loc[agg["unit_value"].isin([np.inf, -np.inf]), "unit_value"] = np.nan
    return agg


def classify_top_countries(df, top_n=7):
    """Classify countries into top-N + 'Other'."""
    totals = df.groupby("Country")["value_cad"].sum().sort_values(ascending=False)
    top = totals.head(top_n).index.tolist()
    df["country_group"] = df["Country"].where(df["Country"].isin(top), "Other")
    return df, top


# ── Chart 6: Russia Import Collapse ─────────────────────────────────────────
def chart_russia_collapse(df_canada):
    """Show total Canada HS 3102 imports with Russia highlighted."""
    if df_canada.empty:
        print("  [6/10] SKIPPED: No Canada-wide HS 3102 data")
        return None
    
    monthly = aggregate_monthly(df_canada)
    
    # Separate Russia vs Rest
    russia = monthly[monthly["Country"] == "Russian Federation"].copy()
    rest = monthly[monthly["Country"] != "Russian Federation"].groupby("date").agg(
        value_cad=("value_cad", "sum"),
        quantity_kg=("quantity_kg", "sum"),
    ).reset_index()
    
    fig = go.Figure()
    
    # Rest of world
    fig.add_trace(go.Bar(
        x=rest["date"], y=rest["quantity_kg"] / 1e6,
        name="Rest of World",
        marker_color="#93c5fd",
        hovertemplate="RoW: %{y:.1f}M kg<br>%{x|%b %Y}<extra></extra>",
    ))
    
    # Russia
    if not russia.empty:
        fig.add_trace(go.Bar(
            x=russia["date"], y=russia["quantity_kg"] / 1e6,
            name="Russian Federation",
            marker_color=COLORS["russia"],
            hovertemplate="Russia: %{y:.1f}M kg<br>%{x|%b %Y}<extra></extra>",
        ))
    
    # Tariff event
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper",
                  line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper",
                       text="35% Tariff<br>(Mar 2022)", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    fig.update_layout(
        title=dict(
            text="Canadian Nitrogen Fertilizer Imports (HS 3102) — Russia Collapse<br>"
                 "<sub>Monthly import volume, millions of kg | Source: Statistics Canada CIMT</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        barmode="stack",
        yaxis_title="Import Volume (millions kg)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "06_russia_import_collapse.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [6/10] Saved: {out.name}")
    
    # Stats
    if not russia.empty:
        pre_russia = russia[russia["date"] < TARIFF_DATE]["quantity_kg"].sum() / 1e6
        post_russia = russia[russia["date"] >= TARIFF_DATE]["quantity_kg"].sum() / 1e6
        print(f"         Russia pre-tariff total:  {pre_russia:.1f}M kg")
        print(f"         Russia post-tariff total: {post_russia:.1f}M kg")
        if pre_russia > 0:
            print(f"         Change: {(post_russia/pre_russia - 1)*100:+.0f}%")
    
    return fig


# ── Chart 7: Trade Diversion — Top Suppliers ────────────────────────────────
def chart_trade_diversion(df_canada):
    """Sunburst-style comparison of import sources pre vs post tariff."""
    if df_canada.empty:
        print("  [7/10] SKIPPED: No Canada-wide HS 3102 data")
        return None
    
    df_canada, top_countries = classify_top_countries(df_canada)
    monthly = aggregate_monthly(df_canada, "country_group")
    
    # Pre vs post aggregation
    pre = monthly[monthly["date"] < TARIFF_DATE].groupby("country_group")["value_cad"].sum().reset_index()
    post = monthly[monthly["date"] >= TARIFF_DATE].groupby("country_group")["value_cad"].sum().reset_index()
    
    pre["period"] = "Pre-Tariff (2019 – Feb 2022)"
    post["period"] = "Post-Tariff (Mar 2022 – 2024)"
    
    combined = pd.concat([pre, post])
    
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "pie"}, {"type": "pie"}]],
                        subplot_titles=["Pre-Tariff (2019 – Feb 2022)", 
                                       "Post-Tariff (Mar 2022 – 2024)"])
    
    colors_list = [COUNTRY_COLORS.get(c, "#94a3b8") for c in pre["country_group"]]
    fig.add_trace(go.Pie(
        labels=pre["country_group"], values=pre["value_cad"],
        marker=dict(colors=colors_list),
        textinfo="label+percent",
        hole=0.3,
        hovertemplate="%{label}: $%{value:,.0f}<br>%{percent}<extra></extra>",
    ), row=1, col=1)
    
    colors_list2 = [COUNTRY_COLORS.get(c, "#94a3b8") for c in post["country_group"]]
    fig.add_trace(go.Pie(
        labels=post["country_group"], values=post["value_cad"],
        marker=dict(colors=colors_list2),
        textinfo="label+percent",
        hole=0.3,
        hovertemplate="%{label}: $%{value:,.0f}<br>%{percent}<extra></extra>",
    ), row=1, col=2)
    
    fig.update_layout(
        title=dict(
            text="Trade Diversion — HS 3102 Nitrogen Fertilizer Import Sources (Canada)<br>"
                 "<sub>Import value (CAD) share by country of origin</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        margin=dict(t=100, b=40, l=40, r=40),
    )
    
    out = CHART_DIR / "07_trade_diversion.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [7/10] Saved: {out.name}")
    return fig


# ── Chart 8: Ontario Import Mix ─────────────────────────────────────────────
def chart_ontario_imports(df_ontario):
    """Stacked area chart of Ontario HS 3102 imports by country over time."""
    if df_ontario.empty:
        print("  [8/10] SKIPPED: No Ontario HS 3102 data")
        return None
    
    df_ontario, top_countries = classify_top_countries(df_ontario, top_n=6)
    monthly = aggregate_monthly(df_ontario, "country_group")
    
    # Pivot to wide for stacked area
    pivot = monthly.pivot_table(index="date", columns="country_group", 
                                values="quantity_kg", aggfunc="sum").fillna(0)
    
    # Order columns by total volume
    col_order = pivot.sum().sort_values(ascending=False).index.tolist()
    
    fig = go.Figure()
    for country in col_order:
        color = COUNTRY_COLORS.get(country, "#94a3b8")
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[country] / 1e6,
            name=country,
            stackgroup="one",
            line=dict(width=0.5, color=color),
            fillcolor=color.replace(")", ",0.6)").replace("rgb", "rgba") if "rgb" in color else color,
            hovertemplate=f"{country}: %{{y:.2f}}M kg<br>%{{x|%b %Y}}<extra></extra>",
        ))
    
    # Tariff event
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper",
                  line=dict(color="white", width=3, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper",
                       text="35% Tariff", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"],
                                 weight="bold"),
                       bgcolor="white", bordercolor=COLORS["tariff"])
    
    fig.update_layout(
        title=dict(
            text="Ontario Nitrogen Fertilizer Imports (HS 3102) by Country<br>"
                 "<sub>Monthly import volume, millions of kg | Source: Statistics Canada CIMT</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        yaxis_title="Import Volume (millions kg)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "08_ontario_import_mix.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [8/10] Saved: {out.name}")
    return fig


# ── Chart 9: CIF Unit Value Trends ──────────────────────────────────────────
def chart_unit_values(df_canada):
    """CIF unit value ($/kg) by major supplier over time."""
    if df_canada.empty:
        print("  [9/10] SKIPPED: No Canada-wide HS 3102 data")
        return None
    
    # Focus on top suppliers
    top_suppliers = ["Russian Federation", "United States", "Trinidad and Tobago",
                     "Morocco", "Egypt", "Qatar"]
    
    monthly = aggregate_monthly(df_canada)
    monthly = monthly[monthly["Country"].isin(top_suppliers)]
    monthly = monthly[monthly["unit_value"].notna() & (monthly["unit_value"] > 0) & (monthly["unit_value"] < 5)]
    
    fig = go.Figure()
    
    for country in top_suppliers:
        subset = monthly[monthly["Country"] == country].sort_values("date")
        if subset.empty:
            continue
        
        color = COUNTRY_COLORS.get(country, "#94a3b8")
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["unit_value"],
            name=country,
            line=dict(color=color, width=2),
            mode="lines+markers",
            marker=dict(size=4),
            hovertemplate=f"{country}<br>%{{x|%b %Y}}: $%{{y:.3f}}/kg<extra></extra>",
        ))
    
    # Tariff event
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper",
                  line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper",
                       text="35% Tariff", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    fig.update_layout(
        title=dict(
            text="CIF Unit Value — Nitrogen Fertilizer (HS 3102) by Country<br>"
                 "<sub>CAD per kg | Higher = more expensive per unit | Source: CIMT (Value / Quantity)</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        yaxis_title="CAD per kg",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "09_cif_unit_values.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [9/10] Saved: {out.name}")
    
    # Print key unit value stats
    pre_russia = monthly[(monthly["Country"] == "Russian Federation") & (monthly["date"] < TARIFF_DATE)]["unit_value"]
    post_russia = monthly[(monthly["Country"] == "Russian Federation") & (monthly["date"] >= TARIFF_DATE)]["unit_value"]
    pre_us = monthly[(monthly["Country"] == "United States") & (monthly["date"] < TARIFF_DATE)]["unit_value"]
    post_us = monthly[(monthly["Country"] == "United States") & (monthly["date"] >= TARIFF_DATE)]["unit_value"]
    
    if not pre_russia.empty:
        print(f"         Russia CIF $/kg:  pre={pre_russia.mean():.3f}  post={post_russia.mean():.3f}" if not post_russia.empty else f"         Russia CIF $/kg:  pre={pre_russia.mean():.3f}  post=N/A (imports stopped)")
    if not pre_us.empty and not post_us.empty:
        print(f"         US CIF $/kg:      pre={pre_us.mean():.3f}  post={post_us.mean():.3f}")
    
    return fig


# ── Chart 10: Ontario HS 3105 Compound ───────────────────────────────────────
def chart_ontario_3105(df_3105):
    """Ontario HS 3105 (compound fertilizer) import trends."""
    if df_3105.empty:
        print("  [10/10] SKIPPED: No Ontario HS 3105 data")
        return None
    
    df_3105, top_countries = classify_top_countries(df_3105, top_n=6)
    monthly = aggregate_monthly(df_3105, "country_group")
    
    # Line chart of total volume + Russia highlighted
    total = monthly.groupby("date").agg(
        value_cad=("value_cad", "sum"),
        quantity_kg=("quantity_kg", "sum"),
    ).reset_index()
    
    russia_3105 = monthly[monthly["country_group"] == "Russian Federation"]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=total["date"], y=total["value_cad"] / 1e6,
        name="Total HS 3105 Imports",
        line=dict(color="#2563eb", width=3),
        fill="tozeroy",
        fillcolor="rgba(37, 99, 235, 0.1)",
        hovertemplate="Total: $%{y:.1f}M<br>%{x|%b %Y}<extra></extra>",
    ))
    
    if not russia_3105.empty:
        fig.add_trace(go.Scatter(
            x=russia_3105["date"], y=russia_3105["value_cad"] / 1e6,
            name="Russian Federation",
            line=dict(color=COLORS["russia"], width=2.5),
            fill="tozeroy",
            fillcolor="rgba(220, 38, 38, 0.15)",
            hovertemplate="Russia: $%{y:.1f}M<br>%{x|%b %Y}<extra></extra>",
        ))
    
    # Tariff event
    fig.add_shape(type="line", x0=TARIFF_DATE_STR, x1=TARIFF_DATE_STR,
                  y0=0, y1=1, yref="paper",
                  line=dict(color=COLORS["tariff"], width=2, dash="dash"))
    fig.add_annotation(x=TARIFF_DATE_STR, y=1, yref="paper",
                       text="35% Tariff", showarrow=False,
                       xanchor="right", yanchor="top",
                       font=dict(size=11, color=COLORS["tariff"]))
    
    fig.update_layout(
        title=dict(
            text="Ontario Compound Fertilizer Imports (HS 3105)<br>"
                 "<sub>Monthly import value, millions CAD | Source: Statistics Canada CIMT</sub>",
            font=dict(size=16),
        ),
        template="plotly_white",
        height=500,
        yaxis_title="Import Value ($ millions CAD)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hovermode="x unified",
        margin=dict(t=100, b=40, l=60, r=20),
    )
    
    out = CHART_DIR / "10_ontario_hs3105_compound.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"  [10/10] Saved: {out.name}")
    return fig


# ── Summary Table ────────────────────────────────────────────────────────────
def print_trade_summary(df_canada, df_ontario):
    """Print a summary table of trade patterns."""
    print("\n" + "=" * 70)
    print("   TRADE PATTERN SUMMARY")
    print("=" * 70)
    
    for label, df in [("CANADA (HS 3102)", df_canada), ("ONTARIO (HS 3102)", df_ontario)]:
        if df.empty:
            continue
        
        pre = df[df["date"] < TARIFF_DATE]
        post = df[df["date"] >= TARIFF_DATE]
        
        print(f"\n  --- {label} ---")
        print(f"  {'Country':<25} {'Pre-Tariff ($M)':>16} {'Post-Tariff ($M)':>16} {'Change':>10}")
        print(f"  {'-'*67}")
        
        # Get top countries by total value
        totals = df.groupby("Country")["value_cad"].sum().sort_values(ascending=False).head(8)
        
        for country in totals.index:
            pre_val = pre[pre["Country"] == country]["value_cad"].sum() / 1e6
            post_val = post[post["Country"] == country]["value_cad"].sum() / 1e6
            pct = (post_val / pre_val - 1) * 100 if pre_val > 0 else float('inf')
            pct_str = f"{pct:+.0f}%" if abs(pct) < 10000 else "NEW"
            print(f"  {country:<25} {pre_val:>16.1f} {post_val:>16.1f} {pct_str:>10}")
        
        total_pre = pre["value_cad"].sum() / 1e6
        total_post = post["value_cad"].sum() / 1e6
        total_pct = (total_post / total_pre - 1) * 100 if total_pre > 0 else 0
        print(f"  {'TOTAL':<25} {total_pre:>16.1f} {total_post:>16.1f} {total_pct:>+9.0f}%")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("   CIMT TRADE DATA ANALYSIS")
    print("=" * 70)
    print()
    
    # Load available data
    print("Loading CIMT data...")
    df_3102_canada = load_cimt("cimt_3102_all_countries_canada.csv")
    df_3102_ontario = load_cimt("cimt_3102_all_countries_ontario.csv")
    df_3105_ontario = load_cimt("cimt_3105_all_countries_ontario.csv")
    
    for label, df in [("HS 3102 Canada", df_3102_canada), 
                      ("HS 3102 Ontario", df_3102_ontario),
                      ("HS 3105 Ontario", df_3105_ontario)]:
        if not df.empty:
            countries = df["Country"].nunique()
            print(f"  {label}: {len(df)} rows, {countries} countries, "
                  f"{df['date'].min():%b %Y} - {df['date'].max():%b %Y}")
    
    print("\nGenerating charts...")
    chart_russia_collapse(df_3102_canada)
    chart_trade_diversion(df_3102_canada)
    chart_ontario_imports(df_3102_ontario)
    chart_unit_values(df_3102_canada)
    chart_ontario_3105(df_3105_ontario)
    
    # Summary
    print_trade_summary(df_3102_canada, df_3102_ontario)
    
    print(f"\nAll charts saved to: {CHART_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
