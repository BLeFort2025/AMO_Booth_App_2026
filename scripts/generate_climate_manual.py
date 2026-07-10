"""
Generate Climate Profile Developer Manual (Word .docx)
======================================================
Produces a comprehensive developer manual covering the Climate Profile
section's data pipeline, UI sections, and maintenance procedures.

Run:  python scripts/generate_climate_manual.py
"""

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from pathlib import Path

OUTPUT = Path(
    r"C:\Projects\Farm Finance Stats Dashboard"
    r"\Reports and supplemental information"
    r"\Rural Community Data Tabs"
    r"\Climate Profile Tab - Developer Manual.docx"
)


def _add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    return h


def _add_para(doc, text, bold=False, italic=False, style=None):
    p = doc.add_paragraph(style=style)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    return p


def _add_table(doc, headers, rows):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    # Data rows
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            t.rows[ri + 1].cells[ci].text = str(val)
    return t


def _add_code(doc, code_text):
    """Add a code block formatted paragraph."""
    p = doc.add_paragraph()
    run = p.add_run(code_text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(30, 30, 30)
    pf = p.paragraph_format
    pf.space_before = Pt(4)
    pf.space_after = Pt(4)
    return p


def build_manual():
    doc = Document()

    # ── Title ───────────────────────────────────────────────────────────
    title = doc.add_heading("Climate Profile — Developer Manual", level=0)
    doc.add_paragraph(
        "Rural Ontario Community Data Dashboard\n"
        "Page: 9_🏘️_Rural_Community_Data.py — Section §8b\n"
        "Last updated: February 2026"
    )

    # ── Table of Contents ───────────────────────────────────────────────
    _add_heading(doc, "Table of Contents", level=1)
    toc_items = [
        "1. Overview",
        "2. Architecture & Data Flow",
        "3. Data Source — ECCC Climate Normals",
        "4. ETL Pipeline — fetch_climate_normals.py",
        "5. Climate Indicators Reference",
        "6. Output File Schema — climate_normals.csv",
        "7. User Interface (Section §8b)",
        "8. Chart & Visualization Details",
        "9. Ontario Median Benchmark Lines",
        "10. Station Distance Warnings",
        "11. Pipeline Integration — run_pipeline.py",
        "12. Maintenance & Update Guide",
        "13. Troubleshooting",
        "14. Deprecated Components (Pipeline A)",
        "15. Expert Audit History",
    ]
    for item in toc_items:
        doc.add_paragraph(item, style="List Number")

    # ══════════════════════════════════════════════════════════════════════
    # 1. OVERVIEW
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "1. Overview", level=1)
    doc.add_paragraph(
        "The Climate Profile module provides rural Ontario decision-makers with "
        "a station-based climate baseline for their community. It answers the "
        'question: "What is the historical climate profile of our municipality, '
        'and how does it compare to the Ontario median?"'
    )
    doc.add_paragraph(
        "The module consists of two main components:"
    )
    doc.add_paragraph(
        "An ETL script (fetch_climate_normals.py) that fetches 1981-2010 Climate "
        "Normals from the Environment and Climate Change Canada (ECCC) Geomet OGC "
        "API, maps each Ontario Census Subdivision (CSD) to its nearest weather "
        "station using area-weighted centroids and Haversine distance, and outputs "
        "a wide-format CSV with 9 annual climate indicators per CSD.",
        style="List Bullet"
    )
    doc.add_paragraph(
        "A standalone UI section (§8b) within the Rural Community Data page that "
        "visualizes climate indicators across four tabbed charts (Temperature, "
        "Rain & Precipitation, Snowfall, Growing Season), with Ontario median "
        "reference lines, station distance warnings, and full data tables.",
        style="List Bullet"
    )
    _add_para(doc,
        "Key design principle: Climate normals are HISTORICAL AVERAGES (1981-2010), "
        "not current conditions or future projections. The UI and documentation "
        "consistently use the scientifically accurate term 'normals' and display "
        "transparent caveats about the data's vintage and methodology.",
        bold=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # 2. ARCHITECTURE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "2. Architecture & Data Flow", level=1)

    _add_heading(doc, "2.1 Data Flow Diagram", level=2)
    doc.add_paragraph(
        "ECCC Geomet OGC API (live, no auth)\n"
        "    ↓  fetch_climate_normals.py (automated ETL)\n"
        "CSD Boundaries GeoJSON (ontario_csd_boundaries.geojson)\n"
        "    ↓  shapely centroid → Haversine nearest-station matching\n"
        "WIDE CSV (data/latest/wellbeing/climate_normals.csv)\n"
        "    ↓  Streamlit Page §8b\n"
        "Interactive charts, tables, station info, and distance warnings"
    )

    _add_heading(doc, "2.2 File Inventory", level=2)
    _add_table(doc,
        ["File", "Layer", "Purpose"],
        [
            ["scripts/fetch_climate_normals.py", "ETL",
             "Fetches ECCC normals, maps CSDs to stations, outputs CSV"],
            ["data/latest/wellbeing/climate_normals.csv", "Output",
             "Wide-format climate normals (577 CSDs × 15 columns)"],
            ["data/latest/wellbeing/ontario_csd_boundaries.geojson", "Input",
             "CSD polygon boundaries for centroid computation"],
            ["data/latest/wellbeing/dim_geography.csv", "Input",
             "CSD names and county lookup for community labels"],
            ["app/pages/9_🏘️_Rural_Community_Data.py", "UI",
             "Streamlit page (Climate Profile in §8b, lines ~2332-2530)"],
            ["scripts/run_pipeline.py", "Orchestrator",
             "Calls fetch_climate_normals.run() during full pipeline runs"],
        ],
    )

    _add_heading(doc, "2.3 Dependencies", level=2)
    _add_table(doc,
        ["Package", "Purpose", "Install"],
        [
            ["pandas", "DataFrame processing", "pip install pandas"],
            ["requests", "HTTP client for ECCC API", "pip install requests"],
            ["shapely", "Area-weighted CSD centroid computation", "pip install shapely"],
            ["tenacity (pattern)", "Retry with exponential backoff (hand-rolled)", "Built-in"],
            ["plotly.express", "Chart rendering in Streamlit UI", "pip install plotly"],
            ["streamlit", "Dashboard framework", "pip install streamlit"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 3. DATA SOURCE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "3. Data Source — ECCC Climate Normals", level=1)

    doc.add_paragraph(
        "All climate data originates from Environment and Climate Change Canada's "
        "Climate Normals 1981-2010 dataset, served via the Geomet OGC Features API."
    )
    _add_table(doc,
        ["Property", "Value"],
        [
            ["Dataset", "Climate Normals 1981-2010"],
            ["Provider", "Environment and Climate Change Canada (ECCC)"],
            ["API Endpoint", "https://api.weather.gc.ca/collections/climate-normals/items"],
            ["Protocol", "OGC Features API (JSON)"],
            ["Authentication", "None required (public, free)"],
            ["Geographic Filter", "Ontario bounding box: -95.2,41.6,-74.3,56.9"],
            ["Station Filter", "CURRENT_FLAG=Y (active stations only)"],
            ["Temporal Coverage", "30-year averages: 1981-2010"],
            ["Data Immutability", "Historical facts — values will never change"],
            ["Rate Limiting", "No official limit; pipeline uses 0.3s sleep + exponential backoff"],
        ],
    )

    _add_heading(doc, "3.1 What Are Climate Normals?", level=2)
    doc.add_paragraph(
        "Climate normals are 30-year statistical averages of daily weather observations, "
        "computed per the World Meteorological Organization (WMO) standard. The 1981-2010 "
        "normals are the most recent complete set available from ECCC. They represent the "
        "'baseline climate' against which anomalies and trends are measured."
    )
    _add_para(doc,
        "Important: Climate normals are NOT projections, forecasts, or current conditions. "
        "They are historical averages. The pipeline and UI consistently use the word 'normals' "
        "(not 'projections') to maintain scientific accuracy and user trust.",
        bold=True,
    )

    _add_heading(doc, "3.2 API Response Structure", level=2)
    doc.add_paragraph(
        "Each API response returns GeoJSON features. Each feature represents one station-"
        "month-element combination. Key properties:"
    )
    _add_table(doc,
        ["Property", "Description", "Example"],
        [
            ["CLIMATE_IDENTIFIER", "Unique station ID", "6104025"],
            ["STATION_NAME", "Human-readable station name", "TORONTO PEARSON INT'L A"],
            ["E_NORMAL_ELEMENT_NAME", "Climate element description", "Mean daily temperature deg C"],
            ["NORMAL_ID", "Numeric element identifier", "1"],
            ["MONTH", "Month number (1-12)", "7"],
            ["VALUE", "Monthly normal value", "21.5"],
            ["CURRENT_FLAG", "Whether station is active", "Y"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 4. ETL PIPELINE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "4. ETL Pipeline — fetch_climate_normals.py", level=1)
    doc.add_paragraph(
        "Script: scripts/fetch_climate_normals.py\n"
        "Output: data/latest/wellbeing/climate_normals.csv\n"
        "Invocation: python scripts/fetch_climate_normals.py (or via run_pipeline.py)"
    )

    _add_heading(doc, "4.1 Processing Steps", level=2)
    steps = [
        "Step 1 — Compute CSD centroids: Load ontario_csd_boundaries.geojson, "
        "parse DGUIDs via regex (r'35\\d{5}'), compute area-weighted centroids using "
        "shapely.geometry.shape().centroid for each CSD polygon.",

        "Step 2 — Fetch station inventory: Query the ECCC API for January mean temperature "
        "(NORMAL_ID=1) across Ontario to discover all active stations. Extract station ID, "
        "name, lat/lon from each feature. Result: ~124 unique stations.",

        "Step 3 — Map CSDs to nearest stations: For each of the ~577 CSD centroids, "
        "compute Haversine distance to all stations and select the nearest one. Record "
        "the distance in km and flag any mapping where distance exceeds 50 km "
        "(DISTANCE_WARNING_KM constant).",

        "Step 4 — Fetch climate normals: For each of the 9 climate elements (mapped via "
        "ELEMENT_MAP), fetch all monthly values for assigned stations. Request pagination "
        "uses limit=2000 with 0.3s sleep between pages.",

        "Step 5 — Aggregate monthly → annual: Apply aggregation rules per indicator: "
        "SUM for cumulative metrics (precip, rain, snow, GDD, frost days, hot days) "
        "requiring exactly 12 months; AVERAGE for temperature metrics also requiring exactly "
        "12 months (N1 audit fix — prevents seasonal skew from missing summer/winter months). "
        "Divisor for AVERAGE is hardcoded to 12.0.",

        "Step 6 — Build CSD profiles: Join station climate data to CSDs via the station "
        "mapping. Enrich with community names and county from dim_geography.csv. "
        "Include nearest_station, station_distance_km, and distance_warning columns.",

        "Step 7 — Safety guard: If the result DataFrame is empty, contains no climate "
        "columns, or covers fewer than 80% of computed centroids (N5 audit fix), skip the "
        "CSV write to prevent overwriting a good fallback file with truncated data.",

        "Step 8 — Save to CSV: Write final DataFrame to climate_normals.csv. Print "
        "summary statistics (mean, range) for all 9 indicators.",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")

    _add_heading(doc, "4.2 Centroid Computation (Q7 Audit Fix)", level=2)
    doc.add_paragraph(
        "CSD centroids are computed using the shapely library's area-weighted centroid, "
        "which correctly handles irregular polygons and multi-polygons. The previous "
        "implementation used the arithmetic mean of all vertex coordinates, which could "
        "produce centroids outside the polygon for concave shapes."
    )
    _add_code(doc,
        "from shapely.geometry import shape as shapely_shape\n"
        "geom = shapely_shape(geom_dict)  # Parse GeoJSON geometry\n"
        "centroid = geom.centroid          # Area-weighted centroid\n"
        "centroids[sgc] = (centroid.y, centroid.x)  # (lat, lon)"
    )

    _add_heading(doc, "4.3 DGUID Parsing (Q13 Audit Fix)", level=2)
    doc.add_paragraph(
        "CSD codes (SGC codes) are extracted from DGUID strings using a robust regex "
        "pattern. Ontario CSDs always match the pattern 35XXXXX (7 digits starting with 35)."
    )
    _add_code(doc,
        "import re\n"
        "match = re.search(r'35\\d{5}', sgc_raw)\n"
        "if not match:\n"
        "    continue  # Skip non-Ontario or unparseable records\n"
        "sgc = match.group(0)  # e.g., '3523043'"
    )

    _add_heading(doc, "4.4 API Retry Logic (Q14 Audit Fix)", level=2)
    doc.add_paragraph(
        "API requests use an exponential backoff retry wrapper. The initial backoff is 1 "
        "second, doubling with each retry up to MAX_RETRIES=3 attempts. This handles "
        "transient network errors and API throttling without human intervention."
    )
    _add_code(doc,
        "MAX_RETRIES = 3\n"
        "INITIAL_BACKOFF_S = 1.0  # doubles each retry\n\n"
        "def _api_get(params, retries=MAX_RETRIES):\n"
        "    backoff = INITIAL_BACKOFF_S\n"
        "    for attempt in range(retries + 1):\n"
        "        try:\n"
        "            r = requests.get(NORMALS_URL, params=params, timeout=60)\n"
        "            r.raise_for_status()\n"
        "            return r.json()\n"
        "        except Exception as e:\n"
        "            if attempt == retries:\n"
        "                raise\n"
        "            time.sleep(backoff)\n"
        "            backoff *= 2"
    )

    _add_heading(doc, "4.5 Monthly Aggregation Rules (Q11 Audit Fix)", level=2)
    doc.add_paragraph(
        "Climate elements are aggregated from monthly to annual values using two "
        "distinct rules, preventing systematic underestimation:"
    )
    _add_table(doc,
        ["Rule", "Requirement", "Applies To", "Formula"],
        [
            ["SUM", "Exactly 12 months", "Precipitation, Rain, Snow, GDD, Frost Days, Hot Days",
             "annual = Σ(month_1..12)"],
            ["AVERAGE", "Exactly 12 months (N1 fix)", "Mean Temp, Max Temp, Min Temp",
             "annual = Σ(months) / 12.0"],
        ],
    )
    doc.add_paragraph(
        "Both SUM and AVERAGE paths enforce an identical strict 12-month completeness "
        "requirement (N1 audit fix). For 30-year normals, stations missing ANY month "
        "have non-standard records anyway and should be excluded. The previous threshold "
        "of 10 months for AVERAGE was identified as risky because missing July and August "
        "(the two warmest months) would artificially depress the annual mean by ~2-3°C."
    )

    _add_heading(doc, "4.6 Empty-Data Safeguard", level=2)
    doc.add_paragraph(
        "The pipeline implements a two-tier safety guard (N5 audit fix):\n"
        "1. Total failure: If result is empty or has no climate_ columns, abort.\n"
        "2. Partial failure: If the number of assembled CSDs is less than 80% of "
        "computed centroids (min_expected_csds = int(len(centroids) * 0.8)), abort.\n\n"
        "This prevents a partial API timeout from silently overwriting a good 577-row CSV "
        "with a truncated 100-row CSV, which would cause 477 communities to lose their "
        "climate data until the next successful run."
    )
    _add_code(doc,
        "min_expected_csds = int(len(centroids) * 0.8) if centroids else 400\n"
        "if result.empty or len(result) < min_expected_csds or not indicator_cols:\n"
        '    print(f"[ERROR] Insufficient data assembled ({len(result)} CSDs, '
        'need ≥{min_expected_csds}). Keeping existing CSV untouched.")\n'
        "    return None"
    )

    # ══════════════════════════════════════════════════════════════════════
    # 5. CLIMATE INDICATORS
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "5. Climate Indicators Reference", level=1)
    doc.add_paragraph(
        "The pipeline produces 9 climate indicators per CSD. Each is identified by "
        "a column slug in the output CSV and mapped to an ECCC NORMAL_ID for API retrieval."
    )
    _add_table(doc,
        ["Column Slug", "Display Label", "Unit", "ECCC Element", "NORMAL_ID", "Aggregation"],
        [
            ["climate_mean_temp", "Mean Temperature", "°C",
             "Mean daily temperature deg C", "1", "AVERAGE"],
            ["climate_max_temp", "Mean Daily Max Temp", "°C",
             "Mean daily max temperature deg C", "5", "AVERAGE"],
            ["climate_min_temp", "Mean Daily Min Temp", "°C",
             "Mean daily min temperature deg C", "8", "AVERAGE"],
            ["climate_total_precip", "Annual Precipitation", "mm",
             "Total precipitation mm", "56", "SUM"],
            ["climate_total_rain", "Annual Rainfall", "mm",
             "Total rainfall mm", "52", "SUM"],
            ["climate_total_snow", "Annual Snowfall", "cm",
             "Total snowfall cm", "54", "SUM"],
            ["climate_gdd", "Growing Degree Days (5°C)", "GDD",
             "Total degree-days Above 5 deg C", "26", "SUM"],
            ["climate_frost_days", "Frost Days (≤0°C)", "days",
             "Days with daily min temperature LE 0 deg C", "41", "SUM"],
            ["climate_hot_days", "Hot Days (>30°C)", "days",
             "Days with daily max temperature GT 30 deg C", "37", "SUM"],
        ],
    )

    _add_heading(doc, "5.1 Expected Value Ranges (Ontario)", level=2)
    doc.add_paragraph(
        "These ranges are from the current pipeline output (577 CSDs) and can serve "
        "as sanity-check thresholds for future pipeline runs:"
    )
    _add_table(doc,
        ["Indicator", "Mean", "Min", "Max"],
        [
            ["climate_mean_temp (°C)", "5.0", "-4.0", "9.9"],
            ["climate_max_temp (°C)", "10.3", "0.4", "14.4"],
            ["climate_min_temp (°C)", "-0.3", "-9.0", "5.8"],
            ["climate_total_precip (mm)", "900.0", "496.3", "1294.0"],
            ["climate_total_rain (mm)", "702.5", "315.3", "963.2"],
            ["climate_total_snow (cm)", "209.7", "79.2", "447.2"],
            ["climate_gdd (GDD)", "1859.6", "664.1", "2688.2"],
            ["climate_frost_days (days)", "173.3", "100.8", "233.3"],
            ["climate_hot_days (days)", "7.1", "0.4", "23.5"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 6. OUTPUT FILE SCHEMA
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "6. Output File Schema — climate_normals.csv", level=1)
    doc.add_paragraph(
        "The output CSV is in WIDE format — one row per CSD, with metadata and "
        "climate indicator columns."
    )
    _add_table(doc,
        ["Column", "Type", "Description"],
        [
            ["sgc_code", "str(7)", "7-digit Standard Geographical Classification code (35xxxxx)"],
            ["geo_name", "str", "CSD name without county context"],
            ["county", "str", "County or regional municipality name"],
            ["community", "str", "Full display name: 'Geo Name (County)' — e.g., 'Guelph (Wellington)'"],
            ["nearest_station", "str", "Name of the nearest ECCC weather station"],
            ["station_distance_km", "float", "Distance from CSD centroid to station (km)"],
            ["distance_warning", "bool", "True if distance > 50km (DISTANCE_WARNING_KM)"],
            ["climate_mean_temp", "float", "Annual mean temperature (°C)"],
            ["climate_max_temp", "float", "Mean daily maximum temperature (°C)"],
            ["climate_min_temp", "float", "Mean daily minimum temperature (°C)"],
            ["climate_total_precip", "float", "Annual total precipitation (mm)"],
            ["climate_total_rain", "float", "Annual total rainfall (mm)"],
            ["climate_total_snow", "float", "Annual total snowfall (cm)"],
            ["climate_gdd", "float", "Growing Degree Days above 5°C"],
            ["climate_frost_days", "float", "Days with minimum temp ≤ 0°C"],
            ["climate_hot_days", "float", "Days with maximum temp > 30°C"],
        ],
    )

    _add_heading(doc, "6.1 Current Dataset Statistics", level=2)
    _add_table(doc,
        ["Metric", "Value"],
        [
            ["Total CSDs", "577"],
            ["Unique stations matched", "115 (of 124 discovered)"],
            ["Median station distance", "23.3 km"],
            ["Max station distance", "488.7 km"],
            ["CSDs with distance warning", "123 (21%)"],
            ["File format", "Wide CSV (no index)"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 7. USER INTERFACE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "7. User Interface (Section §8b)", level=1)
    doc.add_paragraph(
        "Location: app/pages/9_🏘️_Rural_Community_Data.py, lines ~2332-2530\n"
        "Section header: '🌍 Environment — Climate Profile'\n"
        "Data source: climate_normals.csv (wide format, loaded with @st.cache_data ttl=3600)"
    )

    _add_heading(doc, "7.1 Gate Conditions", level=2)
    doc.add_paragraph(
        "The section renders only if BOTH conditions are met:"
    )
    doc.add_paragraph("CLIMATE_FILE.exists() — the CSV has been generated", style="List Bullet")
    doc.add_paragraph("selected_codes is non-empty — the user has selected at least one community", style="List Bullet")
    doc.add_paragraph(
        "If the CSV does not exist, a collapsed expander shows instructions for "
        "running the pipeline script."
    )

    _add_heading(doc, "7.2 Data Loading", level=2)
    doc.add_paragraph(
        "The _load_climate() function is decorated with @st.cache_data(ttl=3600) "
        "(1-hour cache). It applies the standard CSD normalization pipeline:"
    )
    steps = [
        "Read CSV via pd.read_csv(CLIMATE_FILE)",
        "Convert sgc_code to numeric (handles float strings like '3523043.0')",
        "Drop NaN sgc_codes",
        "Cast to int → str → zero-fill to 7 digits",
        "Filter to Ontario (startswith '35')",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")

    _add_heading(doc, "7.3 Section Layout", level=2)
    doc.add_paragraph("The section displays the following elements in order:")
    elements = [
        "Methodology caption (expanded, Q19 fix): explains data vintage and centroid methodology",
        "Station info line: shows nearest station name and distance for each selected community",
        "Distance warnings: ⚠️ icon on communities with station > 50km, with explanatory note",
        "Four tabbed charts: Temperature | Rain & Precipitation | Snowfall | Growing Season",
        "Expandable data table: all indicators, stations, and distances for selected communities",
        "Bottom caption: data source credit with flagging explanation",
    ]
    for e in elements:
        doc.add_paragraph(e, style="List Number")

    # ══════════════════════════════════════════════════════════════════════
    # 8. CHART DETAILS
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "8. Chart & Visualization Details", level=1)

    _add_heading(doc, "8.1 Tab Configuration", level=2)
    _add_table(doc,
        ["Tab", "Indicators", "Chart Type", "Y-Axis", "Rationale"],
        [
            ["Temperature", "mean_temp, max_temp, min_temp", "px.scatter (dot plot)", "°C",
             "Dot plot handles negative values cleanly; bar charts with negative bars are misleading"],
            ["Rain & Precipitation", "total_precip, total_rain", "px.bar (grouped)", "mm",
             "Same unit (mm); grouped bars for community comparison"],
            ["Snowfall", "total_snow", "px.bar (grouped)", "cm",
             "Separated from rain to avoid mixing mm and cm on one axis"],
            ["Growing Season (Chart 1)", "gdd", "px.bar (grouped)", "GDD",
             "GDD (~2000) isolated to prevent scale-crushing of smaller metrics (N3 fix)"],
            ["Growing Season (Chart 2)", "frost_days, hot_days", "px.bar (grouped)", "Days",
             "Threshold Days (<170) rendered separately for visual clarity (N3 fix)"],
        ],
    )

    _add_heading(doc, "8.2 Chart Rendering Function: _climate_chart()", level=2)
    doc.add_paragraph(
        "All four tabs are rendered by a single function _climate_chart() that accepts:"
    )
    _add_table(doc,
        ["Parameter", "Type", "Description"],
        [
            ["tab", "st.tab", "Streamlit tab container to render inside"],
            ["indicators", "list[str]", "Column slugs to include in the chart"],
            ["title", "str", "Chart title (displayed above the plot)"],
            ["y_label", "str", "Y-axis label (default: 'Value')"],
            ["use_scatter", "bool", "If True, use px.scatter instead of px.bar"],
        ],
    )

    _add_heading(doc, "8.3 Color Palette", level=2)
    doc.add_paragraph(
        "Community bars/dots use a fixed 5-color sequence:\n"
        "#e74c3c (red), #3498db (blue), #27ae60 (green), #f39c12 (orange), #9b59b6 (purple)\n\n"
        "This palette was chosen for visual distinction and colorblind accessibility. "
        "If more than 5 communities are selected, colors will cycle."
    )

    _add_heading(doc, "8.4 Community Names (Q18 Fix)", level=2)
    doc.add_paragraph(
        "Community names are displayed in full, including county context — e.g., "
        "'Guelph (Wellington)' instead of 'Guelph'. The .split(' (')[0] truncation "
        "that was previously applied has been removed. This ensures users can distinguish "
        "between communities with the same name in different counties."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 9. BENCHMARK LINES
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "9. Ontario Median Benchmark Lines", level=1)

    _add_heading(doc, "9.1 Methodology", level=2)
    doc.add_paragraph(
        "Each chart displays one Ontario median reference line per indicator. The median "
        "is computed over ALL CSDs in the climate_normals.csv dataset (not just the selected "
        "communities). This provides a province-wide benchmark for comparison."
    )
    doc.add_paragraph(
        "Formula: Ontario Median = median(climate_df[indicator]) over all 577 CSDs"
    )

    _add_heading(doc, "9.2 Per-Indicator Color Coding (Q15 Fix)", level=2)
    doc.add_paragraph(
        "Each indicator within a tab gets its own color-coded median line to prevent "
        "confusion when multiple indicators share the same chart. The color palette for "
        "median lines is:"
    )
    _add_table(doc,
        ["Index", "Color", "Hex"],
        [
            ["1st indicator", "Blue", "#1f77b4"],
            ["2nd indicator", "Orange", "#ff7f0e"],
            ["3rd indicator", "Green", "#2ca02c"],
            ["4th indicator", "Red", "#d62728"],
            ["5th indicator", "Purple", "#9467bd"],
        ],
    )
    doc.add_paragraph(
        "Each line uses line_dash='dot' with a 9pt annotation showing "
        "'Unweighted CSD Med ({Label}): {Value}' — the N10 audit fix ensures "
        "both statistical transparency (unweighted) and metric identification "
        "(label retained for multi-indicator chart legibility)."
    )

    _add_heading(doc, "9.3 Previous Issue: Single-Indicator Break", level=2)
    doc.add_paragraph(
        "The original implementation contained a 'break' statement inside the reference "
        "line loop, which caused only the FIRST indicator's median to be displayed. This "
        "was misleading when multiple indicators with different scales were on the same chart. "
        "The break was removed and replaced with a full loop that adds one median line per "
        "indicator with distinct colors."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 10. DISTANCE WARNINGS
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "10. Station Distance Warnings", level=1)

    _add_heading(doc, "10.1 Threshold", level=2)
    doc.add_paragraph(
        "Any CSD mapped to a weather station more than 50 km away is flagged with "
        "distance_warning=True in the CSV output. The threshold is defined as the constant "
        "DISTANCE_WARNING_KM=50 in fetch_climate_normals.py."
    )

    _add_heading(doc, "10.2 UI Presentation", level=2)
    doc.add_paragraph(
        "When a selected community has distance_warning=True, the UI displays:"
    )
    doc.add_paragraph("A ⚠️ icon next to the station name in the station info line", style="List Bullet")
    doc.add_paragraph(
        "An explanatory caption: '⚠️ Station is >50 km from community centroid — "
        "climate values may be less representative.'",
        style="List Bullet"
    )

    _add_heading(doc, "10.3 Design Decision: No Exclusion", level=2)
    doc.add_paragraph(
        "Communities mapped to distant stations are NOT excluded from the dataset. "
        "The expert review confirmed that excluding them would create 'data deserts' "
        "across Northern Ontario, disproportionately harming remote and Indigenous "
        "communities. In northern regions, weather systems are geographically massive, "
        "so a station 150 km away may still be a reasonable proxy."
    )
    _add_para(doc,
        "Principle: Transparency over omission. Provide the data with a clear warning, "
        "and let local decision-makers apply their own geographic judgment.",
        bold=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # 11. PIPELINE INTEGRATION
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "11. Pipeline Integration — run_pipeline.py", level=1)
    doc.add_paragraph(
        "fetch_climate_normals is integrated into the main pipeline orchestrator "
        "(scripts/run_pipeline.py) and runs automatically during full pipeline executions."
    )
    _add_code(doc,
        "# --- Tier 2: Climate Normals (ECCC API) ---\n"
        'print("\\nRunning Climate Normals Processor (ECCC Geomet API)...")\n'
        "try:\n"
        "    from scripts import fetch_climate_normals\n"
        "    fetch_climate_normals.run()\n"
        "except Exception as e:\n"
        '    print(f"[WARNING] Climate normals processing skipped: {e}")'
    )
    doc.add_paragraph(
        "The try/except wrapper ensures that if the ECCC API is temporarily unavailable, "
        "the climate step fails gracefully while the rest of the pipeline continues. The "
        "existing climate_normals.csv is preserved as a fallback (see §4.6)."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 12. MAINTENANCE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "12. Maintenance & Update Guide", level=1)

    _add_heading(doc, "12.1 Routine Refresh (Current Normals)", level=2)
    doc.add_paragraph(
        "Because 1981-2010 normals are immutable historical facts, the pipeline only "
        "needs to be re-run if:"
    )
    doc.add_paragraph("New CSDs are added to the ontario_csd_boundaries.geojson file", style="List Bullet")
    doc.add_paragraph("The existing climate_normals.csv is accidentally deleted", style="List Bullet")
    doc.add_paragraph("The ECCC API adds new stations (rare but possible)", style="List Bullet")
    doc.add_paragraph(
        "Under normal circumstances, the generated CSV should be committed to version "
        "control and treated as a permanent data asset."
    )

    _add_heading(doc, "12.2 Updating to 1991-2020 Normals (Future)", level=2)
    doc.add_paragraph(
        "ECCC is in the process of finalizing and publishing the 1991-2020 Climate Normals. "
        "When they become fully available via the Geomet API, the pipeline should be updated:"
    )
    steps = [
        "Verify that the new normals are available by querying the API with CURRENT_FLAG=Y",
        "No code changes are expected — the ECCC API returns the latest normals by default",
        "Run the pipeline: python scripts/fetch_climate_normals.py",
        "Verify the output: check indicator ranges against expected 1991-2020 values",
        "Update the docstring in fetch_climate_normals.py (line 4: '1981-2010' → '1991-2020')",
        "Update the UI caption text in 9_🏘️_Rural_Community_Data.py (line ~2382)",
        "Update the chart titles (pattern: 'Normals (1981-2010)' → 'Normals (1991-2020)')",
        "Commit the updated climate_normals.csv",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")
    _add_para(doc,
        "Note: Because the infrastructure is already solid, this will be a parameter update, "
        "not a code refactor.",
        italic=True,
    )

    _add_heading(doc, "12.3 Adding a New Climate Indicator", level=2)
    doc.add_paragraph(
        "To add a new indicator (e.g., heating degree days, wind speed), follow these steps:"
    )
    steps = [
        "Identify the ECCC E_NORMAL_ELEMENT_NAME and NORMAL_ID by probing the API "
        "(try different NORMAL_IDs with limit=1 to see available elements)",
        "Add the entry to ELEMENT_MAP in fetch_climate_normals.py: "
        "(element_name, normal_id): 'climate_new_slug'",
        "If the indicator is cumulative, add the slug to SUM_ELEMENTS; otherwise it defaults to AVERAGE",
        "Add a display entry to DISPLAY_NAMES in the ETL script",
        "Add the slug to CLIMATE_META in the Streamlit page",
        "Add the slug to the appropriate tab's indicator list (TEMP_INDICATORS, RAIN_INDICATORS, etc.) "
        "or create a new tab",
        "Re-run the pipeline and verify the new column appears in the CSV",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")

    _add_heading(doc, "12.4 Modifying the Distance Warning Threshold", level=2)
    doc.add_paragraph(
        "The 50 km threshold is defined as DISTANCE_WARNING_KM at line 65 of "
        "fetch_climate_normals.py. Changing this value and re-running the pipeline will "
        "update the distance_warning column in the CSV. The UI reads this column at "
        "runtime — no UI code changes are needed."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 13. TROUBLESHOOTING
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "13. Troubleshooting", level=1)
    _add_table(doc,
        ["Symptom", "Likely Cause", "Fix"],
        [
            ["Climate section shows 'data not yet loaded'",
             "climate_normals.csv not generated",
             "Run: python scripts/fetch_climate_normals.py"],
            ["'No climate data available for the selected communities'",
             "Selected CSDs not in the CSV (e.g., non-Ontario)",
             "Verify selected_codes are 7-digit Ontario SGC codes"],
            ["Pipeline prints '[ERROR] No CSD centroids available'",
             "ontario_csd_boundaries.geojson missing or empty",
             "Run: python scripts/fetch_csd_boundaries.py first"],
            ["API timeout / ConnectionError",
             "ECCC API temporarily down",
             "The retry logic will handle transient errors. If persistent, the "
             "existing CSV is preserved as fallback."],
            ["Indicator shows NaN for some communities",
             "Assigned station doesn't have data for that element",
             "Expected for very remote stations; no fix needed"],
            ["Temperature chart shows negative bars incorrectly",
             "Chart type accidentally changed to bar",
             "Ensure use_scatter=True for temperature tab call"],
            ["All median lines same color",
             "_MEDIAN_COLORS palette issue",
             "Check line ~2408 in the Streamlit page"],
            ["Station distance seems wrong",
             "Centroid computed from stale boundary file",
             "Re-run fetch_csd_boundaries.py then fetch_climate_normals.py"],
            ["ModuleNotFoundError: shapely",
             "shapely not installed",
             "Run: pip install shapely"],
            ["Chart shows mm and cm on same axis",
             "Indicator assigned to wrong tab group",
             "Check RAIN_INDICATORS vs SNOW_INDICATORS lists"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 14. DEPRECATED COMPONENTS
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "14. Deprecated Components (Pipeline A)", level=1)
    doc.add_paragraph(
        "The following components were deprecated and removed as part of the February 2026 "
        "expert audit. They are documented here for historical context only."
    )

    _add_heading(doc, "14.1 Pipeline A: fetch_climate.py (DELETED)", level=2)
    _add_table(doc,
        ["Property", "Detail"],
        [
            ["Script", "scripts/fetch_climate.py — DELETED"],
            ["Data Source", "Third-party GitHub CSV (minnzc/Canada_Daily_Climate)"],
            ["Output", "data/derived/climate_indicators.csv — DELETED"],
            ["Format", "Long format (sgc_code, indicator, value)"],
            ["Indicators", "6: mean_temp, max_temp, min_temp, total_precip, growing_days, frost_free_days"],
            ["Issues", "Non-standard GDD (count of days ≥5°C, not degree-sums); "
             "wrong frost-free definition (min>0, not season length); "
             "output never loaded by UI → ghost tab"],
        ],
    )

    _add_heading(doc, "14.2 Why Pipeline A Was Deprecated", level=2)
    doc.add_paragraph(
        "Pipeline A sourced data from an unofficial third-party GitHub repository with "
        "no provenance guarantees. Its indicator definitions were non-standard "
        "(e.g., Growing Degree Days counted days above 5°C rather than computing "
        "cumulative degree-sums, which is the accepted agronomic definition). "
        "Most critically, its output CSV (climate_indicators.csv) was NEVER loaded by "
        "the UI — the data was orphaned, creating a 'ghost tab' that appeared in the "
        "category list but displayed empty charts."
    )

    _add_heading(doc, "14.3 INDICATOR_META Cleanup", level=2)
    doc.add_paragraph(
        "Six ghost INDICATOR_META entries were removed as part of the deprecation:"
    )
    _add_code(doc,
        '# REMOVED — these were never displayed:\n'
        '"climate_mean_temp": ("Mean Temperature", "°C", "Climate"),\n'
        '"climate_max_temp": ("Hottest Day", "°C", "Climate"),\n'
        '"climate_min_temp": ("Coldest Day", "°C", "Climate"),\n'
        '"climate_total_precip": ("Annual Precipitation", "mm", "Climate"),\n'
        '"climate_growing_days": ("Growing Degree Days", "days", "Climate"),\n'
        '"climate_frost_free_days": ("Frost-Free Days", "days", "Climate"),'
    )
    doc.add_paragraph(
        "The 'Climate' category was also removed from the CATEGORIES list, and three "
        "climate indicators were removed from MAP_FRIENDLY_INDICATORS."
    )

    _add_heading(doc, "14.4 Pipeline A Output: fetch_climate_projections.py (DELETED)", level=2)
    doc.add_paragraph(
        "The predecessor of fetch_climate_normals.py was named fetch_climate_projections.py "
        "and output to climate_projections.csv. This naming was scientifically inaccurate — "
        "the data contained historical normals, not future projections. It was renamed to "
        "fetch_climate_normals.py during the audit."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 15. EXPERT AUDIT HISTORY
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "15. Expert Audit History", level=1)
    doc.add_paragraph(
        "The Climate Profile module underwent a comprehensive expert red team review "
        "in February 2026. The initial review returned a NO-GO verdict with 28 FAIL items "
        "across architectural, methodological, UI, and integration categories."
    )

    _add_heading(doc, "15.1 Initial Review: 28 FAIL Items", level=2)
    _add_table(doc,
        ["Category", "Question IDs", "Count", "Summary"],
        [
            ["Pipeline A & Ghost UI", "Q1-Q6, Q20-Q22, Q27-Q28", "11",
             "Competing data systems, orphaned data, ghost tabs"],
            ["Math & Geo", "Q7, Q11, Q13", "3",
             "Wrong centroid method, incomplete data aggregation, brittle parsing"],
            ["Terminology", "Q10, Q12, Q26", "3",
             "'Projections' misnomer, inaccurate indicator labels"],
            ["UI & Visualizations", "Q15-Q19", "5",
             "Missing median lines, mixed units, wrong chart type, truncated names"],
            ["Edge Cases & UX", "Q8, Q9", "2",
             "No distance threshold, no station coverage caveat"],
            ["System Resiliency", "Q14, Q23-Q25", "4",
             "No retry logic, fatal import bug, missing pipeline integration"],
        ],
    )

    _add_heading(doc, "15.2 Round 2: 27/28 PASS + 10 New Concerns", level=2)
    doc.add_paragraph(
        "All original findings were re-assessed against the remediated code. "
        "27/28 returned PASS; Q25 returned PARTIAL. Additionally, 10 new concerns "
        "(N1-N10) were identified."
    )
    _add_table(doc,
        ["Finding", "Priority", "Verdict", "Action Taken"],
        [
            ["N5: Partial overwrite guard", "P0 (Critical)", "ACTION",
             "Added 80% minimum-row guard"],
            ["N1: 10-month AVERAGE threshold", "P1 (High)", "ACTION",
             "Enforced strict 12 months for both SUM and AVERAGE"],
            ["N3: Growing Season mixed units", "P1 (High)", "ACTION",
             "Split tab into GDD + Threshold Days charts"],
            ["N10: Unweighted CSD median label", "P2 (Medium)", "ACTION",
             "Clarified annotation with indicator name"],
            ["N4: Data vintage staleness", "P2 (Medium)", "ACTION",
             "Added warming caveat to caption"],
            ["N2: Shared station mapping", "P3 (Low)", "ACTION",
             "Added shared-station note to caption"],
            ["N6-N9: Cache TTL, distance, Haversine, vintage file", "P3 (Low)", "ACCEPTED",
             "No code changes needed; acceptable technical debt"],
        ],
    )

    _add_heading(doc, "15.3 Round 3: 3/4 Remediations PASS", level=2)
    doc.add_paragraph(
        "Round 3 confirmed 3 of 4 remediations fully resolved. Remediation 3 (N10 median "
        "label) was marked FAIL because removing the indicator name made multi-indicator "
        "tabs visually ambiguous. A 1-line fix was prescribed."
    )

    _add_heading(doc, "15.4 Round 4: Final Sign-Off — 🟢 GO", level=2)
    doc.add_paragraph(
        "The corrected Remediation 3 was verified. All P0, P1, and P2 findings fully "
        "resolved. No regressions introduced. The Climate Profile module was officially "
        "cleared for production deployment."
    )
    _add_para(doc,
        "Final Verdict: 🟢 APPROVED FOR PRODUCTION — SIGNED OFF (Round 4, February 2026)",
        bold=True,
    )

    _add_heading(doc, "15.5 Expert Future-Proofing Notes", level=2)
    doc.add_paragraph(
        "Items flagged for routine maintenance (no action required before launch):"
    )
    doc.add_paragraph(
        "1. Plan a minor ticket to update the pipeline when ECCC publishes the 1991-2020 "
        "normals. Because the infrastructure is solid, this will be a trivial parameter "
        "update. See §12.2 for detailed steps.",
        style="List Number"
    )
    doc.add_paragraph(
        "2. Consider adding a climate_vintage.json metadata file (N9) for automated "
        "caption management when normals period changes. Low priority — ECCC releases "
        "normals once per decade.",
        style="List Number"
    )

    # ── Save ────────────────────────────────────────────────────────────
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUTPUT))
    print(f"✓ Manual saved to: {OUTPUT}")


if __name__ == "__main__":
    build_manual()
