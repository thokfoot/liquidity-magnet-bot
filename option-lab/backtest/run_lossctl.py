import pandas as pd
from engine import load_index_cache, _price_at
import run_sweep as rs

rs.SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")

ENTRY, EXIT, OFF = "09:25:00", "15:15:00", 100
TP = 0.75
SLS = [0.20, 0.25, 0.30, 0.35]
SKIPS = [0.0, 0.0015, 0.0020, 0.0025, 0.0030]


def daily(index, sl):
    rs.CACHE = load_index_cache(index)
    sw = rs.Sweep(index)
    out = {}
    for d in sw.days:
        r = sw.day(d, ENTRY, EXIT, "none", OFF, sl, TP)
        o = _price_at(sw.spot_n, d, "09:15:00")
        t = _price_at(sw.spot_n, d, "09:30:00")
        rng = abs(t - o) / o if o and t else None
        out[d] = (None if r is None else r["net"], rng)
    return out


def evaluate(index, sl, skip_thr, breaker=False):
    d = daily(index, sl)
    nets = []
    prev_lost = False
    for day in sorted(d):
        net, rng = d[day]
        if net is None:
            continue
        if skip_thr and rng is not None and rng > skip_thr:
            continue
        if breaker and prev_lost:
            prev_lost = False
            continue
        nets.append(net)
        prev_lost = net < 0
    s = pd.Series(nets)
    return len(s), s.sum(), 100 * (s > 0).mean(), s.min(), (s[s < 0]).abs().sum()


print(f"Loss-control scan | recipe off±100 SL? TP@25%decay EOD | BN & NIFTY | {OFF} step100\n")
for index in ["BANKNIFTY", "NIFTY"]:
    print(f"== {index} ==")
    print(f"  {'variant':<26}{'days':>5}{'net':>10}{'wr':>5}{'worst':>9}{'sum(neg)':>9}")
    for sl in SLS:
        for skip_thr in SKIPS:
            for breaker in ([False] if skip_thr else [False, True]):
                n, net, wr, w, neg = evaluate(index, sl, skip_thr, breaker)
                lbl = f"SL{int(sl*100)}% / no-skip"
                if skip_thr:
                    lbl = f"SL{int(sl*100)}% / skip>{skip_thr*100:.2f}%"
                if breaker:
                    lbl += " +loss-break"
                print(f"  {lbl:<26}{n:>5}{net:>10,.0f}{wr:>4.0f}%{w:>9,.0f}{neg:>9,.0f}")
    print()