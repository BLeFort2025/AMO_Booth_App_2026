"""
ONFVRVS PDF Data Extraction Script
===================================
Extracts Ontario Farmland Value & Rental Value Survey data (2016-2025) from PDF
reports into structured CSV datasets.

Source PDFs:
  - ONFVRVS_AnnualReports_2016to2024 (1).pdf  (64 pages, 9 years)
  - ONFVRVS_AnnualReport_2025.pdf              (7 pages, 1 year)

Output CSVs (written to data/surveys/):
  1. onfvrvs_rental_rates_and_values.csv   — per-region median rent & land price
  2. onfvrvs_respondent_characteristics.csv — survey-level summary stats
  3. onfvrvs_buyer_perceptions.csv         — % of sales to farmers by region
  4. onfvrvs_survey_metadata.csv           — respondent counts per year

Usage:
    python scripts/extract_onfvrvs_data.py
"""

import csv
import os
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber is required. Install with: pip install pdfplumber")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HISTORICAL_PDF = Path(r"C:\Users\ben.lefort\Downloads\ONFVRVS_AnnualReports_2016to2024 (1).pdf")
CURRENT_PDF = Path(r"C:\Users\ben.lefort\Downloads\ONFVRVS_AnnualReport_2025.pdf")

# Output directory
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "surveys"

# Year-to-page mapping for the historical PDF (0-indexed page numbers)
# Each year has: title page, respondent chars, rental table (2 pages), 
# owned-vs-rented chart, buyer perceptions (1–2 pages)
YEAR_PAGES = {
    2024: {"start": 2,  "rental": [4, 5],   "respondent": [3],     "buyer": [7, 8]},
    2023: {"start": 9,  "rental": [11, 12],  "respondent": [10],    "buyer": [14, 15]},
    2022: {"start": 16, "rental": [18, 19],  "respondent": [17],    "buyer": [21, 22]},
    2021: {"start": 23, "rental": [25, 26],  "respondent": [24],    "buyer": [28, 29]},
    2020: {"start": 30, "rental": [32, 33],  "respondent": [31],    "buyer": [35, 36]},
    2019: {"start": 37, "rental": [39, 40],  "respondent": [38],    "buyer": [42, 43]},
    2018: {"start": 44, "rental": [46, 47],  "respondent": [45],    "buyer": [49, 50]},
    2017: {"start": 51, "rental": [53, 54],  "respondent": [52],    "buyer": [56, 57]},
    2016: {"start": 58, "rental": [59, 60],  "respondent": [63],    "buyer": [61, 62]},
}

YEAR_2025_PAGES = {
    "rental": [2, 3],      # 0-indexed
    "respondent": [1],
    "buyer": [5, 6],
    "start": 0,
}


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Rental rates / land values (2018-2025 format with $ signs)
# Matches: "Region Name (Type) $350 (n=31) $37,500 (n=27) 1.0%"
# Also handles: "$75,000+ (n=10)" and missing values "-"
# Case-insensitive for (n=X) vs (N=X)
RE_RENTAL_DOLLAR = re.compile(
    r'^(.+?)\s+'                                       # Region name (lazy)
    r'\$([\d,]+(?:\.\d+)?\+?)\s*\([nN]\s*=\s*(\d+)\)\s+'  # rent value + (n=X)
    r'(?:\$([\d,]+(?:\.\d+)?\+?)\s*\([nN]\s*=\s*(\d+)\)|(-\s*))\s+'  # price + (n=X) OR dash
    r'([\d.]+)\s*%?'                                   # rent/price ratio
, re.I)

# Rental rates 2016-2017 format (no $ signs)
# Matches: "Brant (Census Division) 200 (n=19) 14000 (n= 17) 0.014"
# Also matches: "Brant (Census Division) 200 (N=29) 12000 (N=31) 1.7%"
# IMPORTANT: Handles footnote superscripts stuck to values, e.g.:
#   "651(n=33)" = value 65, footnote 1
#   "1503 (n=26)" = value 150, footnote 3
RE_RENTAL_NO_DOLLAR = re.compile(
    r'^(.+?)\s+'                                       # Region name
    r'(\d[\d,]*(?:\.\d+)?\+?)\s*\([nN]\s*=\s*(\d+)\)\s+'  # rent value + (n=X)
    r'(?:(\d[\d,]*(?:\.\d+)?\+?)\s*\([nN]\s*=\s*(\d+)\)|(-\s*))\s+'  # price or dash
    r'([\d.]+)\s*%?'                                   # ratio (decimal or pct)
, re.I)

# Buyer perception (single-column): "Region Name 90% (n=19)" or "Region Name 90% (N=19)"
# Some years have the percentage on a new line, so we also handle multiline
RE_BUYER_SINGLE = re.compile(
    r'^(.+?)\s+(\d+(?:\.\d+)?)\s*%\s*\([nN]\s*=\s*(\d+)\)\s*$'
)

# Buyer perception 2016 (3-column): "Region (n=13) 50% 10% 25%"
RE_BUYER_2016 = re.compile(
    r'^(.+?)\s+\([nN]\s*=\s*(\d+)\)\s+'
    r'(\d+(?:\.\d+)?)\s*%\s+'
    r'(\d+(?:\.\d+)?)\s*%\s+'
    r'(\d+(?:\.\d+)?)\s*%'
)

# Respondent characteristics row
# Matches: "Age 911 61.42 64 14.19 23 91"
# Also: "Age 2183 58.75 60 12.42 21 101"
RE_RESPONDENT = re.compile(
    r'^(Age|Sex|Acres Owned|Acres Rented|Ratio of Acres|Number of Landlords|'
    r'Landlords Require Stipulations|Rental Agreement|Total Acres Operated|'
    r'Percentage of Total Acres)\s+'
    r'([\d,]+)\s+'          # n / Obs
    r'([\d,.]+)\s+'         # mean
    r'([\d,.]+)\s+'         # median
    r'([\d,.]+)\s+'         # std dev
    r'([\d,.]+)\s+'         # min
    r'([\d,.]+)'            # max
)

# Survey metadata: "from X,XXX Ontario respondents"
RE_RESPONDENT_COUNT = re.compile(r'from\s+([\d,]+)\s+Ontario\s+respondents', re.I)
RE_POTENTIAL_COUNT = re.compile(r'total\s+of\s+([\d,]+)\s+.*?potential\s+respondents', re.I)


# ---------------------------------------------------------------------------
# Parsing functions
# ---------------------------------------------------------------------------

def clean_number(s, parse_top_code=False):
    """Remove $, commas, whitespace from a number string and return float or None."""
    if s is None or s.strip() in ('-', ''):
        return (None, False) if parse_top_code else None
    
    is_top_coded = '+' in s
    s = s.replace('$', '').replace(',', '').replace('+', '').strip()
    try:
        val = float(s)
        return (val, is_top_coded) if parse_top_code else val
    except ValueError:
        return (None, False) if parse_top_code else None


def clean_region_name(name):
    """Clean region name: strip footnote superscripts and extra whitespace."""
    # Remove trailing superscript digits that appear after closing parenthesis
    # e.g., "Niagara (Regional Municipality)2" -> "Niagara (Regional Municipality)"
    name = re.sub(r'\)\s*\d+\s*$', ')', name.strip())
    # Also handle: "651(n=33)" where the 1 is a footnote stuck to the number
    # Clean leading/trailing whitespace
    name = name.strip()
    # Remove any leading bullet/numbering
    name = re.sub(r'^\d+\s+', '', name)
    return name


def extract_rental_data(pages_text, year):
    """Extract rental rate and land value data from page text."""
    rows = []
    
    # Choose regex based on year:
    # 2016-2017: no $ signs (use RE_RENTAL_NO_DOLLAR)
    # 2018-2025: $ signs (use RE_RENTAL_DOLLAR)
    use_no_dollar = year in (2016, 2017)
    pattern = RE_RENTAL_NO_DOLLAR if use_no_dollar else RE_RENTAL_DOLLAR
    
    for line in pages_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        line_lower = line.lower()
        
        # Skip lines that are just page numbers
        if re.match(r'^\d{1,2}\s*$', line):
            continue
            
        # Skip the year header lines
        if re.match(r'^\d{4}\s+Farmland', line):
            continue
        
        # Skip header "Region" column label (but NOT lines containing
        # "Regional Municipality" which are actual data rows)
        if line_lower.startswith('region') and '(' not in line:
            continue
        
        # Skip header lines and non-data lines
        if any(skip in line_lower for skip in [
            'survey question', 'table ', 'median reported',
            'approximately', 'average', 'tillable', 'cropland',
            'quality', 'rent/price', 'note:', 'the following',
            'we only report', 'footnot', 'ratio (',
            'in 20', 'was the typical', 'for [average', 'per tillable',
            'acre, in the', 'that you selected', 'what was', 'this region',
            'selected?', '(continued)', 'farmland rental', 'farmland values',
            'the mean', 'the result', 'previous three', 'median price',
            'view this result', 'calculated with', 'survey format',
            'a in the', 'these ratios', 'both the mean', 'mean rental',
            'mean reported', 'mean price', 'however', 'unchanged',
            'higher mean', 'bit.ly', 'http'
        ]):
            continue
        
        m = pattern.search(line)
        if m:
            groups = m.groups()
            region = clean_region_name(groups[0])
            
            # Skip if region looks like a header artifact
            if len(region) < 3 or region.lower().startswith('region'):
                continue
            
            rent_raw = groups[1]
            rent_n = int(groups[2]) if groups[2] else None
            
            # Price might be captured in group 3/4 or be a dash (group 5)
            price_raw = groups[3]
            price_n = int(groups[4]) if groups[3] and groups[4] else None
            
            ratio_raw = groups[6]
            ratio, _ = clean_number(ratio_raw, parse_top_code=True)
            
            # Normalize 2016 decimal ratios to percentage
            if year == 2016 and ratio is not None and ratio < 1:
                ratio = round(ratio * 100, 2)
                
            rent_tup = clean_number(rent_raw, parse_top_code=True)
            price_tup = clean_number(price_raw, parse_top_code=True) if price_raw else (None, False)
            
            rent_val, rent_is_top_coded = rent_tup
            price_val, price_is_top_coded = price_tup
            
            is_top_coded = rent_is_top_coded or price_is_top_coded
            
            # Mathematical Cross-Validation for Footnote OCR Artifacts
            # For 2016-2017 no-dollar format, handle footnote superscripts
            if use_no_dollar and rent_val and price_val and ratio:
                expected_ratio = (rent_val / price_val) * 100
                diff = abs(expected_ratio - ratio)
                
                if diff > 0.4:
                    # Footnote detected! Let's test combinations of stripping the last digit.
                    r_test_val = clean_number(rent_raw[:-1], parse_top_code=True)[0] if len(rent_raw) > 1 else None
                    p_test_val = clean_number(price_raw[:-1], parse_top_code=True)[0] if price_raw and len(price_raw) > 1 else None
                    
                    best_match = (rent_val, price_val)
                    smallest_err = diff
                    
                    # 1. Strip rent only
                    if r_test_val:
                        err = abs(((r_test_val / price_val) * 100) - ratio)
                        if err < smallest_err:
                            smallest_err = err; best_match = (r_test_val, price_val)
                    # 2. Strip price only
                    if p_test_val:
                        err = abs(((rent_val / p_test_val) * 100) - ratio)
                        if err < smallest_err:
                            smallest_err = err; best_match = (rent_val, p_test_val)
                    # 3. Strip both
                    if r_test_val and p_test_val:
                        err = abs(((r_test_val / p_test_val) * 100) - ratio)
                        if err < smallest_err:
                            smallest_err = err; best_match = (r_test_val, p_test_val)
                            
                    rent_val, price_val = best_match

            rows.append({
                'year': year,
                'region': region,
                'median_cash_rent_per_acre': rent_val,
                'rent_n': rent_n,
                'median_land_price_per_acre': price_val,
                'price_n': price_n,
                'rent_price_ratio_pct': ratio,
                'is_top_coded': is_top_coded,
            })
    
    return rows


def extract_respondent_chars(pages_text, year):
    """Extract respondent characteristics summary statistics."""
    rows = []
    lines = pages_text.split('\n')
    
    # For multi-line variables like "Acres Rented, Leased, Cropshared or Custom Farmed in"
    # we need to join continuation lines
    joined_text = ' '.join(lines)
    
    # Known variable names to search for
    variable_patterns = [
        ('Age', r'Age\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ('Sex', r'Sex\s+\([^)]+\)\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ('Acres Owned', r'Acres\s+Owned\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ('Acres Rented In', r'(?:Acres\s+Rented(?:,\s*Leased,\s*Cropshared\s*or\s*Custom\s*Farmed\s*in|.*?In))\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ('Rent/Own Ratio', r'Ratio\s+of\s+Acres\s+Rented.*?\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ('Number of Landlords', r'Number\s+of\s+Landlords.*?\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ('Stipulations', r'(?:Landlords\s+Require\s+Stipulations|Rental\s+Agreement\s+Includes\s+Stipulations)\s*\([^)]+\)\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
    ]
    
    # 2016 has different variable names
    if year == 2016:
        variable_patterns = [
            ('Age', r'Age\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
            ('Sex', r'Sex\s+\([^)]+\)\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
            ('Total Acres Operated', r'Total\s+Acres\s+Operated\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
            ('Acres Rented In', r'Acres\s+Rented\s+In\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
            ('Pct Acres Rented In', r'Percentage\s+of\s+Total\s+Acres\s+Rented\s+In.*?\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
            ('Number of Landlords', r'Number\s+of\s+Landlords\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
            ('Stipulations', r'Rental\s+Agreement\s+Includes\s+Stipulations\s*\([^)]+\)\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'),
        ]
    
    for var_name, pattern in variable_patterns:
        m = re.search(pattern, joined_text, re.I | re.DOTALL)
        if m:
            vals = [clean_number(g) for g in m.groups()]
            rows.append({
                'year': year,
                'variable': var_name,
                'n': int(vals[0]) if vals[0] else None,
                'mean': vals[1],
                'median': vals[2],
                'std_dev': vals[3],
                'min': vals[4],
                'max': vals[5],
            })
    
    return rows


def extract_buyer_perceptions(pages_text, year):
    """Extract buyer perception data (% farmland sales to farmers)."""
    rows = []
    lines = pages_text.split('\n')
    
    # Handle potential line-break between region and percentage
    # Some years put the percentage on a new line after the region name
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        line_lower = line.lower()
        
        # Skip "Region" header (but NOT lines with "Regional Municipality")
        if line_lower.startswith('region') and '(' not in line and '%' not in line:
            i += 1
            continue
        
        # Skip "R egion" (OCR artifact header)
        if line_lower.startswith('r egion'):
            i += 1
            continue
        
        # Skip headers, footers, and non-data lines
        if any(skip in line_lower for skip in [
            'table ', 'perceived percentage', 'during the past',
            'approximately', 'percentage of farmland', 'made by farmers',
            'median reported', 'note:', 'the mean', 'respondent perception',
            'were made by', 'farmland value', 'survey ', 'we only',
            'responses to this', 'number of responses', 'were asked',
            'as with the', 'given in the table', 'the median reported',
            'however,', 'considerable', 'spatial variation', 'question.',
            'past 12 months', 'overall sample', 'respondents answered',
            'for the overall', 'covid', 'march 20', 'april 20', 'may 20',
            'this question', 'purchases in', 'were to:',
        ]):
            i += 1
            continue
        
        # Skip dotted separators
        if line.startswith('....') or line.startswith('___'):
            i += 1
            continue
        
        # Skip page numbers
        if re.match(r'^\d{1,2}\s*$', line):
            i += 1
            continue
        
        # Skip year headers
        if re.match(r'^\d{4}\s+Farmland', line):
            i += 1
            continue
            
        # Skip dotted separators
        if line.startswith('....') or line.startswith('___'):
            i += 1
            continue
        
        # Try matching on current line
        m = RE_BUYER_SINGLE.match(line)
        if m:
            region = clean_region_name(m.group(1))
            if len(region) >= 3 and not region.lower().startswith('r egion'):
                pct = clean_number(m.group(2))
                n = int(m.group(3))
                rows.append({
                    'year': year,
                    'region': region,
                    'pct_sales_to_farmers': pct,
                    'n': n,
                })
            i += 1
            continue
        
        # Check if this line is a region name and the next line has the percentage
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            combined = line + ' ' + next_line
            m = RE_BUYER_SINGLE.match(combined)
            if m:
                region = clean_region_name(m.group(1))
                if len(region) >= 3 and not region.lower().startswith('r egion'):
                    pct = clean_number(m.group(2))
                    n = int(m.group(3))
                    rows.append({
                        'year': year,
                        'region': region,
                        'pct_sales_to_farmers': pct,
                        'n': n,
                    })
                i += 2
                continue
        
        i += 1
    
    return rows


def extract_buyer_2016_3col(pages_text):
    """Extract the 2016 3-category buyer perception data."""
    rows = []
    
    for line in pages_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        m = RE_BUYER_2016.match(line)
        if m:
            region = clean_region_name(m.group(1))
            if len(region) >= 3 and not region.lower().startswith('region'):
                rows.append({
                    'year': 2016,
                    'region': region,
                    'n': int(m.group(2)),
                    'pct_farmers': clean_number(m.group(3)),
                    'pct_lifestyle_buyers': clean_number(m.group(4)),
                    'pct_investors': clean_number(m.group(5)),
                })
    
    return rows


def extract_survey_metadata(page_text, year):
    """Extract survey-level metadata from the title/description page."""
    respondents = None
    potential = None
    
    m_resp = RE_RESPONDENT_COUNT.search(page_text)
    if m_resp:
        respondents = int(m_resp.group(1).replace(',', ''))
    
    m_pot = RE_POTENTIAL_COUNT.search(page_text)
    if m_pot:
        potential = int(m_pot.group(1).replace(',', ''))
    
    response_rate = None
    if respondents and potential:
        response_rate = round(respondents / potential * 100, 2)
    
    return {
        'year': year,
        'total_respondents': respondents,
        'total_potential_respondents': potential,
        'response_rate_pct': response_rate,
    }


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

def get_pages_text(pdf, page_indices):
    """Concatenate text from multiple PDF pages."""
    texts = []
    for idx in page_indices:
        if idx < len(pdf.pages):
            text = pdf.pages[idx].extract_text()
            if text:
                texts.append(text)
    return '\n'.join(texts)


def write_csv(filepath, rows, fieldnames):
    """Write rows to CSV file."""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✓ Wrote {len(rows)} rows to {filepath.name}")


def main():
    print("=" * 70)
    print("ONFVRVS PDF Data Extraction")
    print("Ontario Farmland Value & Rental Value Survey (2016-2025)")
    print("=" * 70)
    
    # Validate input files
    for pdf_path in [HISTORICAL_PDF, CURRENT_PDF]:
        if not pdf_path.exists():
            print(f"ERROR: PDF not found: {pdf_path}")
            sys.exit(1)
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Accumulators
    all_rental = []
    all_respondent = []
    all_buyer = []
    all_metadata = []
    buyer_2016_3col = []
    
    # -----------------------------------------------------------------------
    # Process historical PDF (2016-2024)
    # -----------------------------------------------------------------------
    print(f"\n📄 Opening historical PDF: {HISTORICAL_PDF.name}")
    pdf_hist = pdfplumber.open(str(HISTORICAL_PDF))
    print(f"   Pages: {len(pdf_hist.pages)}")
    
    for year, pages in sorted(YEAR_PAGES.items(), reverse=True):
        print(f"\n  📅 Extracting {year}...")
        
        # Rental rates & values
        rental_text = get_pages_text(pdf_hist, pages["rental"])
        rental_rows = extract_rental_data(rental_text, year)
        all_rental.extend(rental_rows)
        print(f"    Rental rates: {len(rental_rows)} regions")
        
        # Respondent characteristics
        resp_text = get_pages_text(pdf_hist, pages["respondent"])
        resp_rows = extract_respondent_chars(resp_text, year)
        all_respondent.extend(resp_rows)
        print(f"    Respondent chars: {len(resp_rows)} variables")
        
        # Buyer perceptions
        buyer_text = get_pages_text(pdf_hist, pages["buyer"])
        if year == 2016:
            # 2016 has the 3-column format — extract both versions
            buyer_3col = extract_buyer_2016_3col(buyer_text)
            buyer_2016_3col.extend(buyer_3col)
            # Also create single-column version (farmers only) for the main dataset
            for row in buyer_3col:
                all_buyer.append({
                    'year': 2016,
                    'region': row['region'],
                    'pct_sales_to_farmers': row['pct_farmers'],
                    'n': row['n'],
                })
            print(f"    Buyer perceptions: {len(buyer_3col)} regions (3-category format)")
        else:
            buyer_rows = extract_buyer_perceptions(buyer_text, year)
            all_buyer.extend(buyer_rows)
            print(f"    Buyer perceptions: {len(buyer_rows)} regions")
        
        # Survey metadata
        title_text = get_pages_text(pdf_hist, [pages["start"]])
        meta = extract_survey_metadata(title_text, year)
        all_metadata.append(meta)
        print(f"    Respondents: {meta['total_respondents']}")
    
    pdf_hist.close()
    
    # -----------------------------------------------------------------------
    # Process 2025 PDF
    # -----------------------------------------------------------------------
    print(f"\n📄 Opening 2025 PDF: {CURRENT_PDF.name}")
    pdf_2025 = pdfplumber.open(str(CURRENT_PDF))
    print(f"   Pages: {len(pdf_2025.pages)}")
    
    year = 2025
    pages = YEAR_2025_PAGES
    print(f"\n  📅 Extracting {year}...")
    
    # Rental rates & values
    rental_text = get_pages_text(pdf_2025, pages["rental"])
    rental_rows = extract_rental_data(rental_text, year)
    all_rental.extend(rental_rows)
    print(f"    Rental rates: {len(rental_rows)} regions")
    
    # Respondent characteristics
    resp_text = get_pages_text(pdf_2025, pages["respondent"])
    resp_rows = extract_respondent_chars(resp_text, year)
    all_respondent.extend(resp_rows)
    print(f"    Respondent chars: {len(resp_rows)} variables")
    
    # Buyer perceptions
    buyer_text = get_pages_text(pdf_2025, pages["buyer"])
    buyer_rows = extract_buyer_perceptions(buyer_text, year)
    all_buyer.extend(buyer_rows)
    print(f"    Buyer perceptions: {len(buyer_rows)} regions")
    
    # Survey metadata
    title_text = get_pages_text(pdf_2025, [pages["start"]])
    meta = extract_survey_metadata(title_text, year)
    all_metadata.append(meta)
    print(f"    Respondents: {meta['total_respondents']}")
    
    pdf_2025.close()
    
    # -----------------------------------------------------------------------
    # Sort all datasets by year
    # -----------------------------------------------------------------------
    all_rental.sort(key=lambda r: (r['year'], r['region']))
    all_respondent.sort(key=lambda r: (r['year'], r['variable']))
    all_buyer.sort(key=lambda r: (r['year'], r['region']))
    all_metadata.sort(key=lambda r: r['year'])
    
    # -----------------------------------------------------------------------
    # Write CSVs
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("Writing CSV datasets...")
    print(f"{'=' * 70}")
    
    write_csv(
        OUTPUT_DIR / "onfvrvs_rental_rates_and_values.csv",
        all_rental,
        ['year', 'region', 'median_cash_rent_per_acre', 'rent_n',
         'median_land_price_per_acre', 'price_n', 'rent_price_ratio_pct']
    )
    
    write_csv(
        OUTPUT_DIR / "onfvrvs_respondent_characteristics.csv",
        all_respondent,
        ['year', 'variable', 'n', 'mean', 'median', 'std_dev', 'min', 'max']
    )
    
    write_csv(
        OUTPUT_DIR / "onfvrvs_buyer_perceptions.csv",
        all_buyer,
        ['year', 'region', 'pct_sales_to_farmers', 'n']
    )
    
    write_csv(
        OUTPUT_DIR / "onfvrvs_survey_metadata.csv",
        all_metadata,
        ['year', 'total_respondents', 'total_potential_respondents', 'response_rate_pct']
    )
    
    # Also write the 2016 3-category buyer data as supplementary
    if buyer_2016_3col:
        write_csv(
            OUTPUT_DIR / "onfvrvs_buyer_perceptions_2016_3cat.csv",
            buyer_2016_3col,
            ['year', 'region', 'n', 'pct_farmers', 'pct_lifestyle_buyers', 'pct_investors']
        )
    
    # -----------------------------------------------------------------------
    # Validation summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("VALIDATION SUMMARY")
    print(f"{'=' * 70}")
    
    # Year coverage
    rental_years = sorted(set(r['year'] for r in all_rental))
    buyer_years = sorted(set(r['year'] for r in all_buyer))
    resp_years = sorted(set(r['year'] for r in all_respondent))
    meta_years = sorted(set(r['year'] for r in all_metadata))
    
    print(f"\n  Rental data years:      {rental_years}")
    print(f"  Buyer data years:       {buyer_years}")
    print(f"  Respondent data years:  {resp_years}")
    print(f"  Metadata years:         {meta_years}")
    
    # Per-year rental row counts
    print(f"\n  Rental regions per year:")
    for y in sorted(set(r['year'] for r in all_rental)):
        count = sum(1 for r in all_rental if r['year'] == y)
        print(f"    {y}: {count} regions")
    
    # Spot-check: print sample rows
    print(f"\n  Sample rental data (first 5 rows):")
    for r in all_rental[:5]:
        print(f"    {r['year']} | {r['region']:40s} | rent=${r['median_cash_rent_per_acre']:>8} | "
              f"price=${r['median_land_price_per_acre'] if r['median_land_price_per_acre'] else 'N/A':>8} | "
              f"ratio={r['rent_price_ratio_pct']}%")
    
    # Numeric bounds check
    print(f"\n  Numeric bounds check:")
    rents = [r['median_cash_rent_per_acre'] for r in all_rental if r['median_cash_rent_per_acre'] is not None]
    prices = [r['median_land_price_per_acre'] for r in all_rental if r['median_land_price_per_acre'] is not None]
    
    rent_range = f"${min(rents):.0f} – ${max(rents):.0f}"
    price_range = f"${min(prices):.0f} – ${max(prices):.0f}"
    
    print(f"    Rent range:   {rent_range}")
    print(f"    Price range:  {price_range}")
    
    # Flag any suspicious values
    issues = []
    for r in all_rental:
        if r['median_cash_rent_per_acre'] and r['median_cash_rent_per_acre'] > 1000:
            issues.append(f"    ⚠ High rent: {r['year']} {r['region']} = ${r['median_cash_rent_per_acre']}")
        if r['median_land_price_per_acre'] and r['median_land_price_per_acre'] > 100000:
            issues.append(f"    ⚠ High price: {r['year']} {r['region']} = ${r['median_land_price_per_acre']}")
    
    if issues:
        print(f"\n  ⚠ Potential outliers ({len(issues)}):")
        for issue in issues:
            print(issue)
    else:
        print(f"\n  ✓ No outliers detected")
    
    # Final summary
    print(f"\n{'=' * 70}")
    print(f"✅ EXTRACTION COMPLETE")
    print(f"   Total rental rows:      {len(all_rental)}")
    print(f"   Total respondent rows:  {len(all_respondent)}")
    print(f"   Total buyer rows:       {len(all_buyer)}")
    print(f"   Total metadata rows:    {len(all_metadata)}")
    print(f"   Output directory:       {OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
