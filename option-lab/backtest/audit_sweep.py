import pandas as pd
import run_sweep as rs
from engine import load_index_cache

rs.SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
rs.CACHE = load_index_cache("NIFTY")
CACHE = rs.CACHE
sw = Sweep("NIFTY") if False else rs.Sweep("NIFTY")
print("filter direction per day:")
for d in sw.days:
    mm = sw._dir(d, "move_010")
    vw = sw._dir(d, "vwap_010")
    nn = sw._dir(d, "none")
    print(f"{d}  move={str(mm):>4}  vwap={str(vw):>4}  none={str(nn)}")

print("\n--- top config daily (entry 09:25 exit 15:15 vwap_010 off100 sl0.35 tp0.75) ---")
rows = []
for d in sw.days:
    r = sw.day(d, "09:25:00", "15:15:00", "vwap_010", 100, 0.35, 0.75)
    if r:
        rows.append(r)
df = pd.DataFrame(rows)
with pd.option_context("display.width", 120):
    print(df.to_string(index=False))
print("sum", df['net'].sum())