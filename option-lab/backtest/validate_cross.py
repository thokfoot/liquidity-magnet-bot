import pandas as pd
import run_sweep as rs
from engine import load_index_cache

rs.SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
top = pd.read_csv(r"C:\Dev\Dev\Trading\option-lab\results\sweep_all.csv").head(10)

for idx in ["BANKNIFTY"]:
    rs.CACHE = load_index_cache(idx)
    sw = rs.Sweep(idx)
    print(f"\n===== VALIDATING TOP-10 configs on {idx} ({len(sw.days)} days) =====")
    for _, c in top.iterrows():
        nets = []
        for d in sw.days:
            r = sw.day(d, c["entry"], c["exit"], c["flt"], int(c["off"]), float(c["sl"]),
                       None if pd.isna(c["tp"]) else float(c["tp"]))
            if r:
                nets.append(r["net"])
        a = pd.Series(nets)
        if len(a):
            print(f"{c['flt']:>10} off={int(c['off']):>3} sl={float(c['sl']):.2f} tp={c['tp']!s:>4}"
                  f"  -> {idx} net={a.sum():>9,.0f}  wr={100*(a>0).mean():.0f}%  worst={a.min():>7,.0f}")
        else:
            print(f"{c['flt']:>10} off={int(c['off']):>3} sl={float(c['sl']):.2f} tp={c['tp']!s:>4}  -> NO DATA")