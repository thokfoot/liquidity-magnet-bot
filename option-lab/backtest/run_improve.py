import pandas as pd

from config import MONTH_CODES
from engine import _price_at, _bars_from, SLIP, load_index_cache
from params import friction_calc, get_lot, get_step, ensure_meta

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
CACHE = load_index_cache("NIFTY")
EXPIRY = pd.Timestamp("2026-09-29")
SL_PCT = 0.25
EXIT_T = "15:15:00"
OP = "09:15:00"
MOVE_T = "09:30:00"
LOT = get_lot("NIFTY")
STEP = get_step("NIFTY")


def dte_sessions(dstr):
    d = pd.Timestamp(dstr)
    return len([x for x in SPOTS["NIFTY"]["date"].unique() if d < x < EXPIRY])


def scan(bars, e):
    sl = e * (1 + SL_PCT)
    x, r = e, "EOD"
    for _, row in bars.iterrows():
        x = float(row["close"])
        if x >= sl:
            r = "SL"; break
    return x, r


def leg(sym, d, entry_t):
    df = CACHE.get(sym)
    if df is None: return None
    bars = _bars_from(df, d, entry_t, EXIT_T)
    if bars.empty: return None
    e = float(bars.iloc[0]["close"])
    if e <= 0: return None
    x, r = scan(bars.iloc[1:], e)
    net = (e - x) * LOT - friction_calc(e, x, LOT, sell_side=True) - (SLIP(e) + SLIP(x)) * LOT
    return {"e": e, "net": net, "reason": r}


def vwap_upto(df, t_str):
    sub = df[df["time"] <= t_str]
    if sub.empty or sub["volume"].sum() <= 0: return None
    tp = (sub["high"] + sub["low"] + sub["close"]) / 3
    return float((tp * sub["volume"]).sum() / sub["volume"].sum())


def day_run(d, filter_type, entry_t, r2_off):
    spot_n = SPOTS["NIFTY"].sort_values("datetime")
    dte = dte_sessions(d)
    near = dte <= 5
    if 6 <= dte <= 8:
        return None
    spot = _price_at(spot_n, d, entry_t)
    if spot is None: return None
    atm = int(round(spot / STEP) * STEP)

    side = None
    if not near:
        if filter_type == "move":        # first-15-min move
            o = _price_at(spot_n, d, OP); t = _price_at(spot_n, d, MOVE_T)
            if o is None or t is None: return None
            mv = (t - o) / o
            side = "PE" if mv > 0.001 else ("CE" if mv < -0.001 else None)
        else:                            # VWAP at 09:30 vs 09:15 close
            o = _price_at(spot_n, d, OP)
            v = vwap_upto(spot_n[spot_n["date"] == pd.Timestamp(d)], MOVE_T)
            if o is None or v is None: return None
            rel = (o - v) / v
            side = "CE" if rel > 0.001 else ("PE" if rel < -0.001 else None)

    res = {}
    if near or side is None:
        st = atm + r2_off
        c = leg(f"NSE:{MONTH_CODES['NIFTY']}{st}CE", d, entry_t)
        pm = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm - r2_off}PE", d, entry_t)
        if c: res["CE"] = c
        if pm: res["PE"] = pm
    else:
        r = leg(f"NSE:{MONTH_CODES['NIFTY']}{atm}{side}", d, entry_t)
        if r: res[side] = r
    if not res: return None
    return {"date": d, "dte": dte, "near": near, "legs": "+".join(res.keys()),
            "net": round(sum(x["net"] for x in res.values()), 2),
            "reason": "/".join(x["reason"] for x in res.values())}


def run(filter_type, entry_t, r2_off, label):
    spot_n = SPOTS["NIFTY"].sort_values("datetime")
    rows = []
    for d in sorted(str(x.date()) for x in spot_n["date"].unique()):
        if not (pd.Timestamp("2026-08-03") <= pd.Timestamp(d) <= pd.Timestamp("2026-09-08")):
            continue
        r = day_run(d, filter_type, entry_t, r2_off)
        if r: rows.append(r)
    df = pd.DataFrame(rows)
    w = df[df["net"] > 0]; l_ = df[df["net"] <= 0]
    print(f"{label:<34} net={df['net'].sum():>9,.0f}  wr={100*len(w)/len(df):>3.0f}% "
          f"({len(w)}w/{len(l_)}l) worst={df['net'].min():>8,.0f}  24d?{len(df)}")
    return df


if __name__ == "__main__":
    print("NIFTY 27d | SL25% | EOD 15:15 | honest friction\n")
    base = run("move", "09:25:00", 0, "BASE 2-REGIME (verified)")
    run("move", "09:45:00", 0, "R1 entry 09:45 (more confirm)")
    run("vwap", "09:25:00", 0, "R1 filter = VWAP@09:30")
    run("move", "09:25:00", 100, "R2 near strangle OTM +-100")
    run("vwap", "09:25:00", 100, "R1 VWAP + R2 OTM +-100")
    print()
    print("--- best candidate daily ---")
    best = run("vwap", "09:25:00", 100, "candidate")
    with pd.option_context("display.width", 120):
        print(best.to_string(index=False))