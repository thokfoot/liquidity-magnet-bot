"""Minute-bar aggregator built from quote snapshots + chain snapshots."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pandas as pd


def minute_key(ist_aware_dt: dt.datetime) -> dt.datetime:
    """Floor an aware datetime to its IST minute (naive, IST wall-clock)."""
    local = ist_aware_dt.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    return local.replace(second=0, microsecond=0)


class SnapshotAggregator:
    """Aggregates per-symbol LTP/OI/vol snapshots into 1-min OHLC rows.

    ``push(symbol, ts_aware, ltp, oi, vol)`` repeatedly; ``finalize(before_minute)``
    returns + clears rows for minutes < before_minute. Prices are last-known
    between snapshots (20s cadence); true OHLCV is backfilled by EOD history.
    """

    def __init__(self):
        self._bars: dict[str, dict] = {}      # symbol -> {minute -> stats}
        self._last: dict[str, tuple] = {}      # symbol -> (ltp, oi, vol) carry-over

    def push(self, symbol: str, ts: dt.datetime, ltp: float, oi: float, vol: float) -> None:
        mk = minute_key(ts)
        cur = self._last.get(symbol)
        last_ltp = cur[0] if cur else ltp
        bucket = self._bars.setdefault(symbol, {})
        stat = bucket.get(mk)
        if stat is None:
            stat = {"open": ltp, "high": ltp, "low": ltp, "close": ltp,
                    "oi": oi, "vol": vol, "n": 1, "last_ts": ts}
            bucket[mk] = stat
        else:
            if ltp > stat["high"]:
                stat["high"] = ltp
            if ltp < stat["low"]:
                stat["low"] = ltp
            stat["close"] = ltp
            stat["oi"] = oi
            if vol > 0:
                stat["vol"] = max(stat["vol"], vol)
            stat["n"] += 1
            stat["last_ts"] = ts
        self._last[symbol] = (ltp, oi, vol)
        _ = last_ltp

    def finalize(self, before_minute: dt.datetime) -> pd.DataFrame:
        rows = []
        cut = minute_key(before_minute)
        for symbol, bucket in list(self._bars.items()):
            done = {mk: stats for mk, stats in bucket.items() if mk < cut}
            for mk, s in done.items():
                rows.append({
                    "symbol": symbol, "ts": mk,
                    "open": s["open"], "high": s["high"], "low": s["low"],
                    "close": s["close"], "oi": s["oi"], "vol": s["vol"], "n": s["n"],
                })
                del bucket[mk]
            if not bucket:
                del self._bars[symbol]
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return df.sort_values(["symbol", "ts"])


def chain_df_to_rows(ts: dt.datetime, index: str, chain: dict, expiry_epoch: int | None = None) -> list[dict]:
    """Flatten a v3 option-chain payload into CHAIN rows (whole chain + meta)."""
    rows = []
    mk = minute_key(ts)
    underlying_ltp = vix = None
    by_strike: dict[int, dict] = {}

    for item in (chain or {}).get("optionsChain") or []:
        itype = item.get("option_type") or ""
        if itype in ("CE", "PE"):
            st = int(item["strike_price"])
            by_strike.setdefault(st, {})[itype] = item
        elif itype == "" and item.get("strike_price", -1) == -1:
            underlying_ltp = item.get("ltp")
    vix_d = (chain or {}).get("indiavixData") or {}
    vix = vix_d.get("ltp")
    for st in sorted(by_strike):
        ce, pe = by_strike[st].get("CE"), by_strike[st].get("PE")
        rows.append({
            "ts": mk, "index": index, "expiry": int(expiry_epoch or 0),
            "strike": st,
            "ce_ltp": ce["ltp"] if ce and ce.get("ltp") else None,
            "ce_oi": ce.get("oi") if ce else None,
            "ce_vol": ce.get("volume") if ce else None,
            "pe_ltp": pe["ltp"] if pe and pe.get("ltp") else None,
            "pe_oi": pe.get("oi") if pe else None,
            "pe_vol": pe.get("volume") if pe else None,
            "underlying_ltp": underlying_ltp,
            "vix": vix,
        })
    return rows