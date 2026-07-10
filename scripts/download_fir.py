"""
FIR Bulk Downloader
===================
Downloads all Financial Information Returns (FIR) for Ontario's 444 municipalities,
years 2000–2024, from the EFIS portal.

Data is published under the Open Government Licence – Ontario.
https://efis.fma.csc.gov.on.ca/fir/index.php/en/reports-and-dashboards/fir-by-year-and-municipality/

Usage:
    python scripts/download_fir.py                  # Full run
    python scripts/download_fir.py --scrape-only     # Just build manifest
    python scripts/download_fir.py --download-only   # Download from existing manifest
    python scripts/download_fir.py --year 2023       # Single year only
"""

import argparse
import csv
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://efis.fma.csc.gov.on.ca/fir/index.php/en/year-municipality/"
OUTPUT_DIR = Path(r"C:\Projects\Farm Finance Stats Dashboard\Database\farm_finance_dashboard_starter\data\FIR Data")
MANIFEST_PATH = OUTPUT_DIR / "download_manifest.csv"

# Conservative rate-limit: 2 seconds between downloads
DOWNLOAD_DELAY = 2.0

# Requests timeout (seconds)
TIMEOUT = 30

# User-agent to identify ourselves politely
HEADERS = {
    "User-Agent": "FIR-Research-Downloader/1.0 (Ontario Municipal Finance Research; ben.lefort)"
}

# Year page URL slugs — scraped from the FIR portal navigation
YEAR_PAGES = {
    2024: "year-2024-2-2-2-2/",
    2023: "year-2023-2-2/",
    2022: "year-2022-2-2-2/",
    2021: "year-2021-2/",
    2020: "year-2020/",
    2019: "year-2019/",
    2018: "year-2018/",
    2017: "year-2017/",
    2016: "year-2016/",
    2015: "year-2015/",
    2014: "year-2014/",
    2013: "year-2013/",
    2012: "year-2012/",
    2011: "year-2011/",
    2010: "year-2010/",
    2009: "year-2009/",
}
# 2000-2008 is a single combined page
ARCHIVE_PAGE = "years-2000-to-2008/"

# Delay between page scrapes (more conservative than file downloads)
PAGE_SCRAPE_DELAY = 3.0


# ---------------------------------------------------------------------------
# Phase 1: Scrape download links
# ---------------------------------------------------------------------------

def scrape_year_page(page_url: str) -> list[dict]:
    """Scrape all .zip download links from a single FIR year page."""
    print(f"  Scraping: {page_url}")
    resp = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if ".zip" in href.lower() and "fir-files" in href.lower():
            # Extract year from filename: FI{YY}{CODE} ...
            filename = urllib.parse.unquote(href.split("/")[-1])
            # Parse year from FI prefix: FI24 -> 2024, FI09 -> 2009, FI00 -> 2000
            match = re.match(r"FI(\d{2})", filename)
            if match:
                yy = int(match.group(1))
                year = 2000 + yy if yy < 50 else 1900 + yy
            else:
                year = 0  # Unknown, still download

            links.append({
                "url": href,
                "year": year,
                "filename": filename,
            })

    return links


def scrape_all_links(years: list[int] = None) -> list[dict]:
    """Scrape download links from all year pages. Returns list of dicts."""
    all_links = []

    # Individual year pages (2009–2024)
    for year, slug in sorted(YEAR_PAGES.items()):
        if years and year not in years:
            continue
        page_url = BASE_URL + slug
        links = scrape_year_page(page_url)
        print(f"    Found {len(links)} download links for {year}")
        all_links.extend(links)
        time.sleep(PAGE_SCRAPE_DELAY)

    # Archive page (2000–2008)
    need_archive = years is None or any(y in range(2000, 2009) for y in years)
    if need_archive:
        page_url = BASE_URL + ARCHIVE_PAGE
        links = scrape_year_page(page_url)
        print(f"    Found {len(links)} download links for 2000-2008 archive")
        # Filter to requested years if specified
        if years:
            links = [l for l in links if l["year"] in years]
        all_links.extend(links)

    # Deduplicate by URL
    seen = set()
    unique = []
    for link in all_links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)

    return unique


def save_manifest(links: list[dict]):
    """Save download manifest to CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "year", "filename"])
        writer.writeheader()
        writer.writerows(links)
    print(f"\nManifest saved: {MANIFEST_PATH} ({len(links)} entries)")


def load_manifest() -> list[dict]:
    """Load download manifest from CSV."""
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        print("Run with --scrape-only first, or without flags for full run.")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


# ---------------------------------------------------------------------------
# Phase 2: Download files
# ---------------------------------------------------------------------------

def download_files(links: list[dict], years: list[int] = None):
    """Download all FIR zip files with rate limiting and resume support."""
    # Filter by year if specified
    if years:
        links = [l for l in links if int(l["year"]) in years]

    total = len(links)
    downloaded = 0
    skipped = 0
    failed = 0
    failures = []

    print(f"\n{'='*60}")
    print(f"Starting download: {total} files")
    print(f"Rate limit: {DOWNLOAD_DELAY}s between requests")
    print(f"Estimated time: {total * DOWNLOAD_DELAY / 60:.0f} minutes")
    print(f"{'='*60}\n")

    for i, link in enumerate(links, 1):
        year = int(link["year"])
        filename = link["filename"]
        url = link["url"]

        # Create year folder
        year_dir = OUTPUT_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        dest = year_dir / filename

        # Skip if already downloaded
        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
            resp.raise_for_status()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            downloaded += 1
            if downloaded % 25 == 0 or i == total:
                print(f"  [{i}/{total}] Downloaded {downloaded} | Skipped {skipped} | Failed {failed}")

        except Exception as e:
            failed += 1
            failures.append((url, str(e)))
            print(f"  FAILED [{i}/{total}] {filename}: {e}")

        # Rate limit
        time.sleep(DOWNLOAD_DELAY)

    # Summary
    print(f"\n{'='*60}")
    print(f"DOWNLOAD COMPLETE")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped (already existed): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total processed: {total}")
    print(f"{'='*60}")

    if failures:
        fail_log = OUTPUT_DIR / "download_failures.csv"
        with open(fail_log, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url", "error"])
            writer.writerows(failures)
        print(f"\nFailure log: {fail_log}")

    # Print per-year summary
    print(f"\nFiles per year:")
    year_counts = {}
    for link in links:
        y = int(link["year"])
        year_counts[y] = year_counts.get(y, 0) + 1
    for y in sorted(year_counts):
        year_dir = OUTPUT_DIR / str(y)
        actual = len(list(year_dir.glob("*.zip"))) if year_dir.exists() else 0
        print(f"  {y}: {actual}/{year_counts[y]} files")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Download Ontario FIR data")
    parser.add_argument("--scrape-only", action="store_true",
                        help="Only scrape links, don't download")
    parser.add_argument("--download-only", action="store_true",
                        help="Download from existing manifest")
    parser.add_argument("--year", type=int, nargs="+",
                        help="Only process specific year(s)")
    args = parser.parse_args()

    years = args.year

    if args.download_only:
        links = load_manifest()
        download_files(links, years)
    elif args.scrape_only:
        print("Phase 1: Scraping download links...")
        links = scrape_all_links(years)
        save_manifest(links)
        print(f"\nDone! Found {len(links)} total download links.")
    else:
        # Full run: scrape + download
        print("Phase 1: Scraping download links...")
        links = scrape_all_links(years)
        save_manifest(links)
        print(f"\nPhase 2: Downloading {len(links)} files...")
        download_files(links)


if __name__ == "__main__":
    main()
