from playwright.sync_api import sync_playwright
import os
from pathlib import Path

# Paths to the HTML charts
chart_dir = Path(r"c:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter\data\latest\tariff_research\charts")
html_15 = chart_dir / "15_ontario_vs_west.html"
html_16 = chart_dir / "16_regional_heatmap.html"

png_15 = chart_dir / "15_ontario_vs_west.png"
png_16 = chart_dir / "16_regional_heatmap.png"

def take_screenshot(html_path, out_path, width=1200, height=800):
    with sync_playwright() as p:
        # headless browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})
        
        # Load local HTML file
        file_url = f"file:///{html_path.resolve().as_posix()}"
        page.goto(file_url)
        
        # Wait for plotly to render
        page.wait_for_selector('.js-plotly-plot')
        page.wait_for_timeout(2000) # give it 2 extra seconds just in case
        
        # Screenshot
        page.screenshot(path=str(out_path))
        browser.close()
        print(f"Saved {out_path.name}")

if html_15.exists():
    take_screenshot(html_15, png_15, 1000, 700)
    
if html_16.exists():
    take_screenshot(html_16, png_16, 1000, 500)
