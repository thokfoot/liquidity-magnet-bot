import pandas as pd

from config import MONTH_CODES
from engine import _price_at, _bars_from, SLIP
from params import friction_calc, get_lot, get_step, ensure_meta

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
RUN_DATES = [str(d.date()) for d in SPOTS["NIFTY"]["date"].unique()
             if pd.Timestamp("2026-08-03") <= d <= pd.Timestamp("2026-09-08")]
EXPIRY = pd.Timestamp("2026-09-29")

SL_PCT, TP_PCT = 0.25, 0.40
ENTRY_T, EXIT_T = "09:25:00", "15:15:00"
SPOT_OPEN_T, SPOT_DIR_T = "09:15:00", "09:30:00"


def load_opt(symbol, cache):
    if symbol in cache:
        return cache[symbol]
    return None


def scan_leg(bars, entry_px):
    sl_price = entry_px * (1 + SL_PCT)
    tp_price = entry_px * (1 - TP_PCT)
    last_px, reason = entry_px, "EOD"
    for _, row in bars.iterrows():
        last_px = float(row["close"])
        if last_px >= sl_price:
            reason = "SL"; break
        if last_px <= tp_price:
            reason = "TP"; break
    return last_px, reason


def trade_leg(opt_df, spot_df, date, strike, side):
    sym = f"NSE:{MONTH_CODES['NIFTY']}{strike}{side}"
    df = load_opt(sym, CACHE)
    if df is None:
        return None
    bars = _bars_from(df, date, ENTRY_T, EXIT_T)
    if bars.empty:
        return None
    entry_px = float(bars.iloc[0]["close"])
    if entry_px <= 0:
        return None
    exit_px, reason = scan_leg(bars.iloc[1:], entry_px)
    lot = get_lot("NIFTY")
    pnl = (entry_px - exit_px) * lot
    fr = friction_calc(entry_px, exit_px, lot, sell_side=True) + (SLIP(entry_px) + SLIP(exit_px)) * lot
    return {"entry": entry_px, "exit": exit_px, "reason": reason, "net": pnl - fr, "fr": fr}


def run_window(strategy, label):
    rows = []
    spot_n = SPOTS["NIFTY"].sort_values("datetime")
    for d in RUN_DATES:
        spot_entry = _price_at(spot_n, d, ENTRY_T)
        if spot_entry is None:
            continue
        step = get_step("NIFTY")
        atm = int(round(spot_entry / step) * step)
        if strategy == "otm":
            legs = [("CE", atm + 150), ("PE", atm - 150)]
            res = {}
            for side, st in legs:
                r = trade_leg(None, None, d, st, side)
                if r:
                    res[side] = r
            if len(res) < 2:
                continue
            net = res["CE"]["net"] + res["PE"]["net"]
            fr = res["CE"]["fr"] + res["PE"]["fr"]
            rows.append({"date": d, "spot": round(spot_entry, 1), "strikes": f"{atm-150}/{atm+150}",
                         "ce_reason": res["CE"]["reason"], "pe_reason": res["PE"]["reason"],
                         "net": round(net, 2), "fr": round(fr, 2)})
        elif strategy == "trend":
            o = _price_at(spot_n, d, SPOT_OPEN_T)
            t = _price_at(spot_n, d, SPOT_DIR_T)
            if o is None or t is None:
                continue
            move = (t - o) / o
            res = {}
            if move > 0.001:      # up -> sell PE only
                r = trade_leg(None, None, d, atm, "PE")
                if r: res["PE"] = r
            elif move < -0.001:   # down -> sell CE only
                r = trade_leg(None, None, d, atm, "CE")
                if r: res["CE"] = r
            else:                 # sideways -> both
                rc = trade_leg(None, None, d, atm, "CE")
                rp = trade_leg(None, None, d, atm, "PE")
                if rc: res["CE"] = rc
                if rp: res["PE"] = rp
            if not res:
                continue
            net = sum(r["net"] for r in res.values())
            fr = sum(r["fr"] for r in res.values())
            legs = "+".join(res.keys())
            rows.append({"date": d, "spot": round(spot_entry, 1), "legs": legs,
                         "reason": "/".join(r["reason"] for r in res.values()),
                         "net": round(net, 2), "fr": round(fr, 2)})
    df = pd.DataFrame(rows)
    wins = df[df["net"] > 0]
    losses = df[df["net"] <= 0]
    tot_fr = df["fr"].sum()
    print(f"\n=== {label}: {len(df)} days ===")
    print(f"NET PnL  : {df['net'].sum():>12,.2f}")
    print(f"friction : {tot_fr:>12,.2f}  (avg {tot_fr/len(df):,.0f}/day)")
    print(f"win rate : {100*len(wins)/len(df):.1f}%  ({len(wins)}w/{len(losses)}l)")
    print(f"worst day: {df['net'].min():>12,.2f}   best day: {df['net'].max():>12,.2f}")
    with pd.option_context("display.width", 150):
        print(df.to_string(index=False))
    return df


def main():
    global CACHE
    from engine import load_index_cache
    CACHE = load_index_cache("NIFTY")
    run_window("otm", "OTM STRANGLE (+/-150) with honest friction")
    run_window("trend", "TREND FILTER (first-15-min direction) with honest friction")


if __name__ == "__main__":
    main()