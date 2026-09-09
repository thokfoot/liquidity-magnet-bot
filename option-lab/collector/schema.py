"""Schema & storage paths (local mirror + GCS object names), idempotent writes.

Layout (both local DATA_ROOT and GCS bucket mirror):
    spot/{index}/{date}.parquet                    1-min spot bars  (hist-upgraded)
    opts/{index}/{date}/{expiry}_{CE|PE}_{strike}.parquet   1-min option bars
    chain/{index}/{date}.parquet                   full-chain OI/LTP snapshots
    meta/{date}.json                               run manifest (symbols, expiries, source)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from . import config as C  # noqa: PLR2004 - values pulled from env

OPT_COLUMNS = ["ts", "open", "high", "low", "close", "vol", "oi", "n"]
SPOT_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "source"]
CHAIN_COLUMNS = ["ts", "expiry", "strike", "ce_ltp", "ce_oi", "ce_vol", "pe_ltp", "pe_oi", "pe_vol"]


def _today() -> str:
    return datetime.now(timezone.utc).astimezone().date().strftime("%Y-%m-%d")


def local(root: Path, day: str, kind: str, index: str = "", *parts: str) -> Path:
    """Build a local path under DATA_ROOT for a (kind, index, day) artifact."""
    segs = [root]
    if kind == "spot":
        segs += ["spot", index, f"{day}.parquet"]
    elif kind == "opts":
        segs += ["opts", index, day, *parts]
    elif kind == "chain":
        segs += ["chain", index, f"{day}.parquet"]
    elif kind == "meta":
        segs += ["meta", (parts[0] if parts else f"{day}.json")]
    else:
        raise ValueError(kind)
    return Path(*segs)


def gcs_object(day: str, kind: str, index: str = "", *parts: str) -> str:
    """Mirror object name in the bucket (no bucket prefix)."""
    if kind == "spot":
        return f"spot/{index}/{day}.parquet"
    if kind == "opts":
        return f"opts/{index}/{day}/{'/'.join(parts)}"
    if kind == "chain":
        return f"chain/{index}/{day}.parquet"
    if kind == "meta":
        return f"meta/{parts[0] if parts else day}.json"
    raise ValueError(kind)


# ---------------------------------------------------------------- writers
def write_frame(path: Path, df: pd.DataFrame, drop_key: str) -> int:
    """Upsert a frame into parquet: merge on key, dedupe, keep sorted. Returns rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df = df.sort_values(drop_key).drop_duplicates(drop_key, keep="last")
    if path.exists():
        old = pd.read_parquet(path)
        df = pd.concat([old, df], ignore_index=True)
    df = df.sort_values(drop_key).drop_duplicates(drop_key, keep="last")
    df.to_parquet(path, index=False)
    return len(df)


def append_jsonl(path: Path, rows: list[dict]) -> int:
    """Append raw JSON lines (chain snapshots can be high-cardinality)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")
    return len(rows)


def write_meta(day: str, payload: dict) -> None:
    p = local(C.DATA_ROOT, day, "meta")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def read_day_parquet(day: str, kind: str, index: str = "") -> pd.DataFrame | None:
    p = local(C.DATA_ROOT, day, kind, index)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def recent_days(n: int = 30) -> list[str]:
    """Last ``n`` UTC calendar days for manifests (UTC-safe, collector(-agnostic))."""
    today = _today()
    base = pd.Timestamp(today)
    return [(base - pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)][::-1]