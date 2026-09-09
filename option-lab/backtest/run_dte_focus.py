import pandas as pd

from config import MONTH_CODES
from engine import _price_at, _bars_from, SLIP, load_index_cache
from params import friction_calc, get_lot, get_step, ensure_meta

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
CACHE = load_index_cache("NIFTY")
EXPIRY = pd.Timestamp("2026-09-29")
SL_PCT, TP_PCT = 0.25, 0.40
ENTRY_T, EXIT_T = "09:25:00", "15:15:00"
OP, DT = "09:15:00", "09:30:00"


def dte_sessions(dstr):
    d = pd.Timestamp(dstr)
    return len([x for x in SPOTS["NIFTY"]["date"].unique() if d < x < EXPIRY])


def scan(bars, entry_px):
    sl, tp = entry_px * (1 + SL_PCT), entry_px * (1 - TP_PCT)
    last, reason = entry_px, "EOD"
    for _, r in bars.iterrows():
        last = float(r["close"])
        if last >= sl: reason = "SL"; break
        if last <= tp: reason = "TP"; break
    return last, reason


def leg(sym, d, spot_n):
    df = CACHE.get(sym)
    if df is None: return None
    bars = _bars_from(df, d, ENTRY_T, EXIT_T)
    if bars.empty: return None
    e = float(bars.iloc[0]["close"])
    if e <= 0: return None
    x, reason = scan(bars.iloc[1:], e)
    lot = get_lot("NIFTY")
    net = (e - x) * lot - friction_calc(e, x, lot, sell_side=True) - (SLIP(e) + SLIP(x)) * lot
    return {"e": e, "x": x, "r": reason, "net": net}


def day_run(d, spot_n, mode, max_dte=None):
    if max_dte is not None and dte_sessions(d) >= max_dte:
        return None
    spot = _price_at(spot_n, d, ENTRY_T)
    if spot is None: return None
    step = get_step("NIFTY")
    atm = int(round(spot / step) * step)
    res = {}
    if mode == "strangle":
        c = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}CE", d, spot_n)
        p = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}PE", d, spot_n)
        if c: res["CE"] = c
        if p: res["PE"] = p
    else:
        o, t = _price_at(spot_n, d, OP), _price_at(spot_n, d, DT)
        if o is None or t is None: return None
        mv = (t - o) / o
        if mv > 0.001:
            p = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}PE", d, spot_n)
            if p: res["PE"] = p
        elif mv < -0.001:
            c = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}CE", d, spot_n)
            if c: res["CE"] = c
        else:
            c = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}CE", d, spot_n)
            p = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}PE", d, spot_n)
            if c: res["CE"] = c
            if p: res["PE"] = p
    if not res: return None
    return {"date": d, "dte": dte_sessions(d), "net": round(sum(r["net"] for r in res.values()), 2),
            "reason": "/".join(r["r"] for r in res.values())}


def run(mode, max_dte=None):
    spot_n = SPOTS["NIFTY"].sort_values("datetime")
    rows = []
    for d in sorted(str(x.date()) for x in spot_n["date"].unique()):
        if not (pd.Timestamp("2026-08-03") <= pd.Timestamp(d) <= pd.Timestamp("2026-09-08")):
            continue
        r = day_run(d, spot_n, mode, max_dte)
        if r: rows.append(r)
    df = pd.DataFrame(rows)
    w = df[df["net"] > 0]
    l_ = df[df["net"] <= 0]
    print(f"[{mode.upper()}  maxDTE={max_dte}]  days={len(df)}  net={df['net'].sum():>9,.0f}  "
          f"wr={100*len(w)/len(df):.0f}% ({len(w)}w/{len(l_)}l)  worst={df['net'].min():>7,.0f}  "
          f"best={df['net'].max():>7,.0f}")
    return df


if __name__ == "__main__":
    print("NIFTY monthly-29Sep contracts, 09:25 entry / 15:15 exit, SL25/TP40, honest friction")
    for mode in ["strangle", "trend"]:
        for mdt in [None, 8, 5]:
            d = run(mode, mdt)
            if mdt in (5, 8) and mode == "strangle":
                print(d.to_string(index=False))