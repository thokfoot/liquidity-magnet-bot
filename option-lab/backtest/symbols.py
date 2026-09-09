import csv
import json
import re
import datetime

import pandas as pd

from config import MASTER_NSE, MASTER_BSE, MONTH_CODES, LOT_SIZE, STRIKE_STEP

_OPT_RE = re.compile(r"^(?:NSE:|BSE:)?([A-Z]+)(\d{6}|\d{2}[A-Z]{3})(\d+)(CE|PE)$")


def parse_fy_symbol(symbol):
    m = _OPT_RE.match(symbol)
    if not m:
        return None
    return {"index_raw": m.group(1), "expiry_code": m.group(2),
            "strike": int(m.group(3)), "itype": m.group(4)}


def read_master(path, exchange):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, c in enumerate(reader):
            if i == 0:
                continue
            if len(c) >= 18 and c[16] in ("CE", "PE"):
                try:
                    rows.append({
                        "name": c[1],
                        "expiry_epoch": int(c[8]),
                        "symbol": c[9],
                        "exchange": exchange,
                        "underlying": c[13],
                        "itype": c[16],
                        "lot": int(c[3]) if c[3] else 0,
                    })
                except (ValueError, IndexError):
                    continue
    return pd.DataFrame(rows)


def load_masters():
    nse = read_master(MASTER_NSE, "NSE")
    bse = read_master(MASTER_BSE, "BSE")
    return pd.concat([nse, bse], ignore_index=True)


def derive_lot_and_step(master):
    for name in MONTH_CODES:
        sub = master[(master["underlying"] == name) & (master["itype"].isin(["CE", "PE"]))]
        if len(sub) == 0:
            continue
        LOT_SIZE[name] = int(sub["lot"].mode().iloc[0]) if len(sub) else 0
        strikes = set()
        for sym in sub["symbol"].unique():
            p = parse_fy_symbol(sym)
            if p:
                strikes.add(p["strike"])
        strikes = sorted(strikes)
        diffs = set()
        for a, b in zip(strikes, strikes[1:]):
            if b - a > 0:
                diffs.add(b - a)
        STRIKE_STEP[name] = min(diffs) if diffs else 50
    return dict(LOT_SIZE), dict(STRIKE_STEP)


def build_calendar(master):
    idx = master[master["itype"].isin(["CE", "PE"])].copy()
    rows = []
    for (ul, ep), g in idx.groupby(["underlying", "expiry_epoch"]):
        rows.append({
            "index": ul,
            "expiry": pd.Timestamp(ep, unit="s"),
            "expiry_epoch": ep,
        })
    cal = pd.DataFrame(rows).drop_duplicates().sort_values(["index", "expiry"]).reset_index(drop=True)
    return cal


def build_symbols(index, strikes, expire_code=None):
    """Return list of Fyers symbols: {code}<strike>CE/PE for given strikes."""
    code = expire_code or MONTH_CODES[index]
    syms = []
    for st in strikes:
        syms.append(f"NSE:{code}{st}CE")
        syms.append(f"NSE:{code}{st}PE")
    return syms


def parse_symbol_expiry(symbol):
    """Extract (index, yymmdd OR monthcode, strike, itype) from a Fyers option symbol."""
    # patterns: NIFTY26SEP23800CE or NIFTY26091519150CE
    body = symbol.split(":")[-1]
    if body[:3] in ("NIF", "BAN", "FIN", "MID"):
        index = {"NIF": "NIFTY", "BAN": "BANKNIFTY", "FIN": "FINNIFTY", "MID": "MIDCPNIFTY"}[body[:3]]
    else:
        index = "BANKNIFTY" if "BANK" in body[:8] else "NIFTY"
    if len(body) >= 7 and body[7:10] in ("SEP", "OCT", "NOV", "DEC", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG"):
        code = body[len(index):].rstrip("CE").rstrip("PE")
        rest = code[6:]
        strike = rest if rest else 0
    return index, body


if __name__ == "__main__":
    m = load_masters()
    print(dict(derive_lot_and_step(m)))
    cal = build_calendar(m)
    for ix in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]:
        sub = cal[cal["index"] == ix]
        print(ix, len(sub), sub["expiry"].dt.date.tolist()[:6])
    cal.to_parquet(r"C:\Dev\Dev\Trading\option-lab\data\expiry_calendar.parquet")
    print("calendar saved")