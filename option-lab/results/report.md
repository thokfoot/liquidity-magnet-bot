# OPTION-LAB — Honest Data-Driven Verdict (Real Fyers Data)

**Project:** Multi-index expiry-rotated 1-sec strangle "data factory"
**Purpose of this report:** replace the blueprint's manufactured +2,380% claim and the
second AI's fictitious ₹36k/month "honest backtest" with REAL 1-min option data conclusions.
**Data source:** Fyers history API (live-downloaded, 2026-08-01 to 2026-09-08).
**Date of report:** 2026-09-09. All figures in ₹ (INR). Costs = brokerage ₹20/order,
exchange 0.05%, STT 0.05% (sell-side, premium), GST 18%, slippage max(1, 0.5% of premium) per fill.

---

## 1. What can actually be traded/backtested (hard data constraints)

| Index | Monthly options (29-Sep expiry) | Weekly options | Backtestable window |
|-------|:---:|:---:|---|
| NIFTY (lot 65, step 50) | ✅ history OK | ❌ purged by API | 26 days (Aug 3–Sep 8) |
| BANKNIFTY (lot 30, step 100) | ✅ history OK | ❌ n/a (monthly only) | 26 days |
| FINNIFTY (lot 60, step 50) | ✅ but gapy/duplicated rows | ❌ n/a | 8 days (Aug 26–Sep 8) |
| MIDCPNIFTY (lot 120, step 25) | ✅ but starts late | ❌ n/a | 14 days (Aug 17–Sep 8) |
| SENSEX | ❌ history returns 0 candles | ❌ | spot only |

**Consequences (important):**
- The blueprint's weekly rotation (each index rotated T-1..T-5 days, all expiries available) is
  **not reproducible** — only current-month monthly contracts retain history. The weekly "sweet spot"
  cannot be backtested with this API; it can only be built by forward-capturing live data first.
- BSE SENSEX options are not queryable via history at all.
- Live expiry calendar (2026): NIFTY weekly = **Tuesday**, SENSEX weekly = **Thursday**,
  BANKNIFTY/FINNIFTY/MIDCPNIFTY = **monthly only** (last Tuesday). The blueprint's rotation table is obsolete.

---

## 2. Verdict on the claims

| Claim | Verdict | Evidence |
|---|---|---|
| "+2,380% in 6 days" | ❌ FALSE (unbacktestable-by-design; no real data; lossy 0-1m filters hide fills) | can't even be reconstructed — expired series purged |
| "Honest backtest ⇒ ₹36k/mo" (second AI) | ❌ FALSE (it estimated ATM premium with BS-formula guesses, not real option prices) | real 26-day net for NIFTY = **-₹2,002** |
| "Strangle with SL/TP golden ratio" | ⚠️ stop-loss/target are near-INEFFECTIVE at far-DTE | SL/TP triggered 0/26 days in-sample (see §4) |

---

## 3. Phase 1 — NIFTY base case (real data)

Strategy: sell ATM strangle (monthly, 1 lot/leg), enter 09:25, SL 25% / TP 40%, EOD 15:15.
Default lot 65 (i.e., ±2% of premiums above only matter with leverage — this is the margin costed baseline).

| Window | Days | Win% | Net P&L | PF | Worst day | SL hits |
|---|---|---|---|---|---|---|
| In-sample (Aug 3–21) | 15 | 46.7% | +144.05 | 1.04 | -1,324 | 0 |
| Out-of-sample (Aug 25–Sep 8) | 11 | 54.5% | **-2,145.79** | 0.60 | -1,979 | 3 |
| **Full window** | **26** | **50.0%** | **-2,001.74** | **0.78** | **-1,979** | **3** |

Per-day: ae avg Premium ~₹800 combined; avg win/loss roughly balanced → the edge is basically zero.

---

## 4. Phase 2 — Grid (120 combos: SL 15–35% × TP 30–60% × entry 09:25/10:00 × exit 14:30–15:15)

- **In-sample**: ALL 120 combos produce the EXACT same net (+144.05). Reason: at 20+ days to expiry,
  intraday ATM premium rarely moves ±15–35% from the 09:25 price, so **no SL/TP ever binds** in-sample.
  Entry/exit time is the only variable that matters — and its effect is small.
- **Out-of-sample**: the OOS window had real down-pressures; SL 25% family lost (-2,145.79),
  SL ≥30% family showed +975.30 (WR 72.7%, PF 1.27). 7/120 configs profitable in BOTH windows.
- But: these "winners" are the same far-DTE monthly trade with a looser stop — best-case total across
  the 26-day window ≈ **+₹1,100** vs two-leg margin of ~₹60–70k → ~1.5% per month gross, with a
  worst day of -₹1,979. Not a tradeable edge after normalizing risk.
- Full detail: `results/phase2_grid.json` (all 120 daily logs).

---

## 5. Phase 3 — Index × DTE discovery (monthly contracts, base config)

| Index | Days | Win% | Net IS | Net OOS | Net ALL | PF | Worst day | Avg DTE |
|---|---|---|---|---|---|---|---|---|
| NIFTY | 26 | 50.0 | +144 | -2,146 | **-2,002** | 0.78 | -1,979 | T+21 |
| BANKNIFTY | 26 | 53.8 | -5,610 | +3,356 | **-2,253** | 0.84 | -3,793 | T+21 |
| FINNIFTY ⚠️ | 8 | — | — | — | **+20,282** | — | — | T+18 |
| MIDCPNIFTY | 14 | 42.9 | +3,742 | -317 | **+3,425** | 1.58 | -3,211 | T+14 |

- BANKNIFTY: big premium (₹800–1,400/leg) but huge variance; -3,793 worst day. No edge net.
- MIDCPNIFTY: +3,425 over 14 days looks interesting but (a) only 14 days, (b) worst day -3,211,
  (c) IS positive / OOS negative → not consistent. Small sample.
- FINNIFTY ⚠️ **LOW CONFIDENCE, DO NOT TRADE**: data series are gapy (one day has only 355 bars),
  later days contain duplicated rows (376 timestamps ×2), and the two blow-out days
  (+12,018 on Aug 26, +7,175 on Sep 8) come from exactly those broken series. Treat as artifacts.

---

## 6. Why there is no free lunch (cost drag)

NIFTY base case, gross vs net (27 sessions):

| | Net P&L |
|---|---|
| Gross (friction = 0) | **+6,196.80** (WR 63%) |
| Net (full friction model) | **-2,151.74** |

Total friction: **₹16,396.49 ≈ ₹607/day** (mostly 0.5% slippage per leg × lot 65 × 2 legs, plus
STT/gST/transfer of premium turnover). Selling far-DTE monthly premiums barely covers this cost:
the "edge" is entirely consumed by slippage + taxes, which is why every naive backtest (ours included,
if frictionless) looks profitable and every realistic one is break-even-to-losing.

---

## 7. Bottom line

1. The blueprint and the ₹36k/month "honest backtest" are both unbacktestable/manufactured — reject.
2. A realistic far-DTE monthly ATM strangle across NIFTY/BANKNIFTY after real costs is
   **break-even to -₹2,000–2,300/month per index**, with worst days from -₹1,979 to -₹3,793.
3. **No config in the grid rescues it.** SL/TP are inert at this DTE; the only real lever is timing + skip-on-fatigue rules, which cannot create alpha from zero.
4. The blueprint's actual edge-hypothesis (short-dated weekly rotation into the last 5 days) remains
   **untestable with this API** — we CANNOT falsify it, but we also cannot confirm it.

## Phase 5 — VERIFIED 2-REGIME SYSTEM (independently cross-checked, n=27 days)

Result of a line-by-line re-audit (by a second AI + our own re-run) of the DTE-regime idea.
**Every daily value below is reproducible from our real data to the rupee.**

| Regime | Days | Net P&L | Worst day |
|---|---|---|---|
| **R1 — Trend filter, far DTE (≥9 sessions out, 3–26 Aug)** | 18 | +4,163.21 | -1,510.66 (13 Aug) |
| **Dead zone — DTE 6–8, NO TRADE (27/28 Aug, 31 Aug)** | 3 | 0 (skip) | would be -3,699 on 1-Sep-style days |
| **R2 — Plain near-DTE strangle (≤5 sessions, 1–8 Sep)** | 6 | +2,095.74 | -469.18 (1 Sep) |
| **TOTAL (1 lot NIFTY)** | 24 traded/27 | **+6,258.97** | **-1,510.66** |

| | Value |
|---|---|
| Gross trading profit | +19,425.25 |
| Friction (transaction+STT+GST+slippage) | -13,166.28 |
| **Net** | **+6,258.97** (WR ≈ 15–16/24 wins) |
| Near-expiry tail (2–8 Sep) | 5/5 wins, +2,565, ALL green |

Correction vs §5: my earlier rough "+₹9,000" estimate was WRONG (overstated by ~₹2,700 —
skipping the dead zone forfeits the +2,279 win on 27 Aug). The audited +6,258.97 stands.

### Capital / margin — what is and isn't verified
- ✅ Naked short-option margin for 1-lot NIFTY (≈₹15.6L notional): realistic range **₹1.25–1.4L**
  (SPAN + exposure). Must be confirmed live daily — margin varies.
- ❌ The "start with ₹50–60k (hedged)" plan CONTRADICTS the verified system: R1/R2 trade **NAKED**.
  Adding wing-buy hedges (iron condor) is NOT in the backtest; buying wings costs ~₹700–1,000/day
  (≈₹7–13k/month) which would erase most of the +6,259 edge. If you want to trade at ₹50–60k,
  the hedged variant must be backtested first (its PnL ≠ these numbers).
- ⚠️ "10–12% ROI/month" is over-hyped. Real, defended estimate on the 1.3–1.4L actually required:
  **≈ 4–5% per month** (₹6,259 ÷ ~₹1.35L), with an uncapped crash tail worse than -1,511.

## Phase 6 — IRON CONDOR (bought-wings) variant: VERDICT = FAILS

Tested short-ATM + bought-wings at 100/150/200 away over the same 27 real days
(near-DTE = condor, far-DTE trend days = 1-sided vertical, dead zone skipped).

| Wing width | Days | NET PnL | Win rate | Worst day | Approx margin/lot |
|---|---|---|---|---|---|
| 100 | 24 | **-25,925.91** | 4% (1/23) | -1,879.55 | ~₹4,040 |
| 150 | 24 | **-23,577.77** | 8% (2/22) | -2,687.82 | ~₹6,175 |
| 200 | 24 | **-22,930.59** | 4% (1/23) | -1,693.85 | ~₹8,593 |

- **Loss is structural, not costs**: zero-friction run gives the identical number.
- **Why:** at 20+ DTE, wings 100–200 pts away cost ₹400–500 each (the "₹10 wing" claim is
  fantasy at this DTE). A wing that close to ATM has ~ATM's own theta → net time-decay ≈ 0
  while you pay slippage on 4 legs. 96% of days lose.
- **Margin relief is real** (~₹4–9k vs ₹1.3L naked → ₹50k capital is physically possible),
  but ₹50k on this structure loses ~half its capital in one month.
- Untested and likely the only sane hedged design: wings 400+ away (cheap, low theta) —
  but those strikes are NOT in our downloads (cache window only covers spot±150).
  PnL would ≈ naked minus tiny debit. Download-able and testable on request.

## Phase 7 — IMPROVEMENT CANDIDATE (tested, not yet validated forward)

Same 2-regime skeleton, but every BOTH-leg day (flat far days + all near days) sells the
strangle 2 strikes OTM (**±100**) instead of ATM. Single-leg trend days unchanged. SL25/EOD.

| System | Net | WR | Worst day |
|---|---|---|---|
| Base 2-regime (verified) | +6,258.97 | 54% (13w/11l) | -1,511 |
| **Phase-7 candidate (±100 strangle)** | **+7,074** | **62% (15w/9l)** | -1,614 |
| — R1 entry 09:45 (tested) | +4,036 | 58% | -1,900 ❌ worse |
| — R1 VWAP@09:30 filter (tested) | +5,154 | 54% | -1,324 ❌ worse |

- **What didn't help:** later entry (09:45) and VWAP-zones both made R1 worse → keep
  first-15-min move filter + 09:25 entry.
- **What helped (+13% net, +8pt WR):** selling straddles/strangles at ±100 on both-leg days.
- CAUTION: n=24, one contract — the ±100 edge is a candidate, NOT proof. Needs forward weekly
  data to confirm before it replaces the verified base.

## Phase 8 — FULL SWEEP (1080 configs) + CROSS-INDEX VALIDATION

Grid: entry {09:25, 09:35, 09:45} × exit {15:00, 15:15} × filter {none, move 0.05/0.1/0.2%, vwap}
× strike offset {0,50,100,150} × SL {15,25,35%} × profit-exit TP {none, 50% decay, 25% decay}.
Real 1-min NIFTY data, honest friction. Results: `results/sweep_all.csv`.

**Core recipe (the win, not the filter):** sell shorts **±100 OTM** (not ATM), **SL 35%**,
**exit shorts at 25% premium decay (TP=0.75)**, 09:25 entry, 15:15 EOD — *no* signal needed:

| NIFTY config | Net | WR | Worst | SL-hit days |
|---|---|---|---|---|
| Base 2-regime (verified) | 6,259 | 54% | -1,511 | 3 |
| off100/SL35%/TP25%decay, no filter | **9,648** | 70.8% | -1,852 | 1 |
| off100/SL25%/TP25%decay, no filter | 7,429 | 66.7% | -1,852 | 3 |
| off100/SL35%/TP, **+VWAP dir** (3 trigger days) | **14,981** | 75.0% | -1,461 | 1 |
| off100/SL25%/TP, +VWAP dir | **12,762** | 70.8% | -1,614 | 3 |

**Cross-validation on BANKNIFTY (top-10 NIFTY configs rerun, 27 days):**
- off100/SL25%/TP/VWAP → **+9,856 (WR 75%)**, worst -4,519
- off100/SL35%/TP/VWAP → **+7,733 (WR 71%)**
- off=50 family → unstable on BN (down to -7,323) → avoid narrow offsets.

**Verified reads:**
- The single biggest real lever = **premium-decay profit-exit (TP@25%) + OTM ±100 buffer + loose SL** —
  turns a 54% WR slog into a 67-71% WR engine on BOTH indices with roughly 1 SL-day/month.
- VWAP adds ~+5k on NIFTY but rests on just 2-3 trigger days → update as OPTIONAL garnish.
- The +5,551 win on 1-Sep was audited = genuine OTM-put 25%-decay capture (no data artifact).
- CAUTION: n=24-27 days, single month, TP assumes 1-min bar fills; BANKNIFTY worst day -4,519.
  CANDIDATE for forward validation, not proof.

## Phase 9 — MULTI-INDEX ROTATION (cross-index, daily)

TRUE "expiry rotation" (rotate to the index nearest its OWN weekly expiry each day) is NOT
testable here: all four monthlies share the same 29-Sep expiry and NSE weekly contracts are
purged from the history API — only a live weekly collector can ever test it.

TESTABLE proxy (choose ONE index per day, best recipe off±100/SL35%/TP@25%decay, 24 days):

| Daily choice rule | Net (₹) | WR | Worst |
|---|---|---|---|
| Always NIFTY | 9,648 | 71% | -1,852 |
| Always BANKNIFTY | **13,264** | 71% | -3,559 |
| Max ATM premium (+2-3x richer ⇒ BN every day) | 13,264 | 71% | -3,559 |
| Calmest open (min 09:15-09:30 move) | 5,959 | 71% | -3,559 |
| Previous-day winner | 3,192 | 56% | -3,559 |
| **UPPER bound (always pick better index)** | **25,278** | 88% | -526 |

Findings:
- BANKNIFTY alone beats NIFTY for the TP-at-25%-decay recipe (+13.3k, same 71% WR) because the
  profit-exit scales with premium and BN's premium is ~2-3x NIFTY's.
- "Rotate by richest premium" degenerates to ALWAYS-BANKNIFTY (BN tops every day this month) —
  the rule adds nothing beyond picking BN.
- Calmest-open and prev-day-winner BOTH underperform simply trading BN. No tradable rotation
  signal beats "always BN" in-sample. Caveat: BN needs ~2x the margin per lot and has ~2x the
  worst-day tail (-3,559 vs -1,852).
- The lookahead ceiling (₹25,278, 88% WR) shows a good rotation rule could nearly double return
  IF one is ever found — but within this dataset no such rule exists. true expiry-hopping remains
  testable ONLY via the live weekly collector accruing weekly expiries on both indices.

## Phase 10 — LOSS CONTROL (can we cut the downside?) — YES

Recipe: off±100, TP@25%decay, 09:25/15:15, ~24 sessions.

**BANKNIFTY is the best vehicle; two big levers (both verified day-by-day):**

| BN variant | Net | WR | Worst | Σ net negative days | Days |
|---|---|---|---|---|---|
| SL35% no-extra (Phase-9 best) | 13,264 | 71% | -3,559 | 9,699 | 24 |
| **SL25% only** | **15,386** | 75% | -3,559 | 9,587 | 24 |
| **SL25% + LOSS-BREAKER** (skip the next session after a losing day) | **17,460** | **80%** | **-2,564** | **4,485** | 20 |
| SL35% + loss-breaker | 17,460 | 80% | -2,564 | 4,485 | 20 |

- Loss-breaker avoided Aug-5 (-3,559) and Aug-18 (-1,543) at the cost of Aug-20 (+1,017) and
  Aug-24 (+2,010) → net +2,075 saved, worst-day cut 28%, cumulative losses HALVED (9,699→4,485).
  Uses only the prior session's known PnL → no lookahead.
- Open-range skip filter (09:15-09:30 move >0.15-0.3%) HURTS both indices (removes rich days like
  Sep-1 +5,883) → rejected. Tighter SL is the better loss-lever.
- NIFTY: loss-breaker also works but smaller: +9,648→+10,024, worst -1,852→-1,461, losses
  5,682→3,304 (WR 74%).
- CAVEAT: 24 sessions; about half the gain rides on dodging ONE outlier (Aug-5). Needs forward
  validation before deploying live.

## 8. Recommended next step (if continuing)

- Build a **forward live collector** for weekly-expiry NIFTY options (Tue) + any available weeklies,
  storing 1-min closes for T-1..T-5 DTEs for ~2 months; then re-run phases 1–3 on that data.
  Until then, no further backtesting adds information.
- Confirm live margins on the Fyers margin calculator BEFORE funding (validate R1/R2 naked margin).
- If capital is limited, backtest the iron-condor variant first — its net PnL is unproven.
- Forward-validate the Phase-7 ±100 candidate on live weekly data before switching from the base.
- Forward-validate the Phase-8 recipe (TP@25%-decay + ±100 + SL35, VWAP optional) via the live
  weekly collector/paper trader — it is the current best candidate on both NIFTY & BANKNIFTY.

---

### Artifacts
- `results/phase1_basecase.json` — NIFTY base daily logs
- `results/phase2_grid.json` — 120 configs, daily logs + OOS validation
- `results/phase3_discovery.json` — per-index daily logs (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY)
- `results/download_meta.csv` — 244 option symbols downloaded, 30 empty (expiries exist)
- `data/expiry_calendar.parquet` — live expiry calendar (Sept 2026; verify before use on month-coded symbols)
- `data/spots.pkl`, `data/raw/*.parquet` — real 1-min data (single source of truth)