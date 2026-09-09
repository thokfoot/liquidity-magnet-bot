import json
import os
import pandas as pd

from config import RESULTS_DIR


def print_summary(title, s):
    if s is None:
        print(f"{title}: NO DATA")
        return
    print(f"\n=== {title} ===")
    print(f"  Days       : {s['days']}  (win {s['win_days']} / loss {s['loss_days']}, {s['win_rate']}%)")
    print(f"  Net PnL    : Rs{s['net_pnl']:,.2f}")
    print(f"  Avg / day  : Rs{s['avg_pnl']:,.2f}")
    print(f"  ProfitFctr : {s['profit_factor']}")
    print(f"  Worst day  : Rs{s['worst_day']:,.2f}   Best day Rs{s['best_day']:,.2f}")
    print(f"  SL-hit days: {s['sl_hit_days']}   Avg prem Rs{s['avg_premium']:,.2f}")


def save_json(name, payload):
    path = os.path.join(RESULTS_DIR, name)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"[saved] {path}")
    return path


def daily_table(results):
    return pd.DataFrame(results)[["date", "ce_entry", "pe_entry", "ce_reason",
                                  "pe_reason", "net_pnl", "spot_entry", "atm_strike"]]