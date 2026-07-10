import sys
import subprocess

try:
    import kaleido
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "kaleido==0.1.0.post1"])

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(r"c:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter")
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Import from the regional analysis script
import tariff_regional_analysis as tra

# Setup output dir
tra.CHART_DIR.mkdir(parents=True, exist_ok=True)

df = tra.load_fipi_regional("Nitrogen fertilizers")

print("Generating Chart 15 (Ontario vs West) as PNG...")
model_ont_west = tra.chart_ont_vs_west(df)

print("Generating Chart 16 (Regional Heatmap) as PNG...")
fig16 = tra.chart_regional_heatmap(df)

# Manually save the figures as png
import plotly.io as pio

# We have to rebuild figure 15 because the function returns the dataframe, not the figure
# So I will just patch the function or rely on the fact that we can just recreate it.
def save_chart_15():
    regions = ["Ontario", "Western Canada", "Canada"]
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fig = make_subplots(
        rows=2, cols=1, row_heights=[0.65, 0.35],
        subplot_titles=["Nitrogen Fertilizer Price Index — Ontario vs Western Canada", "Ontario–West Gap (positive = Ontario more expensive)"],
        vertical_spacing=0.10,
    )
    ont = df[df["GEO"] == "Ontario"].sort_values("date").copy()
    west = df[df["GEO"] == "Western Canada"].sort_values("date").copy()
    ont["idx"] = tra.rebase(ont["value"], ont["date"])
    west["idx"] = tra.rebase(west["value"], west["date"])
    
    for geo in regions:
        subset = df[df["GEO"] == geo].sort_values("date").copy()
        subset["idx"] = tra.rebase(subset["value"], subset["date"])
        color = tra.REGION_COLORS.get(geo, "#94a3b8")
        width = 3 if geo != "Canada" else 2
        dash = "solid" if geo != "Canada" else "dot"
        fig.add_trace(go.Scatter(x=subset["date"], y=subset["idx"], name=geo, line=dict(color=color, width=width, dash=dash), mode="lines+markers", marker=dict(size=5 if geo != "Canada" else 3)), row=1, col=1)
        
    merged = pd.merge(ont[["date", "idx"]], west[["date", "idx"]], on="date", suffixes=("_ont", "_west"))
    merged["gap"] = merged["idx_ont"] - merged["idx_west"]
    gap_colors = ["#dc2626" if v > 0 else "#2563eb" for v in merged["gap"]]
    fig.add_trace(go.Bar(x=merged["date"], y=merged["gap"], marker_color=gap_colors, showlegend=False), row=2, col=1)
    
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8", line_width=1, row=2, col=1)
    for xref in ["x", "x2"]:
        fig.add_shape(type="line", x0=tra.TARIFF_DATE_STR, x1=tra.TARIFF_DATE_STR, y0=0, y1=1, yref="paper", xref=xref, line=dict(color="#dc2626", width=2, dash="dash"))
    
    fig.update_layout(template="plotly_white", height=700, width=1000, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), margin=dict(t=80, b=40, l=60, r=20))
    fig.write_image(str(tra.CHART_DIR / "15_ontario_vs_west.png"), scale=2)

save_chart_15()

fig16.update_layout(width=1000)
fig16.write_image(str(tra.CHART_DIR / "16_regional_heatmap.png"), scale=2)
print("Saved PNGs!")
