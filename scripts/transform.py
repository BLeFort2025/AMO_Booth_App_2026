import pandas as pd
import yaml
from pathlib import Path

from scripts.fetch_statcan import ensure_year_column

DATA_LATEST = Path("data/latest")
TABLES_YML = Path("config/tables.yml")

def standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    if "REF_DATE" in df.columns:
        df["YEAR"] = df["REF_DATE"].astype(str).str.slice(0,4).astype(int)
    if "GEO" in df.columns:
        df["GEO"] = df["GEO"].astype(str).str.strip()
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
    return df

def load(table_id: str) -> pd.DataFrame:
    return pd.read_csv(DATA_LATEST / f"{table_id}.csv", low_memory=False)


def apply_table_transforms() -> None:
    """Apply table-level transforms driven by tables.yml configuration.

    Currently supports an optional `latest_only` flag per table. When set to True,
    the transformation trims the dataset down to the most recent YEAR value. By
    default, all available years are kept.
    """

    cfg = yaml.safe_load(TABLES_YML.read_text())
    tables = cfg.get("tables", cfg)

    for table_cfg in tables:
        if not table_cfg.get("active", True):
            continue

        table_id = table_cfg["id"]
        csv_name = table_cfg.get("csv") or f"{table_id}.csv"
        final_path = DATA_LATEST / csv_name

        if not final_path.exists():
            continue

        latest_only = bool(table_cfg.get("latest_only", False))

        df = pd.read_csv(final_path, low_memory=False)
        original = df.copy()
        df = ensure_year_column(df)

        if latest_only and "YEAR" in df.columns:
            max_year = df["YEAR"].dropna().max()
            df = df[df["YEAR"] == max_year]

        # Only rewrite the file if the content changed (either YEAR added or filtered)
        if not df.equals(original):
            df.to_csv(final_path, index=False)

def compute_ceag_profitability():
    # CEAG Revenues + Expenses => NOI, Margin
    rev = standardize(load("32-10-0240-01"))
    exp = standardize(load("32-10-0241-01"))
    keys = ["GEO","YEAR"]
    merged = (rev.assign(REV=rev["VALUE"])[keys+["REV"]]
                .merge(exp.assign(EXP=exp["VALUE"])[keys+["EXP"]], on=keys, how="inner"))
    merged["NET_OP_INCOME"] = merged["REV"] - merged["EXP"]
    merged["PROFIT_MARGIN"] = merged["NET_OP_INCOME"] / merged["REV"]
    out = merged[keys + ["REV","EXP","NET_OP_INCOME","PROFIT_MARGIN"]]
    out.to_csv(DATA_LATEST / "ceag_profitability_cd.csv", index=False)

def compute_ceag_direct_sales_share():
    # Direct sales as share of operating revenues (same GEO,YEAR)
    try:
        ds = standardize(load("32-10-0242-01"))
        rev = standardize(load("32-10-0240-01"))
    except FileNotFoundError:
        return
    keys = ["GEO","YEAR"]
    merged = (ds.assign(DIRECT_SALES=ds["VALUE"])[keys+["DIRECT_SALES"]]
                .merge(rev.assign(REV=rev["VALUE"])[keys+["REV"]], on=keys, how="inner"))
    merged["DIRECT_SALES_SHARE"] = merged["DIRECT_SALES"] / merged["REV"]
    merged[keys + ["DIRECT_SALES","REV","DIRECT_SALES_SHARE"]].to_csv(
        DATA_LATEST / "ceag_direct_sales_share_cd.csv", index=False
    )

def run():
    # Run all transformations that depend on fetched sources
    apply_table_transforms()

    # CEAG derived metrics
    try:
        compute_ceag_profitability()
        compute_ceag_direct_sales_share()
        print("Derived CEAG metrics written.")
    except FileNotFoundError:
        print("CEAG source files not found yet; run fetch first.")

    # NEW: IO multipliers + SUT subset
    try:
        from scripts.io_multipliers_transform import run as io_run
        io_run()
        print("Derived IO multipliers assets written.")
    except FileNotFoundError:
        print("IO source files not found yet; run fetch_io_tables.py or pipeline fetch first.")
    except Exception as e:
        print(f"[WARN] IO transforms failed (non-fatal): {e}")

if __name__ == "__main__":
    run()
