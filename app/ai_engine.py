"""
AI Research Assistant — core engine.

Auto-discovers all CSV datasets in data/, builds schema descriptions,
sends questions to Gemini Flash, and executes generated pandas code
in a restricted sandbox.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import re
import textwrap
import time
import traceback
from pathlib import Path
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
from scipy import stats as _scipy_stats

# ── Project root ────────────────────────────────────────
from app.smart_read import smart_read
_PROJECT = Path(__file__).resolve().parents[1]
DATA_ROOT = _PROJECT / "data"

# Directories to scan for datasets
_SCAN_DIRS = [
    DATA_ROOT / "derived",
    DATA_ROOT / "latest",
    DATA_ROOT / "latest" / "wellbeing",
    DATA_ROOT / "surveys",
    DATA_ROOT / "omafra",
]

# Skip these directories / patterns during scan
_SKIP_PATTERNS = {"archive", "_fir_inspect", "FIR Data", "__pycache__"}

# Maximum sample rows sent to LLM (schema only — never full data)
_SAMPLE_ROWS = 3
# Maximum columns to describe per table (keep prompt concise)
_MAX_COLS_DESCRIBED = 40
# Daily query cap  (Gemini 2.5 Flash free tier = 250 RPD).
DAILY_QUERY_CAP = 50

# Maximum CSV file size (in MB) the AI assistant will index.
# Files larger than this are handled by dedicated engines (IO multipliers,
# trade pipeline, etc.) and would crash Streamlit Cloud's 1 GB memory limit
# if loaded by the sandbox.  The row-counting scan alone for a 3 GB file
# can spike memory beyond the container limit.
_MAX_FILE_SIZE_MB = 200

# Maximum number of full DataFrames kept in the in-memory cache.
# Older entries are evicted when this limit is exceeded.
_MAX_CACHED_DATAFRAMES = 3

# Retry configuration for API errors
_MAX_API_RETRIES = 3
_RETRY_DELAYS = [2, 5, 10]  # seconds

log = logging.getLogger(__name__)


class GeminiAPIError(Exception):
    """Raised when the Gemini API returns a transient error after retries."""
    pass


# ════════════════════════════════════════════════════════
#  DATA REGISTRY — auto-discover every CSV
# ════════════════════════════════════════════════════════

class DatasetInfo:
    """Metadata for a single discovered CSV file."""
    __slots__ = ("path", "name", "category", "columns", "dtypes",
                 "n_rows", "n_cols", "sample_text")

    def __init__(self, path: Path, category: str):
        self.path = path
        self.category = category
        self.name = path.stem  # e.g.  "fir_indicators"
        try:
            df = pd.read_csv(path, nrows=_SAMPLE_ROWS)
            # Estimate row count from file size and average row length
            # instead of iterating every line (which reads multi-GB files
            # into memory and crashes Streamlit Cloud).
            file_size = path.stat().st_size
            if not df.empty:
                # Use the sample rows to estimate average bytes per row
                sample_bytes = sum(
                    len(str(v)) for row in df.values for v in row
                ) + len(df.columns) * _SAMPLE_ROWS  # commas/newlines
                avg_row_bytes = max(sample_bytes / _SAMPLE_ROWS, 1)
                full_len = int(file_size / avg_row_bytes)
            else:
                full_len = 0
        except Exception:
            df = pd.DataFrame()
            full_len = 0
        self.columns = list(df.columns)[:_MAX_COLS_DESCRIBED]
        self.dtypes = {c: str(df[c].dtype) for c in self.columns}
        self.n_rows = max(full_len, 0)
        self.n_cols = len(df.columns)

        # Build a compact sample text for the LLM
        if not df.empty:
            lines = df.head(_SAMPLE_ROWS).to_string(index=False, max_cols=12)
            self.sample_text = lines[:600]
        else:
            self.sample_text = "(no data)"

    @property
    def schema_description(self) -> str:
        """Compact description for the LLM prompt."""
        cols = ", ".join(f"{c} ({self.dtypes.get(c, '?')})" for c in self.columns)
        extra = ""
        return (
            f"TABLE: {self.name}  [category={self.category}, "
            f"{self.n_rows} rows, {self.n_cols} cols]\n"
            f"  Columns: {cols}{extra}\n"
            f"  Sample:\n{textwrap.indent(self.sample_text, '    ')}"
        )


class OnDemandDatasetInfo:
    """Metadata stub for a StatCan table not yet on disk.

    The full schema is populated lazily on first load/describe.
    """
    __slots__ = ("name", "category", "table_cfg", "columns", "dtypes",
                 "n_rows", "n_cols", "sample_text", "_hydrated")

    def __init__(self, table_cfg: dict):
        self.table_cfg = table_cfg
        self.name = table_cfg["id"]
        self.category = "Statistics Canada"
        # Build a descriptive line from config metadata
        cfg_name = table_cfg.get("name", "")
        cfg_notes = table_cfg.get("notes", "")
        cfg_theme = table_cfg.get("theme", "")
        desc_parts = [p for p in [cfg_name, cfg_theme, cfg_notes] if p]
        desc_line = " | ".join(desc_parts) if desc_parts else ""
        self.columns = []
        self.dtypes = {}
        self.n_rows = 0
        self.n_cols = 0
        self.sample_text = f"(on-demand — {desc_line})" if desc_line else "(on-demand)"
        self._hydrated = False

    def hydrate(self, df: pd.DataFrame):
        """Populate schema metadata from the actual DataFrame once loaded."""
        if self._hydrated:
            return
        self.columns = list(df.columns)[:_MAX_COLS_DESCRIBED]
        self.dtypes = {c: str(df[c].dtype) for c in self.columns}
        self.n_rows = len(df)
        self.n_cols = len(df.columns)
        if not df.empty:
            lines = df.head(_SAMPLE_ROWS).to_string(index=False, max_cols=12)
            self.sample_text = lines[:600]
        self._hydrated = True

    @property
    def schema_description(self) -> str:
        """Compact description for the LLM prompt."""
        cfg_name = self.table_cfg.get("name", "")
        cfg_notes = self.table_cfg.get("notes", "")
        cfg_theme = self.table_cfg.get("theme", "")
        desc_parts = [p for p in [cfg_name, cfg_theme] if p]
        title_line = " — ".join(desc_parts) if desc_parts else self.name

        if self.columns:
            cols = ", ".join(f"{c} ({self.dtypes.get(c, '?')})" for c in self.columns)
        else:
            cols = f"(columns available on load — call describe(\"{self.name}\") first)"

        notes_line = f"\n  Notes: {cfg_notes}" if cfg_notes else ""
        return (
            f"TABLE: {self.name}  [{title_line}, category={self.category}, "
            f"{self.n_rows} rows, {self.n_cols} cols]\n"
            f"  Columns: {cols}{notes_line}\n"
            f"  Sample:\n{textwrap.indent(self.sample_text, '    ')}"
        )


class DataRegistry:
    """Discovers and indexes all CSV files under data/, plus on-demand StatCan tables."""

    def __init__(self):
        self.datasets: dict[str, DatasetInfo | OnDemandDatasetInfo] = {}
        self._dataframes: dict[str, pd.DataFrame] = {}
        self._discover()

    def _discover(self):
        seen_paths: set[str] = set()
        seen_table_ids: set[str] = set()

        # ── Phase 1: Scan local CSV files ──
        for scan_dir in _SCAN_DIRS:
            if not scan_dir.exists():
                continue
            for csv_file in sorted(scan_dir.rglob("*.csv")):
                # Skip unwanted directories
                parts = set(csv_file.parts)
                if parts & _SKIP_PATTERNS:
                    continue

                # Skip files larger than the size limit — they are
                # handled by dedicated engines and would OOM the app.
                try:
                    file_mb = csv_file.stat().st_size / (1024 * 1024)
                    if file_mb > _MAX_FILE_SIZE_MB:
                        log.debug("Skipping large file (%.0f MB): %s", file_mb, csv_file.name)
                        continue
                except OSError:
                    continue

                canon = str(csv_file.resolve())
                if canon in seen_paths:
                    continue
                seen_paths.add(canon)

                # Determine category from directory
                rel = csv_file.relative_to(DATA_ROOT)
                if str(rel).startswith("derived"):
                    cat = "Derived Indicators"
                elif str(rel).startswith("surveys"):
                    cat = "OFA Surveys"
                elif "wellbeing" in str(rel):
                    cat = "Wellbeing & Census"
                elif "omafra" in str(rel):
                    cat = "Statistics Canada"
                else:
                    cat = "Statistics Canada"

                name = csv_file.stem
                # Handle duplicate names by prefixing category
                if name in self.datasets:
                    name = f"{cat.split()[0].lower()}_{name}"

                info = DatasetInfo(csv_file, cat)
                info.name = name
                self.datasets[name] = info
                seen_table_ids.add(name)

        # ── Phase 2: Register on-demand StatCan tables from config ──
        try:
            from scripts import config_loader
            all_tables = config_loader.load_tables(active_only=True)
            if isinstance(all_tables, list):
                for t in all_tables:
                    table_id = t.get("id", "")
                    if not table_id or table_id in seen_table_ids:
                        continue
                    # Also skip if we already have its CSV stem
                    csv_name = t.get("csv", f"{table_id}.csv")
                    csv_stem = csv_name.replace(".csv", "")
                    if csv_stem in seen_table_ids:
                        continue
                    # Only register tables that can be fetched on demand
                    if not t.get("statscan_url"):
                        continue
                    od_info = OnDemandDatasetInfo(t)
                    self.datasets[table_id] = od_info
                    seen_table_ids.add(table_id)
        except Exception as e:
            log.warning("Could not load tables.yml for on-demand discovery: %s", e)

    def get_dataframe(self, name: str) -> pd.DataFrame:
        """Lazily load and cache a dataset (local CSV or on-demand StatCan fetch)."""
        if name not in self._dataframes:
            info = self.datasets.get(name)
            if info is None:
                raise KeyError(f"Dataset '{name}' not found. Available: {list(self.datasets.keys())}")

            if isinstance(info, OnDemandDatasetInfo):
                # Use the dashboard's live-fetch pipeline
                try:
                    from app.utils import load_dataset
                    df = load_dataset(info.table_cfg)
                    info.hydrate(df)
                    self._dataframes[name] = df
                except Exception as e:
                    raise KeyError(
                        f"Failed to fetch on-demand dataset '{name}' from Statistics Canada: {e}"
                    ) from e
            else:
                self._dataframes[name] = smart_read(info.path)

            # Evict oldest cached DataFrames to stay within memory budget.
            # dict preserves insertion order in Python 3.7+, so the first
            # keys are the oldest.
            while len(self._dataframes) > _MAX_CACHED_DATAFRAMES:
                oldest_key = next(iter(self._dataframes))
                del self._dataframes[oldest_key]

        return self._dataframes[name]

    def list_datasets(self, keyword: str = "") -> list[dict]:
        """Search datasets by keyword in name or category. Returns list of dicts."""
        results = []
        kw = keyword.lower()
        for name, info in self.datasets.items():
            if kw and kw not in name.lower() and kw not in info.category.lower():
                continue
            results.append({
                "name": name,
                "category": info.category,
                "rows": info.n_rows,
                "columns": info.n_cols,
            })
        return results

    def describe_dataset(self, name: str) -> dict:
        """Return full column info for a dataset, including unique values for categoricals."""
        df = self.get_dataframe(name)
        info = {}
        for col in df.columns:
            col_info = {"dtype": str(df[col].dtype)}
            # For object/category columns with ≤30 unique values, show them
            if df[col].dtype == "object" or str(df[col].dtype) == "category":
                nunique = df[col].nunique()
                if nunique <= 30:
                    col_info["unique_values"] = sorted(
                        df[col].dropna().unique().tolist()
                    )
                else:
                    col_info["nunique"] = nunique
                    col_info["sample_values"] = df[col].dropna().unique()[:5].tolist()
            else:
                col_info["min"] = str(df[col].min())
                col_info["max"] = str(df[col].max())
            info[col] = col_info
        return info

    def find_common_keys(self, name1: str, name2: str) -> list[str]:
        """Find column names that exist in both datasets (potential join keys)."""
        df1 = self.get_dataframe(name1)
        df2 = self.get_dataframe(name2)
        common = [c for c in df1.columns if c in df2.columns]
        return common

    def match_geo(self, dataset_name: str, search_term: str) -> str | None:
        """Find the exact GEO value matching a search term (partial, case-insensitive).

        Many StatCan datasets use coded GEO values like 'Ontario [PR350000000]'.
        This helper handles that automatically.

        Args:
            dataset_name: Name of the dataset to search.
            search_term: The geography to find (e.g., 'Ontario', 'PEI', 'Canada').

        Returns:
            The exact GEO value string to use in filtering, or None if not found.
        """
        df = self.get_dataframe(dataset_name)
        geo_cols = [c for c in df.columns if 'geo' in c.lower()]
        if not geo_cols:
            return None
        geo_col = geo_cols[0]
        search_lower = search_term.lower()
        for val in df[geo_col].dropna().unique():
            if search_lower in str(val).lower():
                return str(val)
        return None

    def build_schema_prompt(self) -> str:
        """Build the full schema description for the LLM prompt."""
        parts = []
        by_cat: dict[str, list[DatasetInfo]] = {}
        for info in self.datasets.values():
            by_cat.setdefault(info.category, []).append(info)

        for cat in sorted(by_cat):
            parts.append(f"\n{'='*60}\n  {cat.upper()}\n{'='*60}")
            for info in sorted(by_cat[cat], key=lambda i: i.name):
                parts.append(info.schema_description)

        return "\n\n".join(parts)

    @property
    def table_names(self) -> list[str]:
        return sorted(self.datasets.keys())

    @property
    def summary(self) -> str:
        cats = {}
        for info in self.datasets.values():
            cats[info.category] = cats.get(info.category, 0) + 1
        lines = [f"  {cat}: {n} datasets" for cat, n in sorted(cats.items())]
        return f"Total: {len(self.datasets)} datasets\n" + "\n".join(lines)


# ════════════════════════════════════════════════════════
#  SAFE EXECUTOR — sandboxed pandas execution
# ════════════════════════════════════════════════════════

# Blocked module names
_BLOCKED_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "http",
    "urllib", "requests", "pathlib", "io", "builtins",
    "importlib", "ctypes", "signal", "threading", "multiprocessing",
})

# Blocked function names
_BLOCKED_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__", "open",
    "input", "breakpoint", "exit", "quit",
})


def _safe_import_check(code: str) -> str | None:
    """Return an error message if the code tries to import blocked modules."""
    import_pattern = re.compile(
        r'(?:^|\n)\s*(?:import|from)\s+(\w+)', re.MULTILINE
    )
    for match in import_pattern.finditer(code):
        mod = match.group(1)
        if mod in _BLOCKED_MODULES:
            return f"Blocked import: '{mod}' is not allowed in the sandbox."
    return None


def _safe_builtin_check(code: str) -> str | None:
    """Return an error if the code uses blocked builtins."""
    for fn in _BLOCKED_BUILTINS:
        # Match function calls like open(...) or __import__(...)
        if re.search(rf'\b{re.escape(fn)}\s*\(', code):
            return f"Blocked function: '{fn}()' is not allowed in the sandbox."
    return None


# Safe builtins whitelist
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool,
    "dict": dict, "enumerate": enumerate, "filter": filter,
    "float": float, "format": format, "frozenset": frozenset,
    "getattr": getattr, "hasattr": hasattr, "hash": hash,
    "int": int, "isinstance": isinstance, "issubclass": issubclass,
    "iter": iter, "len": len, "list": list, "map": map,
    "max": max, "min": min, "next": next, "print": print,
    "range": range, "repr": repr, "reversed": reversed,
    "round": round, "set": set, "slice": slice, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "type": type,
    "zip": zip, "None": None, "True": True, "False": False,
    "KeyError": KeyError, "ValueError": ValueError,
    "TypeError": TypeError, "IndexError": IndexError,
    "AttributeError": AttributeError, "Exception": Exception,
}

# Allowed imports (the only modules the LLM can import)
_ALLOWED_IMPORTS = {
    "pandas": pd, "numpy": np, "datetime": _dt,
    "pd": pd, "np": np, "altair": alt, "alt": alt,
    "scipy": __import__("scipy"), "scipy.stats": _scipy_stats,
}

def _restricted_import(name, *args, **kwargs):
    """Only allow importing safe modules."""
    if name in _ALLOWED_IMPORTS:
        return _ALLOWED_IMPORTS[name]
    raise ImportError(f"Import of '{name}' is not allowed. Use pre-loaded pd, np, datetime.")


class SafeExecutor:
    """Execute LLM-generated pandas code in a restricted namespace."""

    def __init__(self, registry: DataRegistry):
        self.registry = registry

    def execute(self, code: str) -> dict[str, Any]:
        """
        Run code and return a dict with:
          - "result": the value of `RESULT` variable if set by the code
          - "dataframes": any DataFrames created
          - "error": error string if any
          - "code": the code that was run
        """
        # Safety checks
        err = _safe_import_check(code)
        if err:
            return {"result": None, "dataframes": {}, "error": err, "code": code}

        err = _safe_builtin_check(code)
        if err:
            return {"result": None, "dataframes": {}, "error": err, "code": code}

        # Build restricted builtins
        safe_builtins = dict(_SAFE_BUILTINS)
        safe_builtins["__import__"] = _restricted_import

        # Build namespace with dataset access
        namespace: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "pd": pd,
            "np": np,
            "alt": alt,
            "scipy": __import__("scipy"),
            "datetime": _dt,
            "load": self.registry.get_dataframe,
            "list_datasets": self.registry.list_datasets,
            "describe": self.registry.describe_dataset,
            "find_common_keys": self.registry.find_common_keys,
            "match_geo": self.registry.match_geo,
            "CURRENT_YEAR": _dt.date.today().year,
            "RESULT": None,
            "CHART": None,
        }

        try:
            exec(code, namespace)
        except Exception as e:
            tb = traceback.format_exc()
            return {
                "result": None,
                "dataframes": {},
                "error": f"{type(e).__name__}: {e}\n{tb[-500:]}",
                "code": code,
            }

        # Collect results
        result = namespace.get("RESULT")
        chart = namespace.get("CHART")
        dfs = {
            k: v for k, v in namespace.items()
            if isinstance(v, pd.DataFrame) and k not in ("pd",) and not k.startswith("_")
        }

        return {
            "result": result,
            "chart": chart,
            "dataframes": dfs,
            "error": None,
            "code": code,
        }


# ════════════════════════════════════════════════════════
#  GEMINI AGENT
# ════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
You are a data analyst assistant for the Ontario Federation of Agriculture (OFA) dashboard.
You answer questions by writing Python/pandas code that runs against the dashboard's datasets.

IMPORTANT CONTEXT:
- The current year is {current_year}.
- The variable `CURRENT_YEAR` (an integer) is already available in your namespace.
- You can call `list_datasets(keyword)` to search for datasets by name or category.
- You MUST call `describe("dataset_name")` BEFORE filtering any dataset.
- You can call `find_common_keys("dataset1", "dataset2")` before merging.
- You can call `match_geo("dataset_name", "Ontario")` to find the exact GEO value
  for a province/territory. This handles coded values like "Ontario [PR350000000]".

ON-DEMAND DATASETS (CRITICAL):
- Many datasets show "0 rows" in the catalog below. These are fetched live from
  Statistics Canada when you call `load()`. They ARE available — just not pre-loaded.
- PAY ATTENTION to the table NAME and NOTES in each TABLE entry — they tell you
  exactly what data the table contains. Use this to pick the RIGHT dataset.
- For on-demand datasets, you MUST call `describe()` FIRST to discover the actual
  column names. NEVER guess column names for these tables.
- SAFE COLUMN LOOKUP PATTERN (prevents IndexError on empty list):
  ```
  matches = [c for c in info if 'keyword' in c.lower()]
  if not matches:
      RESULT = f"Column containing 'keyword' not found. Available columns: {list(info.keys())}"
  else:
      target_col = matches[0]
  ```
  ALWAYS use this pattern. NEVER do `[c for c in info if ...][0]` directly.

RULES:
1. Use `load("dataset_name")` to load any dataset as a DataFrame.
2. ALWAYS store your final answer in the variable `RESULT` — this is what gets displayed.
   - If RESULT is a string, it will be shown as text.
   - If RESULT is a DataFrame, it will be shown as a table.
   - If RESULT is a dict with keys "text" and "df", both will be shown.
   NEVER leave RESULT as None. Always provide a meaningful, analytical answer.
3. `pd` (pandas), `np` (numpy), `alt` (altair), `datetime`, and `scipy.stats` are
   already available. Do NOT import them again. For scipy.stats, use:
   `from scipy.stats import pearsonr, spearmanr` or `from scipy import stats`.
4. Do NOT use: open(), os, subprocess, requests, or any file/network I/O.
5. Do NOT use exec(), eval(), or __import__().
5b. Do NOT use exit() or quit(). They are blocked in the sandbox and will crash
    your code. If a column is not found or data is missing, set RESULT to a
    descriptive error message string and use if/else blocks to skip further code.
    Example of the CORRECT early-return pattern:
    ```
    cols = [c for c in info if 'geo' in c.lower()]
    if not cols:
        RESULT = "Error: 'geo' column not found."
    else:
        geo_col = cols[0]
        # ... continue processing ...
    ```
6. Keep code concise and correct. Use descriptive variable names.
7. For cross-dataset analysis, load multiple datasets and merge on common keys
   (e.g. county, sgc_code, municipality, year).
8. Always handle missing data gracefully with .dropna() or .fillna().
9. When aggregating, round results to 2 decimal places.
10. If the question is ambiguous, make reasonable assumptions and note them in RESULT.
10b. GEOGRAPHY REQUIREMENT: If the user's question involves geographic data
    (counties, municipalities, provinces, regions) but does NOT specify which
    geography to analyze, set RESULT to a clarification message asking them
    to specify. Example:
    RESULT = ("Please specify which geography you'd like to analyze. "
              "For example: a specific county (e.g., Oxford, Wellington), "
              "a province (e.g., Ontario), or 'all counties' for a provincial summary.")
    Exception: If the question is clearly about Ontario-wide or provincial-level
    data (e.g., 'Ontario milk production', 'provincial farm expenses'), default
    to Ontario without asking.
11. IMPORTANT — Column names can be very long. NEVER hardcode long column names as string
    literals. Instead, use one of these safe patterns:
    - `df.columns[i]` to reference a column by index
    - `[c for c in df.columns if 'keyword' in c.lower()][0]` to find a column by keyword
    - `df.filter(like='keyword')` to select columns containing a keyword
    - Assign the column name to a variable first: `col = df.columns[3]`
12. Always write COMPLETE, syntactically valid Python. Never truncate strings or lines.

COLUMN DISCOVERY (MANDATORY — your code WILL FAIL without this):
13. You MUST call `describe("dataset_name")` BEFORE filtering ANY dataset.
    Your code will produce wrong results if you skip this step.
14. MANDATORY two-step workflow:
    ```
    # STEP 1: Discover schema (NEVER skip this)
    info = describe("dataset_name")
    df = load("dataset_name")
    
    # STEP 2: Use info to find exact column names and values
    geo_col = [c for c in info if 'geo' in c.lower()][0]
    geo_values = info[geo_col].get('unique_values', info[geo_col].get('sample_values', []))
    target_val = [v for v in geo_values if 'ontario' in str(v).lower()][0]
    df_filtered = df[df[geo_col] == target_val]
    ```
15. For categorical filtering, ALWAYS get actual values from describe() first:
    ```
    info = describe("my_dataset")
    # Find the column you need by keyword:
    target_col = [c for c in info if 'indicator' in c.lower()][0]
    # Get the actual values this column contains:
    actual_values = info[target_col].get('unique_values', info[target_col].get('sample_values', []))
    # Pick the value that best matches what you need:
    best_match = [v for v in actual_values if 'broadband' in str(v).lower()][0]
    ```

TIME-SERIES & DATE FILTERING (CRITICAL):
16. "Last N years" means from CURRENT_YEAR - N to CURRENT_YEAR. ALWAYS use `CURRENT_YEAR`.
17. Many StatCan datasets store dates in a `REF_DATE` column (string like "2023" or
    "2023-01"). FIR / derived / survey datasets use `year` (integer). Always check
    which column exists and parse it correctly.
18. For year-range filtering, ALWAYS convert to integer first and then filter:
    ```
    # For StatCan datasets with REF_DATE:
    df['_year'] = pd.to_numeric(df['REF_DATE'].astype(str).str[:4], errors='coerce')
    df = df[df['_year'].between(start_year, end_year)]
    # For FIR / derived datasets with 'year':
    df = df[df['year'].between(start_year, end_year)]
    ```
19. NEVER assume 3 rows of sample data represent all available years. The data spans
    decades. Always filter by the time range the user asks for.

MERGING DATASETS (CRITICAL — follow this checklist):
20. BEFORE any merge, call `find_common_keys("dataset1", "dataset2")` to find
    shared column names. Then verify the key values overlap:
    ```
    common = find_common_keys("dataset1", "dataset2")
    # Pick the best join key from common columns
    join_key = common[0]  # e.g. 'sgc_code' or 'county'
    # Verify there is actual overlap:
    overlap = set(df1[join_key].dropna()) & set(df2[join_key].dropna())
    ```
21. When merging, ALWAYS use `suffixes=('', '_drop')` and then drop the extras:
    ```
    merged = df1.merge(df2, on=join_key, how='inner', suffixes=('', '_drop'))
    merged = merged[[c for c in merged.columns if not c.endswith('_drop')]]
    ```
22. After ANY merge, NEVER reference a column name you have not verified exists.
    Always re-inspect `merged.columns` if needed.
23. For county-level joins, the common keys are typically `county`, `sgc_code`, or
    `municipality_name`. Always use `.dropna()` on the join key first.

CHARTS:
23. When the user asks to visualize, chart, plot, compare, show trends, or
    uses words like "show me", "compare", or "over time", ALWAYS create an Altair chart.
    Use `alt` (already imported). Store the chart in the variable `CHART`.
    Example:
    ```
    CHART = alt.Chart(df).mark_line().encode(
        x='Year:O', y='Value:Q', color='Category:N'
    ).properties(title='My Chart', width=700, height=400)
    ```
    You can set both RESULT (for a data table) AND CHART (for a visualization).
    Make charts presentation-quality: use .properties(title=..., width=700, height=400),
    appropriate mark types (mark_line for trends, mark_bar for comparisons, mark_point
    for scatter), clear axis labels, and a clean color scheme.
21. CHART SIZE LIMIT: Altair has a 5000-row limit. If the DataFrame has more than
    4000 rows, ALWAYS aggregate or sample before charting:
    ```
    chart_df = df.groupby('Year').agg(...).reset_index()  # preferred: aggregate
    # or: chart_df = df.sample(n=4000, random_state=42) if aggregation is not possible
    ```

EMPTY RESULTS (CRITICAL):
25. ALWAYS check if your filtered DataFrame is empty BEFORE computing results:
    ```
    if df_filtered.empty:
        RESULT = ("No data found matching the filter criteria. "
                  f"Searched column '{col}' for value '{val}'. "
                  f"Available values are: {actual_values[:10]}")
    ```
    If the result is empty, explain what was searched, what filters were applied,
    and what values ARE available so the user can refine their question.

ANALYSIS QUALITY:
26. BE ANALYTICAL, NOT A DATA DUMP. Never just load and display raw DataFrames.
    Always compute something meaningful: aggregations, rankings, correlations, comparisons.
    - For "correlation" or "relationship" questions: compute the actual Pearson/Spearman
      correlation coefficient, merge the datasets at county level, and create a scatter
      plot with trend line. Set RESULT to a text summary with the r-value and interpretation.
    - For "which has the highest/lowest" questions: compute the answer and show a ranked table.
    - For "compare X and Y" questions: create a side-by-side chart AND a summary table.
    - Always include context: sample sizes, time periods, caveats about data quality.

ADVISORY & RECOMMENDATION QUESTIONS:
27. When the user asks for RECOMMENDATIONS, ADVICE, or SUGGESTIONS about which
    datasets to use, how to approach an analysis, or what data is available for a topic:
    - Use `list_datasets()` to discover relevant datasets.
    - Use `describe("dataset_name")` to inspect the most relevant ones.
    - Set RESULT to a DESCRIPTIVE TEXT (string or dict with "text" and "df" keys) that
      includes for EACH recommended dataset:
      a) The dataset name
      b) What it contains (key columns, row count, time range if available)
      c) WHY it is relevant to the user's goal
      d) How the datasets could be combined or used together for the analysis
    - Format the text as a clear, numbered markdown list. Use **bold** for dataset names.
    - Optionally include a summary DataFrame with columns like
      [Dataset, Description, Rows, Key Columns, Relevance].
    - NEVER return just a raw Python list of dataset names. Always explain WHY each
      dataset is useful and HOW it fits the user's goal.

GEOGRAPHY FILTERING (CRITICAL — your code WILL FAIL without this):
28. Many Statistics Canada datasets store province/territory names with appended codes,
    e.g. "Ontario [PR350000000]" or "Canada [000000000]" rather than plain "Ontario".
    ALWAYS use the `match_geo()` helper to resolve geography names:
    ```
    ontario_val = match_geo("dataset_name", "Ontario")
    if not ontario_val:
        RESULT = "'Ontario' not found in this dataset."
    else:
        geo_col = [c for c in info if 'geo' in c.lower()][0]
        df_filtered = df[df[geo_col] == ontario_val]
    ```
    NEVER do exact equality checks like `'Ontario' in df[geo_col].unique()` — this will
    fail on coded values. Always use `match_geo()` instead.

SANDBOX LIMITATIONS:
29. This sandbox CANNOT create, save, or export files (no Word docs, PDFs, PowerPoints,
    Excel files, or images to disk). The functions open(), os, pathlib, and all file I/O
    are blocked. If the user asks to "generate a report", "create a Word document",
    "export to PDF", or similar:
    - Set RESULT to a helpful text explaining that file generation is not supported
      in the sandbox, but offer to produce the analysis content (charts, tables, and
      narrative text) directly in the dashboard instead.
    - Then provide the analytical content inline using RESULT and CHART.
    - Example: RESULT = ("I can't generate Word documents in this sandbox, but here is "
      "the full analysis with charts and narrative that you can copy into your report:")

RESPONSE SCOPE:
30. Keep your code focused and concise. If the user asks to analyze MANY datasets at once
    (e.g., "create charts for all 10 datasets"), focus on the TOP 3 most relevant datasets
    rather than attempting all of them. Processing too many datasets in a single turn will
    cause your code to be truncated. Always tell the user which datasets you covered and
    suggest they ask follow-up questions for the remaining ones.

AVAILABLE DATASETS:
{schema}
"""


class GeminiAgent:
    """Sends questions to Gemini Flash and returns generated pandas code."""

    def __init__(self, api_key: str, registry: DataRegistry):
        self.api_key = api_key
        self.registry = registry
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _build_system_prompt(self) -> str:
        """Build the system prompt with current year and schema."""
        schema_text = self.registry.build_schema_prompt()
        # Use .replace() instead of .format() to avoid conflicts with
        # curly braces in code examples within the prompt template.
        return (_SYSTEM_PROMPT
                .replace("{schema}", schema_text)
                .replace("{current_year}", str(_dt.date.today().year)))

    def ask(self, question: str, conversation: list[dict] | None = None) -> str:
        """Send question to Gemini and return the generated pandas code."""
        client = self._get_client()
        system = self._build_system_prompt()

        # Build messages — Gemini uses "user" and "model" roles
        contents = []
        if conversation:
            for msg in conversation[-6:]:  # Keep last 6 messages for context
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}],
                })

        contents.append({
            "role": "user",
            "parts": [{"text": (
                f"Question: {question}\n\n"
                f"The current year is {_dt.date.today().year}. "
                "Write Python code to answer this question using the available datasets. "
                "If the question asks for recommendations, advice, or suggestions about "
                "which datasets to use, set RESULT to a detailed text explanation with "
                "dataset names, descriptions, and rationale — not just a raw list. "
                "pd, np, datetime, and CURRENT_YEAR are already imported — do NOT import them. "
                "IMPORTANT: Do NOT hardcode long column names. Use df.columns[i] or "
                "df.filter(like='keyword') to reference columns safely. "
                "For time-series questions, always filter to the requested year range "
                "using CURRENT_YEAR as reference. "
                "Remember to store the final answer in RESULT. "
                "Return ONLY the Python code, no markdown fences or explanations."
            )}],
        })

        code = self._call_gemini(client, system, contents)

        # Auto-retry on SyntaxError: re-ask with error feedback
        try:
            compile(code, "<ai_check>", "exec")
        except SyntaxError as e:
            # Add error feedback and retry once
            contents.append({
                "role": "model",
                "parts": [{"text": code}],
            })
            contents.append({
                "role": "user",
                "parts": [{"text": (
                    f"The code above has a SyntaxError: {e}\n"
                    "Please fix the code. Remember: NEVER hardcode long column names. "
                    "Use df.columns[i] or [c for c in df.columns if 'keyword' in c.lower()][0] "
                    "to reference columns safely. Return ONLY the fixed Python code."
                )}],
            })
            code = self._call_gemini(client, system, contents)

        return code

    def ask_fix(self, original_code: str, error_msg: str,
                conversation: list[dict] | None = None) -> str:
        """Re-ask Gemini to fix code that caused a runtime error."""
        client = self._get_client()
        system = self._build_system_prompt()

        contents = []
        if conversation:
            for msg in conversation[-4:]:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}],
                })

        contents.append({
            "role": "model",
            "parts": [{"text": original_code}],
        })
        contents.append({
            "role": "user",
            "parts": [{"text": (
                f"The code above produced a runtime error:\n{error_msg}\n\n"
                "Please fix the code. Common issues:\n"
                "- After merging DataFrames, column names may have suffixes. "
                "Use suffixes=('', '_drop') and filter out '_drop' columns.\n"
                "- NEVER reference a column name without verifying it exists "
                "in df.columns.\n"
                "- For time-series data, use CURRENT_YEAR (already available) "
                "to determine date ranges. 'Last N years' = CURRENT_YEAR - N.\n"
                "- If charting >4000 rows, aggregate or sample first.\n"
                "Return ONLY the fixed Python code."
            )}],
        })

        return self._call_gemini(client, system, contents)

    def _call_gemini(self, client, system: str, contents: list) -> str:
        """Make a Gemini API call with retry on transient errors."""
        last_err = None
        for attempt in range(_MAX_API_RETRIES):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config={
                        "system_instruction": system,
                        "temperature": 0.1,
                        "max_output_tokens": 8192,
                    },
                )

                code = response.text.strip()

                # Strip markdown code fences if present
                if code.startswith("```"):
                    lines = code.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    code = "\n".join(lines)

                return code

            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                # Retry on transient API errors (503 / 429)
                if any(err_code in err_str for err_code in (
                    "503", "429", "unavailable",
                    "resource_exhausted", "overloaded",
                )):
                    delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                    log.warning("Gemini API error (attempt %d/%d), retrying in %ds: %s",
                                attempt + 1, _MAX_API_RETRIES, delay, e)
                    time.sleep(delay)
                    continue
                # Non-transient error — raise immediately
                raise

        # All retries exhausted
        raise GeminiAPIError(
            "The AI service is temporarily unavailable. "
            "Please try again in a minute."
        ) from last_err


# ════════════════════════════════════════════════════════
#  RATE LIMITER
# ════════════════════════════════════════════════════════

class RateLimiter:
    """Simple daily query counter stored in Streamlit session state."""

    def __init__(self, daily_cap: int = DAILY_QUERY_CAP):
        self.daily_cap = daily_cap

    def check(self, session_state) -> tuple[bool, int]:
        """Return (allowed, remaining) queries."""
        today = _dt.date.today().isoformat()
        if session_state.get("_ai_date") != today:
            session_state["_ai_date"] = today
            session_state["_ai_count"] = 0

        count = session_state.get("_ai_count", 0)
        remaining = max(0, self.daily_cap - count)
        return remaining > 0, remaining

    def increment(self, session_state):
        session_state["_ai_count"] = session_state.get("_ai_count", 0) + 1
