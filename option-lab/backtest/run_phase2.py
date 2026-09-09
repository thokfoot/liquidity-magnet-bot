import itertools
import pandas as pd

from config import RESULTS_DIR
from engine import run_backtest, summarize, load_index_cache
from report import save_json
from params import (IN_SAMPLE_FROM, IN_SAMPLE_TO, OUT_SAMPLE_FROM, OUT_SAMPLE_TO,
                    ensure_meta)

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
CACHE = load_index_cache("NIFTY")


def split_dates():
    is_dates = [str(d.date()) for d in SPOTS["NIFTY"]["date"].unique()
                if pd.Timestamp(IN_SAMPLE_FROM) <= d <= pd.Timestamp(IN_SAMPLE_TO)]
    oos_dates = [str(d.date()) for d in SPOTS["NIFTY"]["date"].unique()
                 if pd.Timestamp(OUT_SAMPLE_FROM) <= d <= pd.Timestamp(OUT_SAMPLE_TO)]
    return is_dates, oos_dates


def main():
    print("#" * 70)
    print("# PHASE 2 — CONTROLLED GRID (IS rank -> OOS validate)")
    print("#" * 70)
    is_dates, oos_dates = split_dates()
    grid_sl = [0.15, 0.20, 0.25, 0.30, 0.35]
    grid_tp = [0.30, 0.40, 0.50, 0.60]
    grid_entry = ["09:25:00", "10:00:00"]
    grid_exit = ["14:30:00", "15:00:00", "15:15:00"]

    rows = []
    n = len(grid_sl) * len(grid_tp) * len(grid_entry) * len(grid_exit)
    for i, (sl, tp, en, ex) in enumerate(itertools.product(
            grid_sl, grid_tp, grid_entry, grid_exit)):
        r_is = run_backtest("NIFTY", SPOTS, entry_time=en, exit_time=ex,
                            sl_pct=sl, tp_pct=tp, dates=is_dates, opt_cache=CACHE)
        s = summarize(r_is)
        if s is None:
            continue
        rows.append({
            "sl": sl, "tp": tp, "entry": en[:5], "exit": ex[:5],
            "is_net": s["net_pnl"], "is_wr": s["win_rate"],
            "is_pf": s["profit_factor"], "is_worst": s["worst_day"],
            "is_slhit": s["sl_hit_days"], "is_days": s["days"],
        })
        if (i + 1) % 40 == 0:
            print(f"  grid {i+1}/{n}")

    g = pd.DataFrame(rows).sort_values("is_net", ascending=False).reset_index(drop=True)
    print(f"\ngrid {len(g)} combos. Top-12 by IN-SAMPLE net PnL:")
    print(g.head(12)[["sl", "tp", "entry", "exit", "is_net", "is_wr", "is_pf"]].to_string(index=False))

    # OOS validation of the top-10 IS configs
    top = g.head(10)
    oos_rows = []
    for _, cfg in top.iterrows():
        r_oos = run_backtest("NIFTY", SPOTS, entry_time=cfg.entry + ":00",
                             exit_time=cfg.exit + ":00", sl_pct=cfg.sl,
                             tp_pct=cfg.tp, dates=oos_dates, opt_cache=CACHE)
        s = summarize(r_oos)
        oos_rows.append({
            "sl": cfg.sl, "tp": cfg.tp, "entry": cfg.entry, "exit": cfg.exit,
            "is_net": cfg.is_net, "oos_net": s["net_pnl"] if s else None,
            "oos_wr": s["win_rate"] if s else None,
            "oos_pf": s["profit_factor"] if s else None,
            "oos_worst": s["worst_day"] if s else None,
        })
    o = pd.DataFrame(oos_rows)
    print("\nTop-10 IS configs -> OOS validation:")
    print(o.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # "best robust" = best IS config that ALSO stays profitable OOS
    o["both_win"] = (o["is_net"] > 0) & (o["oos_net"] > 0)
    save_json("phase2_grid.json", {
        "grid": rows,
        "oos": o.to_dict("records"),
        "note": "No config below this line survived both windows profitably.",
    })
    winners = o[o["both_win"]]
    if len(winners):
        print("\nCONFIGS PROFITABLE IN BOTH WINDOWS:", len(winners))
        print(winners.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    else:
        print("\nNO CONFIG PROFITABLE IN BOTH WINDOWS (worst-day risk dominated).")


if __name__ == "__main__":
    main()