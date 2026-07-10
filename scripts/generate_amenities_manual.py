"""
Generate Community Amenities Developer Manual (Word .docx)
==========================================================
Produces a comprehensive developer manual covering the Community Amenities
tab's data pipeline, UI sections, and maintenance procedures.

Run:  python scripts/generate_amenities_manual.py
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
    r"\Community Amenities Tab - Developer Manual.docx"
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
    title = doc.add_heading("Community Amenities Tab — Developer Manual", level=0)
    doc.add_paragraph(
        "Rural Ontario Community Data Dashboard\n"
        "Page: 9_🏘️_Rural_Community_Data.py\n"
        "Last updated: February 2026"
    )

    # ── Table of Contents ───────────────────────────────────────────────
    _add_heading(doc, "Table of Contents", level=1)
    toc_items = [
        "1. Overview",
        "2. Architecture",
        "3. Data Sources",
        "4. ETL Pipeline — Health Facilities",
        "5. ETL Pipeline — Arts & Culture Facilities",
        "6. ETL Pipeline — Education Facilities (Stub)",
        "7. ETL Pipeline — Recreation Facilities (Stub)",
        "8. Shared Infrastructure",
        "9. Page Layout & User Interface",
        "10. Benchmark Calculation Methodology",
        "11. INDICATOR_META Configuration",
        "12. Output File Reference",
        "13. Maintenance & Update Guide",
        "14. Troubleshooting",
        "15. Expert Audit History",
    ]
    for item in toc_items:
        doc.add_paragraph(item, style="List Number")

    # ══════════════════════════════════════════════════════════════════════
    # 1. OVERVIEW
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "1. Overview", level=1)
    doc.add_paragraph(
        "The Community Amenities module provides rural Ontario decision-makers with "
        "a facility-level view of local service capacity. It answers the question: "
        '"How does our community\'s access to health, arts, education, and recreation '
        'facilities compare to our peers and to provincial benchmarks?"'
    )
    doc.add_paragraph(
        "The module consists of two main components:"
    )
    doc.add_paragraph(
        "ETL scripts that download and process Statistics Canada's Longitudinal Open Data "
        "for the Economy (LODE) facility databases, producing per-CSD facility counts.",
        style="List Bullet"
    )
    doc.add_paragraph(
        "Standalone UI sections within the Rural Community Data page that visualize "
        "facility counts, per-capita rates, and dual benchmarks (Ontario Average, "
        "Rural Ontario Average).",
        style="List Bullet"
    )
    _add_para(doc,
        "Key design principle: Community amenities data is ATEMPORAL — these are "
        "point-in-time snapshots, not Census time-series. They are quarantined from "
        "the generic time-series tab system and displayed only in purpose-built "
        "standalone sections with appropriate caveats and context.",
        bold=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # 2. ARCHITECTURE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "2. Architecture", level=1)
    doc.add_paragraph(
        "The Community Amenities module uses a three-layer architecture:"
    )

    _add_heading(doc, "2.1 Data Flow Diagram", level=2)
    doc.add_paragraph(
        "StatCan LODE ZIPs (raw)\n"
        "    ↓  ETL scripts (scripts/fetch_*.py)\n"
        "WIDE CSV (data/latest/wellbeing/*_facility_counts.csv)\n"
        "LONG CSV (data/derived/*.csv)\n"
        "Vintage JSON (data/latest/wellbeing/amenities_vintage.json)\n"
        "    ↓  Streamlit Page (app/pages/9_…Rural_Community_Data.py)\n"
        "Interactive charts, tables, and benchmark lines"
    )

    _add_heading(doc, "2.2 File Inventory", level=2)
    _add_table(doc,
        ["File", "Layer", "Purpose"],
        [
            ["scripts/fetch_health_facilities.py", "ETL", "Processes ODHF → health CSV + vintage JSON"],
            ["scripts/fetch_arts_facilities.py", "ETL", "Processes ODCAF → arts CSV + vintage JSON"],
            ["scripts/fetch_education_facilities.py", "ETL", "Processes ODEF → education CSV (stub)"],
            ["scripts/fetch_recreation_facilities.py", "ETL", "Processes ODRSF → recreation CSV (stub)"],
            ["data/raw/ODHF_v1.1.zip", "Raw", "Downloaded ODHF data (manual download)"],
            ["data/raw/ODCAF*.zip", "Raw", "Downloaded ODCAF data (manual download)"],
            ["data/latest/wellbeing/health_facility_counts.csv", "Output", "Wide-format health facility counts"],
            ["data/latest/wellbeing/arts_facility_counts.csv", "Output", "Wide-format arts facility counts"],
            ["data/derived/health_facilities.csv", "Output", "Long-format health indicator"],
            ["data/derived/arts_culture.csv", "Output", "Long-format arts indicator"],
            ["data/latest/wellbeing/amenities_vintage.json", "Metadata", "Dynamic data vintage for UI captions"],
            ["app/pages/9_🏘️_Rural_Community_Data.py", "UI", "Streamlit page (Health Access §9, Arts §8c)"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 3. DATA SOURCES
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "3. Data Sources", level=1)
    doc.add_paragraph(
        "All facility data originates from Statistics Canada's Longitudinal Open "
        "Data for the Economy (LODE) program. These are open-data, point-in-time "
        "snapshots released as downloadable ZIP files."
    )

    _add_table(doc,
        ["Database", "Acronym", "Version", "Release Year", "URL"],
        [
            ["Open Database of Healthcare Facilities", "ODHF", "v1.1", "2021",
             "statcan.gc.ca/en/lode/databases/odhf"],
            ["Open Database of Cultural and Art Facilities", "ODCAF", "v1.0", "2019",
             "statcan.gc.ca/en/lode/databases/odcaf"],
            ["Open Database of Educational Facilities", "ODEF", "—", "—",
             "statcan.gc.ca/en/lode/databases/odef"],
            ["Open Database of Recreational and Sport Facilities", "ODRSF", "—", "—",
             "statcan.gc.ca/en/lode/databases/odrsf"],
        ],
    )

    doc.add_paragraph("")
    _add_para(doc,
        "Important: These ZIPs must be downloaded manually and placed in data/raw/. "
        "There is no automated download — StatCan LODE pages require acknowledgment "
        "of terms of use before download.",
        bold=True,
    )

    _add_heading(doc, "3.1 Supporting Data", level=2)
    _add_table(doc,
        ["File", "Purpose", "Source"],
        [
            ["census_indicators.csv", "Population data for per-capita rates and Ontario total", "Census pipeline"],
            ["dim_geography.csv", "CSD names and county lookup", "Census pipeline"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 4. ETL — HEALTH FACILITIES
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "4. ETL Pipeline — Health Facilities", level=1)
    doc.add_paragraph(
        "Script: scripts/fetch_health_facilities.py\n"
        "Input:  data/raw/ODHF_v1.1.zip\n"
    )

    _add_heading(doc, "4.1 Processing Steps", level=2)
    steps = [
        "Open ZIP and locate the largest CSV file (main data file)",
        "Resolve column names via alias matching (CSD, Province, Facility Type)",
        "Filter to Ontario records (matches 'on', 'ontario', or '35')",
        "Normalize CSD codes: convert to integer, zero-fill to 7 digits, validate ^35\\d{5}$ regex",
        "Map facility types → internal categories: hospitals, ambulatory, nursing_residential",
        "Unmapped types fall back to 'other' category (Rec 3 audit fix)",
        "Pivot: count facilities per CSD × category → wide format",
        "Enrich: merge community names from dim_geography.csv",
        "Compute per-capita rate: (total_facilities / population) × 10,000",
        "Save WIDE CSV → data/latest/wellbeing/health_facility_counts.csv",
        "Save LONG CSV → data/derived/health_facilities.csv",
        "Update amenities_vintage.json with pipeline metadata",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")

    _add_heading(doc, "4.2 Facility Type Mapping", level=2)
    _add_table(doc,
        ["ODHF Facility Type (raw)", "Internal Column Name"],
        [
            ["Hospitals", "hospitals"],
            ["Ambulatory Health Care Services", "ambulatory"],
            ["Nursing and Residential Care Facilities", "nursing_residential"],
            ["(Any unmapped type)", "other"],
        ],
    )
    doc.add_paragraph(
        "The 'other' fallback ensures no facility is silently dropped when StatCan "
        "introduces new categories. A console warning prints the unmapped type names "
        "and counts for operator awareness."
    )

    _add_heading(doc, "4.3 Column Alias Resolution (Rec 5)", level=2)
    doc.add_paragraph(
        "StatCan frequently changes header casing between releases (e.g., CSDuid → "
        "CSDUID → csd_uid). The _find_column() function normalizes all DataFrame "
        "column headers to lowercase and checks against a predefined alias list:"
    )
    _add_table(doc,
        ["Column Purpose", "Accepted Aliases"],
        [
            ["CSD UID", "csduid, csd_uid, csd"],
            ["Province", "province, prov_terr, province / territory"],
            ["Facility Type", "odhf_facility_type, facility_type, source_facility_type"],
        ],
    )
    doc.add_paragraph(
        "If no alias matches, a RuntimeError is raised with the tried aliases "
        "and available columns, enabling fast diagnosis."
    )

    _add_heading(doc, "4.4 Wide-Format Output Schema", level=2)
    _add_table(doc,
        ["Column", "Type", "Description"],
        [
            ["sgc_code", "str(7)", "7-digit Standard Geographical Classification code (Ontario: 35xxxxx)"],
            ["ambulatory", "int", "Count of Ambulatory Health Care Services"],
            ["hospitals", "int", "Count of Hospitals"],
            ["nursing_residential", "int", "Count of Nursing and Residential Care Facilities"],
            ["other", "int", "Count of unmapped facility types (fallback bin)"],
            ["total_facilities", "int", "Sum of all facility type columns"],
            ["community", "str", "CSD name (county) — e.g., 'Guelph (Wellington)'"],
            ["county", "str", "County or regional municipality name"],
            ["geo_name", "str", "CSD name without county"],
            ["population", "float", "Latest Census population for the CSD"],
            ["facilities_per_10k", "float", "total_facilities / population × 10,000"],
        ],
    )

    _add_heading(doc, "4.5 Long-Format Output Schema", level=2)
    _add_table(doc,
        ["Column", "Type", "Description"],
        [
            ["sgc_code", "str(7)", "7-digit SGC code"],
            ["indicator", "str", "Always 'health_facilities'"],
            ["value", "int", "Total facility count for the CSD"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 5. ETL — ARTS FACILITIES
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "5. ETL Pipeline — Arts & Culture Facilities", level=1)
    doc.add_paragraph(
        "Script: scripts/fetch_arts_facilities.py\n"
        "Input:  data/raw/ODCAF*.zip (glob pattern — case-insensitive)\n"
    )

    _add_heading(doc, "5.1 Processing Steps", level=2)
    steps = [
        "Locate ODCAF ZIP via glob pattern (ODCAF*.zip, then odcaf*.zip fallback)",
        "Open ZIP and select the largest non-metadata CSV",
        "Resolve column names via alias matching (CSD, Province, Facility Type)",
        "Filter to Ontario records ('on' or 'ontario')",
        "Normalize CSD codes to 7-digit format, validate Ontario prefix (35xxxxx)",
        "Attempt to find facility type column via aliases; if missing, fall back to simple count",
        "If type column found: pivot by CSD × type, normalize type names (lowercase, underscores)",
        "Enrich with community names and per-capita rates",
        "Save WIDE CSV → data/latest/wellbeing/arts_facility_counts.csv",
        "Save LONG CSV → data/derived/arts_culture.csv (indicator = 'arts_culture_facilities')",
        "Update amenities_vintage.json with pipeline metadata",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")

    _add_heading(doc, "5.2 Type Column Fallback", level=2)
    doc.add_paragraph(
        "Unlike the health script (which has a fixed type map), the arts script "
        "uses whatever type names exist in the source data and normalizes them "
        "as column headers. If no type column is found at all, it falls back to "
        "a simple total count per CSD."
    )

    _add_heading(doc, "5.3 Column Alias Resolution", level=2)
    _add_table(doc,
        ["Column Purpose", "Accepted Aliases"],
        [
            ["CSD UID", "csduid, csd_uid, csd"],
            ["Province", "prov_terr, province, province / territory"],
            ["Facility Type", "odcaf_facility_type, facility_type, source_facility_type"],
        ],
    )

    _add_heading(doc, "5.4 Output Schema", level=2)
    doc.add_paragraph(
        "The wide-format schema is dynamic — columns depend on the facility types "
        "present in the ODCAF data. Common type columns include: art_gallery, "
        "heritage_site, museum, library, performing_arts, etc. Fixed columns match "
        "the health script: sgc_code, total_facilities, community, county, geo_name, "
        "population, facilities_per_10k."
    )

    _add_heading(doc, "5.5 Historical Note", level=2)
    doc.add_paragraph(
        "This script consolidates the functionality of the now-deleted "
        "fetch_arts_culture.py (Rec 4 audit fix). The deprecated script was fully "
        "removed from the repository — version control preserves the history."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 6. ETL — EDUCATION (STUB)
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "6. ETL Pipeline — Education Facilities (Stub)", level=1)
    doc.add_paragraph(
        "Script: scripts/fetch_education_facilities.py\n"
        "Input:  data/raw/ODEF*.zip (not yet downloaded)\n"
        "Status: STUB — created as part of Rec 9 (expand LODE suite)\n"
    )
    doc.add_paragraph(
        "This script follows the exact same pattern as the arts script: "
        "glob for ZIP, alias-based column resolution, Ontario filter, CSD "
        "normalization, type pivot, enrichment, dual output (WIDE + LONG). "
        "It will produce education_facility_counts.csv and education_facilities.csv "
        "once the ODEF ZIP is downloaded and placed in data/raw/."
    )
    _add_para(doc,
        "No UI section exists yet — when activated, a standalone §Education section "
        "should be added to the page following the Health/Arts pattern.",
        italic=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # 7. ETL — RECREATION (STUB)
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "7. ETL Pipeline — Recreation Facilities (Stub)", level=1)
    doc.add_paragraph(
        "Script: scripts/fetch_recreation_facilities.py\n"
        "Input:  data/raw/ODRSF*.zip (not yet downloaded)\n"
        "Status: STUB — created as part of Rec 9 (expand LODE suite)\n"
    )
    doc.add_paragraph(
        "Identical architecture to the education stub. Will produce "
        "recreation_facility_counts.csv and recreation_facilities.csv."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 8. SHARED INFRASTRUCTURE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "8. Shared Infrastructure", level=1)

    _add_heading(doc, "8.1 amenities_vintage.json", level=2)
    doc.add_paragraph(
        "Both health and arts ETL scripts write to a shared JSON file that stores "
        "metadata about the most recent pipeline run. The Streamlit page reads this "
        "file at runtime to display dynamic data vintage captions."
    )
    doc.add_paragraph("Schema:")
    _add_code(doc,
        '{\n'
        '  "health": {\n'
        '    "source": "Open Database of Healthcare Facilities (ODHF)",\n'
        '    "version": "v1.1",\n'
        '    "source_release_year": 2021,\n'
        '    "pipeline_run": "2026-02-24 13:55",\n'
        '    "zip_file": "ODHF_v1.1.zip"\n'
        '  },\n'
        '  "arts": { ... same structure ... }\n'
        '}'
    )
    doc.add_paragraph(
        "Each ETL script reads the existing file first (if it exists) and updates "
        "only its own section, preserving the other section's data. This allows "
        "scripts to be run independently."
    )

    _add_heading(doc, "8.2 _find_column() Helper", level=2)
    doc.add_paragraph(
        "All ETL scripts share a common column-resolution pattern. The function "
        "normalizes DataFrame column headers to lowercase, strips whitespace, and "
        "checks against a predefined alias list. This tolerates StatCan's erratic "
        "casing changes (CSDuid → CSDUID → csd_uid) while failing fast on genuine "
        "schema breaks."
    )
    doc.add_paragraph("Signature:")
    _add_code(doc,
        "def _find_column(df: pd.DataFrame, aliases: list[str], desc: str) -> str:\n"
        "    # Raises RuntimeError if no alias matches\n"
    )

    _add_heading(doc, "8.3 CSD Code Normalization", level=2)
    doc.add_paragraph(
        "All scripts apply the same CSD normalization pipeline:\n"
        "1. Convert to numeric (handles float-encoded UIDs like 3523043.0)\n"
        "2. Drop NaN values\n"
        "3. Cast to integer, then to string, zero-fill to 7 digits\n"
        "4. Validate against regex ^35\\d{5}$ (Ontario only)"
    )

    # ══════════════════════════════════════════════════════════════════════
    # 9. PAGE LAYOUT & USER INTERFACE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "9. Page Layout & User Interface", level=1)
    doc.add_paragraph(
        "Community amenities data is displayed in two standalone sections within "
        "the Rural Community Data page. These sections are NOT part of the generic "
        "tab system — they are purpose-built with facility-specific controls."
    )

    _add_heading(doc, "9.1 Health Access Section (§9)", level=2)
    doc.add_paragraph(
        "Location: Rendered after the generic indicator tabs, gated by "
        "HEALTH_FILE.exists()\n"
        "Data source: health_facility_counts.csv (wide format)"
    )
    doc.add_paragraph("Features:")
    features = [
        "Metric toggle: 'Raw Counts' vs 'Per 10K Population' (radio button)",
        "Grouped bar chart: communities × facility types (hospitals, ambulatory, nursing_residential)",
        "Small-population flag: CSD pop < 1,000 gets asterisk (*) in label",
        "Ontario Average reference line (dashed grey) — uses FULL Ontario population as denominator",
        "Rural Ontario Average reference line (dotted green) — CSDs with pop < 100,000",
        "Data table with all facilities by type, community, and per-capita rates",
        "Dynamic vintage caption from amenities_vintage.json",
        "Regional context tooltip explaining zero-count semantics",
        "Statistics footnote for asterisk-flagged communities",
    ]
    for f in features:
        doc.add_paragraph(f, style="List Bullet")

    _add_heading(doc, "9.2 Arts & Culture Section (§8c)", level=2)
    doc.add_paragraph(
        "Location: Rendered after the Health Access section, gated by "
        "ARTS_FILE.exists()\n"
        "Data source: arts_facility_counts.csv (wide format)"
    )
    doc.add_paragraph("Features:")
    features = [
        "Metric toggle: 'Raw Counts' vs 'Per 10K Population' (radio button)",
        "STACKED bar chart (barmode='stack'): communities × facility types — total height = aggregate",
        "Dynamic hovertemplate: appends 'per 10k pop' suffix when per-capita toggle is active",
        "Small-population flag: CSD pop < 1,000 gets asterisk (*) in label",
        "Ontario Average reference line (dashed grey)",
        "Rural Ontario Average reference line (dotted green)",
        "Data table with all facilities by type, community, and per-capita rates",
        "Dynamic vintage caption from amenities_vintage.json",
        "Regional context tooltip and statistical footnote",
    ]
    for f in features:
        doc.add_paragraph(f, style="List Bullet")

    _add_heading(doc, "9.3 Key UI Decision: Stacked vs Grouped Bars", level=2)
    doc.add_paragraph(
        "The Arts chart uses barmode='stack' while Health uses barmode='group'. "
        "This is intentional: the arts section can have 8+ facility types, which "
        "makes grouped bars illegible (the 'barcode' problem). Stacking preserves "
        "the ability to compare total capacity (bar height) while showing composition. "
        "Health typically has only 3 types, where grouping remains readable."
    )

    _add_heading(doc, "9.4 Streamlit Helper Functions", level=2)
    _add_table(doc,
        ["Function", "Decorator", "Purpose"],
        [
            ["_get_amenity_vintage(section)", "@st.cache_data(ttl=600)",
             "Reads amenities_vintage.json for dynamic captions; falls back to hardcoded defaults"],
            ["_get_ontario_population()", "@st.cache_data(ttl=600)",
             "Sums all CSD populations from census_indicators.csv for full Ontario total (14.2M)"],
            ["_get_rural_totals(facility_df)", "None (trivial)",
             "Filters facility DF to pop < 100K, returns (rural_pop, rural_facility_count)"],
            ["_is_standalone_indicator(meta_tuple)", "None",
             "Checks if INDICATOR_META entry has supported_views: ['standalone']"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 10. BENCHMARK CALCULATION
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "10. Benchmark Calculation Methodology", level=1)

    _add_heading(doc, "10.1 Ontario Average", level=2)
    doc.add_paragraph(
        "Formula: Ontario Average = Σ(all facilities in dataset) / Σ(all Ontario CSD populations) × 10,000"
    )
    doc.add_paragraph(
        "Critical: The denominator uses the FULL Ontario population (~14.2M from 577 CSDs "
        "in census_indicators.csv), NOT the filtered subset of CSDs that have facilities "
        "(~13.7M from ~312–336 CSDs). Using the filtered subset artificially inflates the "
        "benchmark — this was identified as a 'data trap' in the Rec 7 expert audit."
    )

    _add_heading(doc, "10.2 Rural Ontario Average", level=2)
    doc.add_paragraph(
        "Formula: Rural Average = Σ(facilities in CSDs < 100K pop) / Σ(population of CSDs < 100K pop) × 10,000"
    )
    doc.add_paragraph(
        "This provides a peer-appropriate benchmark for rural municipalities. The "
        "100K threshold separates urban centres (Toronto, Ottawa, Hamilton) from the "
        "rural/small-town landscape that represents the dashboard's target audience."
    )

    _add_heading(doc, "10.3 Visual Presentation", level=2)
    _add_table(doc,
        ["Benchmark", "Line Style", "Color", "Position"],
        [
            ["Ontario Average", "Dashed", "#9e9e9e (grey)", "Top right annotation"],
            ["Rural Ontario Average", "Dotted", "#66bb6a (green)", "Bottom right annotation"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 11. INDICATOR_META CONFIGURATION
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "11. INDICATOR_META Configuration", level=1)
    doc.add_paragraph(
        "Community amenities indicators are registered in the INDICATOR_META dictionary "
        "with a special 4th tuple element that quarantines them from the generic tab system."
    )
    doc.add_paragraph("Entry format:")
    _add_code(doc,
        '"arts_culture_facilities": ("Cultural Facilities", "", "Community Amenities", '
        '{"supported_views": ["standalone"]}),\n'
        '"health_facilities":      ("Health Facilities",    "", "Community Amenities", '
        '{"supported_views": ["standalone"]}),'
    )
    doc.add_paragraph("How quarantine works:")
    quarantine_steps = [
        'Standard indicators use a 3-tuple: (display_name, unit, category)',
        'Amenity indicators add a 4th element: {"supported_views": ["standalone"]}',
        '_is_standalone_indicator(meta) checks for this flag',
        'The generic tab system filters out standalone indicators via: '
        'if meta[2] == category and not _is_standalone_indicator(meta)',
        '"Community Amenities" is removed from the CATEGORIES list entirely',
        'The standalone Health and Arts sections render these indicators directly',
    ]
    for s in quarantine_steps:
        doc.add_paragraph(s, style="List Number")

    _add_para(doc,
        "Important: All other code accesses INDICATOR_META values by positional index "
        "(meta[0], meta[1], meta[2]). The 4th element is safely ignored by all existing "
        "code paths. No destructuring unpacking is used anywhere in the codebase.",
        bold=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # 12. OUTPUT FILE REFERENCE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "12. Output File Reference", level=1)

    _add_table(doc,
        ["File", "Format", "Generated By", "Read By"],
        [
            ["health_facility_counts.csv", "Wide CSV", "fetch_health_facilities.py",
             "Page §9 Health Access"],
            ["arts_facility_counts.csv", "Wide CSV", "fetch_arts_facilities.py",
             "Page §8c Arts & Culture"],
            ["health_facilities.csv", "Long CSV", "fetch_health_facilities.py",
             "Generic indicator system (quarantined)"],
            ["arts_culture.csv", "Long CSV", "fetch_arts_facilities.py",
             "Generic indicator system (quarantined)"],
            ["amenities_vintage.json", "JSON", "Both health & arts ETL scripts",
             "Page UI captions (dynamic vintage)"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 13. MAINTENANCE & UPDATE GUIDE
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "13. Maintenance & Update Guide", level=1)

    _add_heading(doc, "13.1 Updating When StatCan Releases New Data", level=2)
    steps = [
        "Navigate to the StatCan LODE page (URLs in Data Sources section above)",
        "Download the new ZIP file (e.g., ODHF_v2.0.zip)",
        "Place in data/raw/ (do NOT rename — the scripts use glob or exact match)",
        "For ODHF: Update the ODHF_ZIP constant in fetch_health_facilities.py to match the new filename",
        "For ODCAF: No change needed — the script uses glob pattern matching (ODCAF*.zip)",
        "Run the ETL script: python scripts/fetch_health_facilities.py (or fetch_arts_facilities.py)",
        "Verify console output: check CSD count, facility count, and any 'other' bin warnings",
        "The amenities_vintage.json will auto-update with the new pipeline_run timestamp",
        "Update the 'version' and 'source_release_year' constants in the _write_vintage() function",
        "Restart the Streamlit app to pick up new data (cache TTL is 10 minutes)",
    ]
    for i, s in enumerate(steps, 1):
        doc.add_paragraph(f"{i}. {s}")

    _add_heading(doc, "13.2 Adding a New LODE Database", level=2)
    steps = [
        "Copy fetch_arts_facilities.py as a template (it's the most flexible pattern)",
        "Update path constants (WIDE_FILE, LONG_FILE, glob pattern)",
        "Update alias lists (CSD_ALIASES, PROV_ALIASES, TYPE_ALIASES) per new schema",
        "Add _write_vintage() call with appropriate section key",
        "Add a new standalone section to the page following the Health/Arts pattern",
        "Register the new indicator in INDICATOR_META with supported_views: ['standalone']",
        "Test with a sample download to verify column resolution and output shape",
    ]
    for i, s in enumerate(steps, 1):
        doc.add_paragraph(f"{i}. {s}")

    _add_heading(doc, "13.3 Handling StatCan Schema Changes", level=2)
    doc.add_paragraph(
        "The alias-based column resolution (_find_column) is designed to absorb "
        "minor header changes. If a genuinely new column name appears:"
    )
    doc.add_paragraph(
        "1. The script will raise a RuntimeError with the available columns\n"
        "2. Add the new column name to the appropriate alias list\n"
        "3. Re-run the script"
    )
    doc.add_paragraph(
        "For ODHF: If StatCan adds a new facility type (e.g., 'Virtual Care Hubs'), "
        "it will automatically map to the 'other' bin and appear in the console warning. "
        "To give it a dedicated column, add a new entry to FACILITY_TYPE_MAP."
    )

    _add_heading(doc, "13.4 Performance Notes", level=2)
    doc.add_paragraph(
        "The helper functions _get_ontario_population() and _get_amenity_vintage() are "
        "decorated with @st.cache_data(ttl=600). This caches results in memory for 10 "
        "minutes, preventing repeated disk I/O on every Streamlit render cycle. If you "
        "update the underlying data files, the cache will auto-refresh within 10 minutes "
        "or you can force-refresh by clearing the Streamlit cache via the UI menu."
    )

    # ══════════════════════════════════════════════════════════════════════
    # 14. TROUBLESHOOTING
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "14. Troubleshooting", level=1)

    _add_table(doc,
        ["Symptom", "Likely Cause", "Fix"],
        [
            ["RuntimeError: Cannot find CSD UID column",
             "StatCan changed header name",
             "Add new name to CSD_ALIASES in the affected script"],
            ["'N other' facilities mapped to 'other'",
             "New ODHF facility type introduced",
             "Add to FACILITY_TYPE_MAP if a dedicated column is desired"],
            ["No vintage caption in UI",
             "amenities_vintage.json not generated",
             "Run ETL script; fallback defaults will show until then"],
            ["Benchmark line missing",
             "census_indicators.csv missing or empty",
             "Run Census pipeline first; _get_ontario_population() returns 0 gracefully"],
            ["'Community Amenities' tab appears (empty)",
             "CATEGORIES list still includes it",
             "Remove 'Community Amenities' from CATEGORIES list"],
            ["Per-capita rates show NaN/inf",
             "CSD has zero population in Census data",
             "Handled: inf is replaced with None in ETL scripts"],
            ["ZIP file not found error",
             "Manual download not completed",
             "Download from StatCan LODE page and place in data/raw/"],
        ],
    )

    # ══════════════════════════════════════════════════════════════════════
    # 15. EXPERT AUDIT HISTORY
    # ══════════════════════════════════════════════════════════════════════
    _add_heading(doc, "15. Expert Audit History", level=1)
    doc.add_paragraph(
        "The Community Amenities module underwent two expert reviews in February 2026."
    )

    _add_heading(doc, "15.1 Round 1: Initial Recommendations (10 items)", level=2)
    _add_table(doc,
        ["Rec", "Title", "Status"],
        [
            ["1", "Quarantine Atemporal Data", "Implemented"],
            ["2", "Surface Data Vintage", "Implemented"],
            ["3", "Resolve Phantom Health Script", "Implemented"],
            ["4", "Consolidate Arts Scripts", "Implemented"],
            ["5", "Alias-based Column Resolution", "Implemented"],
            ["6", "Rural Per-Capita Floor", "Implemented"],
            ["7", "Change Benchmark Baseline", "Implemented"],
            ["8", "Expose Arts Sub-categories", "Implemented"],
            ["9", "Integrate ODEF & ODRSF stubs", "Implemented"],
            ["10", "Add Regional Context Tooltip", "Implemented"],
        ],
    )

    _add_heading(doc, "15.2 Round 2: Audit Remediation (8 items)", level=2)
    _add_table(doc,
        ["Rec", "Verdict", "Fix Applied"],
        [
            ["1", "PARTIAL → PASS", "Metadata flag instead of commented-out keys"],
            ["2", "PARTIAL → PASS", "Dynamic vintage from amenities_vintage.json"],
            ["3", "PASS", "'Other' fallback bin for unmapped types"],
            ["4", "PARTIAL → PASS", "fetch_arts_culture.py fully deleted"],
            ["5", "PARTIAL → PASS", "_find_column() alias matching backported"],
            ["6", "FAIL → PASS", "⚠️ emoji replaced with asterisk (*)"],
            ["7", "PASS → PASS", "Full Ontario pop denominator + Rural Avg line"],
            ["8", "FAIL → PASS", "barmode='group' → 'stack' for legibility"],
        ],
    )

    _add_heading(doc, "15.3 Round 3: Final Sign-Off", level=2)
    doc.add_paragraph(
        "All 8 fixes received PASS verdict. Three pre-flight conditions were met:"
    )
    doc.add_paragraph("Tuple unpacking audit — all access is positional, 4-tuple is safe", style="List Bullet")
    doc.add_paragraph("@st.cache_data memoization added to I/O-heavy helpers", style="List Bullet")
    doc.add_paragraph("Plotly hovertemplate dynamically appends 'per 10k pop' suffix", style="List Bullet")
    _add_para(doc,
        "Result: CONDITIONAL SIGN-OFF upgraded to SIGNED OFF",
        bold=True,
    )

    # ── Save ────────────────────────────────────────────────────────────
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUTPUT))
    print(f"✓ Manual saved to: {OUTPUT}")


if __name__ == "__main__":
    build_manual()
