import itertools
import numpy as np
import pandas as pd

from config import MONTH_CODES
from engine import _price_at, _bars_from, SLIP, load_index_cache
from params import friction_calc, get_lot, get_step, ensure_meta

ensure_meta()
EXPIRY = pd.Timestamp("2026-09-29")
LOT = None

ENTRY_TS = ["09:25:00", "09:35:00", "09:45:00"]
EXIT_TS = ["15:00:00", "15:15:00"]
FILTER = ["none", "move_005", "move_010", "move_020", "vwap_010"]
OFFS = [0, 50, 100, 150]
SLS = [0.15, 0.25, 0.35]
TPS = [None, 0.50, 0.75]
OP = "09:15:00"


def dte_sessions(dstr, spot_n):
    d = pd.Timestamp(dstr)
    return len([x for x in spot_n["date"].unique() if d < x < EXPIRY])


class Sweep:
    def __init__(self, index):
        self.index = index
        self.lot = get_lot(index)
        self.cache = dict(CACHE)          # snapshot THIS index's cache
        self.mc = MONTH_CODES[index]
        self.step = get_step(index)
        self.spot_n = SPOTS[index].sort_values("datetime").reset_index(drop=True)
        self.days = sorted(str(x.date()) for x in self.spot_n["date"].unique()
                           if pd.Timestamp("2026-08-03") <= x <= pd.Timestamp("2026-09-08"))
        self.dfs = {}   # (symbol) -> df
        self.nscan = {} # (date, entry_t, exit_t, off, side) -> numpy closes after entry

    def _df(self, sym):
        df = self.dfs.get(sym)
        if df is None:
            df = self.cache.get(sym)
            self.dfs[sym] = df
        return df

    def _series(self, d, entry_t, exit_t, off, side):
        """closes AFTER the entry bar, for strike = spot@entry (rounded) +- off."""
        key = (d, entry_t, exit_t, off, side)
        if key in self.nscan:
            return self.nscan[key]
        spot = _price_at(self.spot_n, d, entry_t)
        atm = int(round(spot / self.step) * self.step)
        st = atm + (off if side == "CE" else -off)
        sym = f"NSE:{self.mc}{st}{side}"
        df = self._df(sym)
        if df is None:
            self.nscan[key] = None
            return None
        bars = _bars_from(df, d, entry_t, exit_t)
        if len(bars) < 2:
            self.nscan[key] = None
            return None
        e0 = float(bars.iloc[0]["close"])
        if e0 <= 0:
            self.nscan[key] = None
            return None
        c = np.asarray(bars["close"].iloc[1:], dtype=float)
        self.nscan[key] = (e0, c)
        return self.nscan[key]

    def _side_pnl(self, e0, closes, sl, tp):
        sl_px = e0 * (1 + sl)
        out = e0
        reason = "EOD"
        if closes.size:
            sl_hit = np.where(closes >= sl_px)[0]
            tp_px = e0 * tp if tp else None
            tp_hit = np.where(closes <= tp_px)[0] if tp_px else np.array([], dtype=int)
            ev = -1
            if sl_hit.size and tp_hit.size:
                ev = int(min(sl_hit[0], tp_hit[0]))
            elif sl_hit.size:
                ev = int(sl_hit[0]); reason = "SL"
            elif tp_hit.size:
                ev = int(tp_hit[0]); reason = "TP"
            if ev >= 0:
                out = float(closes[ev])
                if reason != "SL":
                    reason = "TP"
            else:
                out = float(closes[-1])
        net = (e0 - out) * self.lot
        net -= friction_calc(e0, out, self.lot, sell_side=True) + (SLIP(e0) + SLIP(out)) * self.lot
        return net, reason

    def _dir(self, d, flt):
        if flt == "none":
            return None
        o = _price_at(self.spot_n, d, OP)
        t = _price_at(self.spot_n, d, "09:30:00")
        if o is None or t is None:
            return None
        if flt.startswith("move"):
            thr = float(flt.split("_")[1]) / 1000.0
            mv = (t - o) / o
            return "PE" if mv > thr else ("CE" if mv < -thr else None)
        sub = self.spot_n[self.spot_n["date"] == pd.Timestamp(d)]
        v = sub[sub["time"] <= "09:30:00"]
        if v.empty or v["volume"].sum() <= 0:
            return None
        vwap = float(((v["high"] + v["low"] + v["close"]) / 3 * v["volume"]).sum() / v["volume"].sum())
        rel = (o - vwap) / vwap
        return "CE" if rel > 0.001 else ("PE" if rel < -0.001 else None)

    def day(self, d, entry_t, exit_t, flt, off, sl, tp):
        dte = dte_sessions(d, self.spot_n)
        if 6 <= dte <= 8:
            return None
        near = dte <= 5
        side = None if near else self._dir(d, flt)
        res = {}
        ok = True
        if near or side is None:
            s_ce = self._series(d, entry_t, exit_t, off, "CE")
            s_pe = self._series(d, entry_t, exit_t, off, "PE")
            if s_ce: res["CE"] = self._side_pnl(*s_ce, sl, tp)
            if s_pe: res["PE"] = self._side_pnl(*s_pe, sl, tp)
        else:
            s = self._series(d, entry_t, exit_t, 0, side)
            if s: res[side] = self._side_pnl(*s, sl, tp)
        if not res:
            return None
        net = sum(x[0] for x in res.values())
        reason = "/".join(x[1] for x in res.values())
        return {"date": d, "dte": dte, "net": round(net, 2), "reason": reason,
                "legs": "+".join(res.keys())}


def sweep(index):
    sw = Sweep(index)
    rows = []
    for (entry_t, exit_t, flt, off, sl, tp) in itertools.product(ENTRY_TS, EXIT_TS, FILTER, OFFS, SLS, TPS):
        nets = []
        reasons = []
        for d in sw.days:
            r = sw.day(d, entry_t, exit_t, flt, off, sl, tp)
            if r:
                nets.append(r["net"]); reasons.append(r)
        if not nets:
            continue
        a = np.array(nets)
        wins = int((a > 0).sum())
        rows.append({"entry": entry_t, "exit": exit_t, "flt": flt, "off": off,
                     "sl": sl, "tp": tp, "net": round(a.sum(), 2), "days": len(a),
                     "wr": round(100.0 * wins / len(a), 1), "worst": round(a.min(), 2),
                     "best": round(a.max(), 2), "sl_days": sum(1 for x in reasons if "SL" in x["reason"])})
    return pd.DataFrame(rows).sort_values("net", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
    CACHE = load_index_cache("NIFTY")
    print("Sweep NIFTY: entry x exit x filter x off x SL x TP ->", len(ENTRY_TS)*len(EXIT_TS)*len(FILTER)*len(OFFS)*len(SLS)*len(TPS), "configs")
    r = sweep("NIFTY")
    print("\nTOP 20 BY NET:")
    with pd.option_context("display.width", 160):
        print(r.head(20).to_string(index=False))
    r.to_csv(r"C:\Dev\Dev\Trading\option-lab\results\sweep_all.csv", index=False)
    print("saved results/sweep_all.csv")