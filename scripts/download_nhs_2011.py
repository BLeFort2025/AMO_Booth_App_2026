"""
Download 2011 National Household Survey (NHS) Profile — CSD-level CSV
=====================================================================
The 2011 NHS was a separate survey from the Census short-form. It contains
income, labour force, education, housing costs, commuting, immigration,
and visible minority data that is NOT in the 2011 Census Profile.

Catalogue: 99-004-XWE2011001
Geographic level: 301 (Census Subdivisions)
Format: CSV (inside ZIP)

Usage:
    python scripts/download_nhs_2011.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from scripts.http_utils import get_robust_session

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR = BASE_DIR / "data" / "raw"
OUT_FILE = RAW_DIR / "99-004-XWE2011001-301_CSV.zip"

# StatCan download URL for NHS CSD-level CSV
NHS_URL = (
    "https://www12.statcan.gc.ca/nhs-enm/2011/dp-pd/prof/details/"
    "download-telecharger/comprehensive/comp_download.cfm?"
    "CTLG=99-004-XWE2011001&FMT=CSV301&Lang=E"
)

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks


def download():
    """Download the 2011 NHS CSD-level CSV ZIP."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if OUT_FILE.exists():
        size_mb = OUT_FILE.stat().st_size / (1024 * 1024)
        print(f"[SKIP] {OUT_FILE.name} already exists ({size_mb:.1f} MB)")
        print(f"       Delete the file to re-download.")
        return str(OUT_FILE)

    print(f"Downloading 2011 NHS Profile (CSD-level) ...")
    print(f"  URL: {NHS_URL[:80]}...")
    print(f"  Destination: {OUT_FILE}")

    try:
        session = get_robust_session()
        r = session.get(NHS_URL, stream=True, timeout=120, allow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        print(
            "\nManual download fallback:"
            "\n  1. Go to: https://www12.statcan.gc.ca/nhs-enm/2011/dp-pd/prof/"
            "details/download-telecharger/comprehensive/comp-csv-tab-nhs-enm.cfm?Lang=E"
            "\n  2. Click 'CSV' next to 'Census subdivisions'"
            f"\n  3. Save as: {OUT_FILE}"
        )
        sys.exit(1)

    # Verify it looks like a ZIP
    content_type = r.headers.get("content-type", "")
    first_chunk = None
    total_bytes = 0

    with open(OUT_FILE, "wb") as f:
        for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                if first_chunk is None:
                    first_chunk = chunk
                    if not chunk[:2] == b"PK":
                        print(f"[ERROR] Response is not a ZIP file (content-type: {content_type})")
                        OUT_FILE.unlink(missing_ok=True)
                        sys.exit(1)
                f.write(chunk)
                total_bytes += len(chunk)
                print(f"\r  Downloaded: {total_bytes / (1024 * 1024):.1f} MB", end="", flush=True)

    print(f"\n\n[OK] Saved: {OUT_FILE} ({total_bytes / (1024 * 1024):.1f} MB)")
    return str(OUT_FILE)


def run():
    """Entry point for pipeline integration."""
    return download()


if __name__ == "__main__":
    download()
