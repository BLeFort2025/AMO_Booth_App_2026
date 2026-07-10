import io, json, zipfile, requests, pandas as pd
from datetime import date
from pathlib import Path
import hashlib
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import config_loader
from scripts.http_utils import get_robust_session

DATA_LATEST = config_loader.get_raw_data_dir()
DATA_ARCH   = Path("data/archive")
MANIFEST_FP = Path("data/manifest.json")


def csv_zip_url(table_id: str) -> str:
    # Example: "32-10-0045-01" -> "32100045" -> "32100045-eng.zip"
    pid = table_id.replace("-", "")      # "3210004501"
    file_id = pid[:8]                    # "32100045"
    return f"https://www150.statcan.gc.ca/n1/tbl/csv/{file_id}-eng.zip"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_manifest():
    if MANIFEST_FP.exists():
        return json.loads(MANIFEST_FP.read_text())
    return {"tables": {}}


def save_manifest(m):
    MANIFEST_FP.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FP.write_text(json.dumps(m, indent=2))

def fetch_table(table_id: str, session: requests.Session | None = None) -> tuple[pd.DataFrame, str]:
    """
    Fetch a StatCan table (CSV packed inside ZIP), safely handling cases
    where the ZIP contains both a data CSV and a metadata CSV.

    Returns:
        df (DataFrame): the parsed CSV data
        content_hash (str): sha256 hash of the ZIP content
    """
    if session is None:
        session = get_robust_session()
    url = csv_zip_url(table_id)
    print(f"[INFO] Downloading {table_id} from {url}")
    r = session.get(url, timeout=180, verify=False)
    r.raise_for_status()

    # Open the StatCan ZIP
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()

    # Keep only CSV files
    csv_names = [n for n in names if n.lower().endswith(".csv")]
    if not csv_names:
        raise ValueError(f"No CSV files found in ZIP: {names}")

    # Prefer the main data file (avoid metadata files)
    preferred = [n for n in csv_names if "metadata" not in n.lower()]
    if preferred:
        chosen = sorted(preferred)[0]
    else:
        chosen = sorted(csv_names)[0]

    with z.open(chosen) as f:
        df = pd.read_csv(f, low_memory=False)

    return df, sha256_bytes(r.content)


def ensure_year_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a YEAR column if REF_DATE (or similar) is present.

    Handles numeric or string REF_DATE values. If parsing the date fails,
    falls back to extracting the first 4-digit year token.
    """

    if "YEAR" in df.columns:
        return df

    # Common alternate naming used in some StatCan extracts
    ref_col = None
    for candidate in ["REF_DATE", "Reference period", "Reference Period"]:
        if candidate in df.columns:
            ref_col = candidate
            break

    if ref_col is None and "Year" in df.columns:
        df = df.rename(columns={"Year": "YEAR"})
        return df

    if ref_col is None:
        return df

    ref = df[ref_col]
    if pd.api.types.is_numeric_dtype(ref):
        years = pd.to_numeric(ref, errors="coerce")
    else:
        parsed = pd.to_datetime(ref.astype(str), errors="coerce")
        years = parsed.dt.year
        if years.isna().all():
            years = ref.astype(str).str.extract(r"(\d{4})")[0]

    df = df.assign(YEAR=pd.to_numeric(years, errors="coerce"))
    return df


def persist_if_changed(table_id: str, df: pd.DataFrame, content_hash: str) -> bool:
    latest_fp = DATA_LATEST / f"{table_id}.csv"
    DATA_LATEST.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    prev_hash = manifest["tables"].get(table_id, {}).get("content_hash")

    if prev_hash == content_hash and latest_fp.exists():
        return False

    # Save latest
    df.to_csv(latest_fp, index=False)

    # Save archived copy
    stamp = date.today().isoformat()
    arch_dir = DATA_ARCH / stamp
    arch_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(arch_dir / f"{table_id}.csv", index=False)

    # Update manifest
    manifest["tables"][table_id] = {
        "content_hash": content_hash,
        "rows": int(len(df)),
        "last_updated_local": stamp,
    }
    save_manifest(manifest)

    return True


def run():
    cfg_tables = config_loader.load_tables()
    changed = []
    failed = []

    session = get_robust_session()

    for t in cfg_tables:
        tid = t["id"]
        if not t.get("active", True):
            continue
        if t.get("source", "statcan") != "statcan":
            continue

        try:
            df, h = fetch_table(tid, session)
            df = ensure_year_column(df)
            time.sleep(1.5)  # Add delay to avoid StatCan connection drops
        except Exception as e:
            print(f"[ERROR] Failed to fetch {tid}: {e}")
            failed.append(tid)
            continue

        if persist_if_changed(tid, df, h):
            changed.append(tid)

    print(f"Updated: {changed}" if changed else "No changes.")
    if failed:
        print(f"Failed to update: {failed}")


if __name__ == "__main__":
    run()
