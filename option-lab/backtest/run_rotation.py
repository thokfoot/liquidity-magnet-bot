import pandas as pd
from engine import load_index_cache

RS = None  # module import guard


def setup():
    import run_sweep as rs
    rs.SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
    return rs


def main():
    rs = setup()
    ENTRY, EXIT, OFF, SL, TP = "09:25:00", "15:15:00", 100, 0.35, 0.75
    pool = ["NIFTY", "BANKNIFTY"]
    sws = {}
    for idx in pool:
        rs.CACHE = load_index_cache(idx)
        sws[idx] = rs.Sweep(idx)

    days = sorted(set(sws["NIFTY"].days))
    rows = []
    for d in days:
        nets, credits, calm, prev = {}, {}, {}, {}
        for idx in pool:
            sw = sws[idx]
            if d not in sw.days:
                nets[idx] = None
                continue
            r = sw.day(d, ENTRY, EXIT, "none", OFF, SL, TP)
            if r is None:
                nets[idx] = None
                continue
            nets[idx] = r["net"]
            # combined entry premium (credit) at the two legs
            c = sw._series(d, ENTRY, EXIT, OFF, "CE")
            p = sw._series(d, ENTRY, EXIT, OFF, "PE")
            credits[idx] = (c[0] + p[0]) if c and p else None
            o = rs._price_at(sw.spot_n, d, "09:15:00")
            t = rs._price_at(sw.spot_n, d, "09:30:00")
            calm[idx] = abs(t - o) / o if o and t else None
        active = {i: nets[i] for i in pool if nets[i] is not None}
        if not active:
            continue
        # candidate rules (all computable at 09:25-09:30, no lookahead)
        pick_prem = max(credits, key=lambda i: credits[i] if credits.get(i) is not None else -1) if any(credits.get(i) is not None for i in pool) else None
        pick_calm = min(calm, key=lambda i: calm[i] if calm.get(i) is not None else 9) if any(calm.get(i) is not None for i in pool) else None
        pick_prev = None
        if rows:
            idx_last = rows[-1]["pick_prem"]
            if idx_last in nets and nets[idx_last] is not None and nets[idx_last] > 0:
                pick_prev = idx_last
        pick_upper = max(active, key=lambda i: active[i])   # lookahead ceiling (not tradable)
        rows.append({
            "date": d,
            "premium_NIFTY": round(credits.get("NIFTY") or 0, 1),
            "premium_BN": round(credits.get("BANKNIFTY") or 0, 1),
            "net_NIFTY": round(nets.get("NIFTY") or 0, 2),
            "net_BANKNIFTY": round(nets.get("BANKNIFTY") or 0, 2),
            "pick_prem": pick_prem, "pick_calm": pick_calm,
            "pick_prev": pick_prev, "pick_upper": pick_upper,
        })

    df = pd.DataFrame(rows)

    def eval_rule(col):
        d = df[df[col].notna()]
        nets = [df.iloc[i][f"net_{x}"] for i, x in enumerate(d[col])]
        s = pd.Series(nets)
        return s.sum(), 100 * (s > 0).mean(), s.min()

    def always(idx):
        s = df[f"net_{idx}"]
        return s.sum(), 100 * (s > 0).mean(), s.min()

    print(f"Multi-index rotation pool {pool} | recipe off±{OFF} SL{SL} TP@25%decay EOD | {len(df)} days (dead-zone skipped in per-index runs)\n")
    for name, fn in [("ALWAYS NIFTY  ", lambda: always("NIFTY")),
                     ("ALWAYS BNFIT  ", lambda: always("BANKNIFTY")),
                     ("RULE max-premi", lambda: eval_rule("pick_prem")),
                     ("RULE calmest  ", lambda: eval_rule("pick_calm")),
                     ("RULE prev-winn", lambda: eval_rule("pick_prev")),
                     ("UPPER best-of ", lambda: eval_rule("pick_upper"))]:
        net, wr, worst = fn()
        print(f"{name}  net={net:>9,.0f}  wr={wr:.0f}%  worst={worst:>8,.0f}")

    with pd.option_context("display.width", 150):
        print("\ndaily (rule columns = chosen index):")
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()