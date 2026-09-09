import pandas as pd

from config import MONTH_CODES
from engine import _price_at, _bars_from, SLIP, load_index_cache
from params import friction_calc, get_lot, get_step, ensure_meta

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
CACHE = load_index_cache("NIFTY")
EXPIRY = pd.Timestamp("2026-09-29")
SL_PCT = 0.25
ENTRY_T, EXIT_T = "09:25:00", "15:15:00"
OP, DT = "09:15:00", "09:30:00"


def dte_sessions(dstr):
    d = pd.Timestamp(dstr)
    return len([x for x in SPOTS["NIFTY"]["date"].unique() if d < x < EXPIRY])


class Side:
    """One condor side: short leg (ATM) + long wing (offset)."""
    def __init__(self, d, atm, side, w):
        self.side = side
        sym_s = f"NSE:{MONTH_CODES['NIFTY']}{atm}{side}"
        sym_w = f"NSE:{MONTH_CODES['NIFTY']}{atm + (w if side == 'CE' else -w)}{side}"
        self.short = CACHE.get(sym_s)
        self.wing = CACHE.get(sym_w)
        self.valid = self.short is not None and self.wing is not None
        self.d = d

    def run(self):
        lot = get_lot("NIFTY")
        bs = _bars_from(self.short, self.d, ENTRY_T, EXIT_T)
        bw = _bars_from(self.wing, self.d, ENTRY_T, EXIT_T)
        if bs.empty or bw.empty:
            return None
        S0 = float(bs.iloc[0]["close"])
        W0 = float(bw.iloc[0]["close"])
        if S0 <= 0 or W0 < 0:
            return None
        sl_price = S0 * (1 + SL_PCT)
        Sx = float(bs.iloc[-1]["close"])
        Wx = float(bw.iloc[-1]["close"])
        reason = "EOD"
        for _, r in bs.iloc[1:].iterrows():
            c = float(r["close"])
            if c >= sl_price:
                Sx = c
                t = r["datetime"]
                m = bw["datetime"] <= t
                Wx = float(bw[m].iloc[-1]["close"]) if m.any() else Wx
                reason = "SL"
                break
        credit = S0 - W0
        pnl_short = (S0 - Sx) * lot
        pnl_wing = (Wx - W0) * lot
        fr_s = friction_calc(S0, Sx, lot, sell_side=True) + (SLIP(S0) + SLIP(Sx)) * lot
        fr_w = friction_calc(W0, Wx, lot, sell_side=False) + (SLIP(W0) + SLIP(Wx)) * lot
        return {"credit": credit, "net": pnl_short + pnl_wing - fr_s - fr_w, "reason": reason}


def day_ic(d, w):
    spot = _price_at(SPOTS["NIFTY"].sort_values("datetime"), d, ENTRY_T)
    if spot is None:
        return None
    atm = int(round(spot / get_step("NIFTY")) * get_step("NIFTY"))
    dte = dte_sessions(d)
    if 6 <= dte <= 8:          # dead zone
        return {"date": d, "dte": dte, "regime": "SKIP", "net": 0.0, "credit": 0.0, "reason": ""}
    near = dte <= 5
    o = _price_at(SPOTS["NIFTY"].sort_values("datetime"), d, OP)
    t = _price_at(SPOTS["NIFTY"].sort_values("datetime"), d, DT)
    if o is None or t is None:
        return None
    mv = (t - o) / o
    up = mv > 0.001
    down = mv < -0.001

    sides = {}
    if near or (not up and not down):
        ce = Side(d, atm, "CE", w); pe = Side(d, atm, "PE", w)
        if ce.valid: sides["CE"] = ce
        if pe.valid: sides["PE"] = pe
    elif up:
        pe = Side(d, atm, "PE", w)
        if pe.valid: sides["PE"] = pe
    elif down:
        ce = Side(d, atm, "CE", w)
        if ce.valid: sides["CE"] = ce

    res = {}
    for k, s in sides.items():
        r = s.run()
        if r: res[k] = r
    if not res:
        return {"date": d, "dte": dte, "regime": "NODATA", "net": 0.0, "credit": 0.0, "reason": ""}
    net = sum(r["net"] for r in res.values())
    credit = sum(r["credit"] for r in res.values())
    reason = "/".join(r["reason"] for r in res.values())
    wings = "+".join(res.keys())
    return {"date": d, "dte": dte, "regime": wings, "net": round(net, 2),
            "credit": round(credit, 2), "reason": reason}


def main():
    lot = get_lot("NIFTY")
    print("IRON CONDOR (short ATM + bought wings)   |  NIFTY lot 65 | SL25% on shorts, EOD 15:15")
    print("R1 far-DTE: trendfilter (put/call spread)  R2 near: condor  Dead-zone DTE 6-8: SKIP")
    spot_n = SPOTS["NIFTY"].sort_values("datetime")
    days = sorted(str(x.date()) for x in spot_n["date"].unique()
                  if pd.Timestamp("2026-08-03") <= x <= pd.Timestamp("2026-09-08"))
    for w in [100, 150, 200]:
        rows = []
        for d in days:
            r = day_ic(d, w)
            if r: rows.append(r)
        df = pd.DataFrame(rows)
        traded = df[df["net"] != 0]
        wins = traded[traded["net"] > 0]
        max_margin_each = max(((w - r["credit"]) * lot if r["net"] != 0 else 0) for _, r in df.iterrows())
        total_credit = df[df["credit"] > 0]["credit"].sum() * lot
        print(f"\n===== width (wing distance) = {w} =====")
        print(f"traded days : {len(traded)}  (skipped deadzone {len(df)-len(traded)})")
        print(f"NET PnL     : {traded['net'].sum():>10,.2f}")
        print(f"win rate    : {100*len(wins)/len(traded):.0f}%  ({len(wins)}w/{len(traded)-len(wins)}l)")
        print(f"worst day   : {traded['net'].min():>10,.2f}    best: {traded['net'].max():>10,.2f}")
        print(f"premiums collected: {total_credit:>10,.0f}")
        print(f"approx margin 1 lot (max vertical, {w} wide x65) : {max_margin_each:>10,.0f}")
        print(f"net ROI on Rs 50k : {100*traded['net'].sum()/50000:>6.1f}%")
        if w == 100:
            print("\n--- width 100 daily ---")
            with pd.option_context("display.width", 120):
                print(df.to_string(index=False))


if __name__ == "__main__":
    main()