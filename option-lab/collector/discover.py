"""Expiry & symbol discovery from the cached Fyers master (NSE_FO.csv)."""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime, timezone

from . import config as C

_OPT_RE = re.compile(r"^(?:NSE:|BSE:)?([A-Z]+)(\d{2}[A-Z]{3})(\d+)(CE|PE)$")


def _read_master(path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for i, cols in enumerate(reader):
            if i == 0 or len(cols) < 18:
                continue
            if cols[16] not in ("CE", "PE"):
                continue
            sym = cols[9]
            m = _OPT_RE.match(sym)
            if not m:
                continue
            rows.append({
                "index_raw": m.group(1),
                "expiry_code": m.group(2),
                "expiry_epoch": int(cols[8]),
                "strike": int(m.group(3)),
                "itype": m.group(4),
                "symbol": sym,
                "lot": int(cols[3]) if cols[3] else 0,
            })
    return rows


def parse_symbol(sym: str) -> dict | None:
    m = _OPT_RE.match(sym)
    if not m:
        return None
    return {"index_raw": m.group(1), "expiry_code": m.group(2),
            "strike": int(m.group(3)), "itype": m.group(4)}


def discover(master_nse: str | None = None) -> dict:
    """Return {index: {expiries: [(epoch, expiry_code)], step, lot}}."""
    import pathlib

    p = pathlib.Path(master_nse or str(C.MASTER_NSE))
    rows = _read_master(p) if p.exists() else []

    by_index: dict[str, dict] = {}
    # map Fyers index_raw (NIFTY, NIFTYBANK, ...) -> our canonical names
    canon = {"NIFTY": "NIFTY", "NIFTYBANK": "BANKNIFTY", "BANKNIFTY": "BANKNIFTY",
             "FINNIFTY": "FINNIFTY", "MIDCPNIFTY": "MIDCPNIFTY"}
    now_s = datetime.now(timezone.utc).timestamp()

    index2symbol_prefix = defaultdict(set)
    strike_steps: dict[str, list[int]] = defaultdict(list)
    lots: dict[str, list[int]] = defaultdict(list)

    for r in rows:
        name = canon.get(r["index_raw"])
        if not name:
            continue
        index2symbol_prefix[name].add(r["expiry_code"])
        strike_steps[name].append(r["strike"])
        lots[name].append(r["lot"])

    for name, prefixes in index2symbol_prefix.items():
        exps = []
        for code in prefixes:
            # expiry epoch: recover from any symbol row of that code
            epoch = None
            for r in rows:
                if canon.get(r["index_raw"]) == name and r["expiry_code"] == code:
                    epoch = r["expiry_epoch"]
                    break
            if epoch is None or epoch < now_s:
                continue
            exps.append((epoch, code))
        exps.sort()
        steps = sorted(set(strike_steps[name]))
        step = min((b - a for a, b in zip(steps, steps[1:]) if b - a > 0), default=C.STRIKE_STEP.get(name, 50))
        lot = C.LOT_SIZE.get(name)
        if lots[name]:
            from statistics import mode
            lot = mode(lots[name])
        by_index[name] = {"expiries": exps, "step": step, "lot": lot}
    return by_index


def month_code(epoch: int) -> str:
    """Fyers month code for an expiry epoch, e.g. 2026-09-29 -> '26SEP'."""
    import datetime as dt
    d = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).astimezone()
    monos = "JANFEBMARAPRMAYJUNJULAUGSEPOCTNOVDEC"
    try:
        return f"{str(d.year)[-2:]}{monos[(d.month - 1) * 3:(d.month - 1) * 3 + 3]}"
    except Exception:  # noqa: BLE001
        return f"{str(d.year)[-2:]}XXX"


def live_expiry_codes(api, index: str, spot_symbol: str, master: dict | None = None) -> list[tuple[int, str, str]]:
    """Discover the live expiry universe from the chain endpoint (incl. weeklies).

    Returns [(epoch, month_code, 'W'|'M')] sorted by epoch. Falls back to the
    (possibly stale) master list with flag 'M' if the chain call fails.
    """
    m = master or {}
    near_epoch = None
    exps = m.get(index, {}).get("expiries") if m else None
    if exps:
        near_epoch = exps[0][0]
    out = []
    if near_epoch:
        chain = api.optionchain(spot_symbol, near_epoch, 4)
        eds = ((chain or {}).get("expiryData")) or []
        if eds:
            now_s = datetime.now(timezone.utc).timestamp()
            seen = set()
            for ed in eds:
                ep = int(ed["expiry"])
                if ep <= now_s or ep in seen:
                    continue
                seen.add(ep)
                out.append((ep, month_code(ep), ed.get("expiry_flag") or "M"))
            out.sort(key=lambda x: x[0])
    if not out:
        for ep, code in [e for e in ((m or {}).get(index, {}).get("expiries") or [])[:8]]:
            out.append((ep, code, "M"))
    return out