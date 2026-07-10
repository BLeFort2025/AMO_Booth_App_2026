"""Analytics helpers for time-series visualizations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd


@dataclass
class AnalyticsOptions:
    """Container for chart analytics options."""

    moving_average_window: Optional[int] = None
    show_trendline: bool = False
    chart_mode: str = "level"
    highlight_outliers: bool = False
    index_to_base: bool = False


# ---------- Core computations ----------


def _apply_groupby(
    df: pd.DataFrame, group_cols: Optional[Iterable[str]]
) -> List[tuple[tuple, pd.DataFrame]]:
    """Split dataframe by groups, or return whole dataframe if no grouping needed."""

    if group_cols:
        grouped = []
        for keys, sub_df in df.groupby(list(group_cols)):
            if not isinstance(keys, tuple):
                keys = (keys,)
            grouped.append((keys, sub_df.copy()))
        return grouped
    return [(tuple(), df.copy())]


def compute_moving_average(
    df: pd.DataFrame,
    value_col: str,
    window: int,
    group_cols: Optional[list[str]] = None,
    time_col: str = "YEAR",
) -> pd.DataFrame:
    """Return a copy of df with a moving average column added per group."""

    out_col = f"{value_col}_ma_{window}"
    result_frames: list[pd.DataFrame] = []

    for keys, sub_df in _apply_groupby(df, group_cols):
        ordered = sub_df.sort_values(time_col)
        ordered[out_col] = (
            ordered[value_col].rolling(window=window, min_periods=1).mean()
        )
        result_frames.append(ordered)

    combined = pd.concat(result_frames, ignore_index=True)
    return combined


def compute_yoy_change(
    df: pd.DataFrame,
    value_col: str,
    group_cols: Optional[list[str]] = None,
    time_col: str = "YEAR",
) -> pd.DataFrame:
    """Return a copy of df with a year-over-year percentage change column added."""

    out_col = f"{value_col}_yoy_pct"
    result_frames: list[pd.DataFrame] = []

    for keys, sub_df in _apply_groupby(df, group_cols):
        ordered = sub_df.sort_values(time_col)
        ordered[out_col] = (
            (ordered[value_col] - ordered[value_col].shift(1))
            / ordered[value_col].shift(1)
            * 100
        )
        result_frames.append(ordered)

    combined = pd.concat(result_frames, ignore_index=True)
    return combined


def compute_linear_trend(
    df: pd.DataFrame,
    value_col: str,
    group_cols: Optional[list[str]] = None,
    time_col: str = "YEAR",
    min_points: int = 3,
) -> pd.DataFrame:
    """Return a copy of df with a linear trendline column added per group."""

    out_col = f"{value_col}_trend"
    result_frames: list[pd.DataFrame] = []

    for keys, sub_df in _apply_groupby(df, group_cols):
        ordered = sub_df.sort_values(time_col)
        x = pd.to_numeric(ordered[time_col], errors="coerce")
        y = pd.to_numeric(ordered[value_col], errors="coerce")
        if x.notna().sum() >= min_points and y.notna().sum() >= min_points:
            coeffs = np.polyfit(x, y, deg=1)
            trend_vals = np.polyval(coeffs, x)
            ordered[out_col] = trend_vals
        else:
            ordered[out_col] = np.nan
        result_frames.append(ordered)

    combined = pd.concat(result_frames, ignore_index=True)
    return combined


def flag_outliers(
    df: pd.DataFrame,
    value_col: str,
    group_cols: list[str],
    time_col: str,
    z_thresh: float = 2.0,
) -> pd.DataFrame:
    """
    Compute YoY % changes per group, measure residuals, and flag points whose
    YoY % change deviates by more than z_thresh standard deviations from the
    mean YoY % change for that series.

    Returns a copy of df with a boolean column 'is_outlier'.
    """

    out = df.copy()
    out["is_outlier"] = False

    if out.empty or value_col not in out.columns or time_col not in out.columns:
        return out

    # Sort by time within each group
    out = out.sort_values(group_cols + [time_col])

    def _flag(group: pd.DataFrame) -> pd.DataFrame:
        g = group.copy()
        g["prev"] = g[value_col].shift(1)
        mask = g["prev"].notna() & (g["prev"] != 0)
        if not mask.any():
            g["is_outlier"] = False
            return g
        yoy = (g.loc[mask, value_col] - g.loc[mask, "prev"]) / g.loc[mask, "prev"]
        mean_yoy = yoy.mean()
        std_yoy = yoy.std()
        if std_yoy == 0 or pd.isna(std_yoy):
            g["is_outlier"] = False
            return g
        z = (yoy - mean_yoy) / std_yoy
        outlier_mask = z.abs() > z_thresh
        g["is_outlier"] = False
        g.loc[mask.index[mask][outlier_mask], "is_outlier"] = True
        return g

    if group_cols:
        out = out.groupby(group_cols, group_keys=False).apply(_flag)
    else:
        out = _flag(out)
    out = out.drop(columns=["prev"], errors="ignore")
    return out

