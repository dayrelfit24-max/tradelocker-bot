#!/usr/bin/env python3
"""
Signal-to-fill decay analysis.

Answers the question a backtest cannot: between the moment a strategy fires and
the moment money settles, where does the edge go?

It separates four distinct leaks, because they have different fixes:

  1. Blocked      — the signal never became a trade (news filter, risk cap).
                    Invisible to P&L, so a strategy can look better or worse
                    than it is purely from which signals got dropped.
  2. Entry slip   — filled worse than the price the strategy asked for.
  3. Exit quality — where the position actually closed, relative to the stop
                    and target the signal defined. Realized R vs intended R.
  4. Carry        — P&L drift on positions held long enough to accrue swap.

Reads tradelocker_trades.json; no network calls, no side effects.
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

TRADES = Path.home() / "tradelocker-bot" / "tradelocker_trades.json"

# Points-per-unit so slippage is comparable across instruments.
TICK = {"US30": 1.0, "NAS100": 1.0, "BTCUSD": 1.0, "ETHUSD": 1.0,
        "XAUUSD": 0.1, "EURUSD": 0.0001}


def tick_for(sym):
    for k, v in TICK.items():
        if sym.upper().startswith(k):
            return v
    return 1.0


def parse(ts):
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def load():
    if not TRADES.exists():
        sys.exit(f"no trades file at {TRADES}")
    return json.loads(TRADES.read_text())


def fmt(x, w=9, dp=2):
    return f"{x:>{w}.{dp}f}" if isinstance(x, (int, float)) else f"{str(x):>{w}}"


def rule(ch="─", n=78):
    print(ch * n)


def analyze(trades):
    attributed = [t for t in trades if t.get("strategy") not in (None, "unknown")]
    measurable = [t for t in attributed if t.get("signalEntry") is not None]

    print()
    rule("═")
    print("  SIGNAL-TO-FILL DECAY")
    rule("═")
    print(f"  {len(trades):>5} trades total")
    print(f"  {len(attributed):>5} attributed to a strategy")
    print(f"  {len(measurable):>5} with signal-level detail (entry/SL/TP recorded)")

    if not measurable:
        print("\n  No trades yet carry signal detail. This fills in as the bot")
        print("  places trades — each one records the price the strategy asked")
        print("  for alongside the price the broker gave.")
        return

    # ── 1. Entry slippage ──────────────────────────────────────────────────
    print()
    rule()
    print("  ENTRY SLIPPAGE — asked for vs actually filled")
    rule()
    print(f"  {'strategy':<14}{'n':>4}{'avg pts':>10}{'worst':>10}{'avg $':>10}{'total $':>10}")
    rule("·")

    by_strat = defaultdict(list)
    for t in measurable:
        by_strat[t["strategy"]].append(t)

    slip_total = 0.0
    for strat, rows in sorted(by_strat.items()):
        slips, costs = [], []
        for t in rows:
            tk = tick_for(t["symbol"])
            # Positive = filled worse than the signal price.
            raw = t["entry"] - t["signalEntry"]
            if t["direction"] == "Short":
                raw = -raw
            pts = raw / tk
            slips.append(pts)
            costs.append(raw * float(t.get("size") or 0))
        if not slips:
            continue
        avg = sum(slips) / len(slips)
        worst = max(slips)
        cost = sum(costs)
        slip_total += cost
        print(f"  {strat:<14}{len(rows):>4}{fmt(avg,10)}{fmt(worst,10)}"
              f"{fmt(cost/len(rows),10)}{fmt(cost,10)}")
    rule("·")
    print(f"  {'ALL':<14}{len(measurable):>4}{'':>10}{'':>10}{'':>10}{fmt(slip_total,10)}")
    print("\n  Positive = you paid up to get in. This is a pure cost: it applies")
    print("  to every trade regardless of whether the signal was right.")

    # ── 2. Exit quality vs the plan ────────────────────────────────────────
    print()
    rule()
    print("  EXIT QUALITY — where trades actually ended, vs stop and target")
    rule()
    print(f"  {'strategy':<14}{'n':>4}{'→target':>9}{'→stop':>8}{'other':>8}"
          f"{'avg R':>9}{'plan R':>9}{'capture':>9}")
    rule("·")

    for strat, rows in sorted(by_strat.items()):
        hit_tp = hit_sl = other = 0
        realized_r, planned_r = [], []
        for t in rows:
            entry, sl, tp = t["signalEntry"], t["signalSL"], t["signalTP"]
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            if risk <= 0:
                continue
            planned_r.append(reward / risk)

            exit_px = float(t["exit"])
            # Classify the exit by which planned level it landed nearest,
            # with a tolerance of a tenth of the stop distance.
            tol = risk * 0.1
            if abs(exit_px - tp) <= tol:
                hit_tp += 1
            elif abs(exit_px - sl) <= tol:
                hit_sl += 1
            else:
                other += 1

            move = exit_px - entry
            if t["direction"] == "Short":
                move = -move
            realized_r.append(move / risk)

        if not realized_r:
            continue
        avg_r = sum(realized_r) / len(realized_r)
        avg_plan = sum(planned_r) / len(planned_r)
        capture = (avg_r / avg_plan * 100) if avg_plan else 0
        n = len(rows)
        print(f"  {strat:<14}{n:>4}{hit_tp:>9}{hit_sl:>8}{other:>8}"
              f"{fmt(avg_r,9)}{fmt(avg_plan,9)}{fmt(capture,8,0)}%")

    print("\n  'other' = closed somewhere that was neither the stop nor the")
    print("  target. A high count there means the plan is not what governs")
    print("  your exits — something else is closing these positions.")

    # ── 3. Holding time and carry ──────────────────────────────────────────
    print()
    rule()
    print("  HOLDING TIME — where carry cost accrues")
    rule()
    print(f"  {'strategy':<14}{'n':>4}{'median hrs':>12}{'max hrs':>10}{'>24h':>7}{'P&L >24h':>11}")
    rule("·")

    for strat, rows in sorted(by_strat.items()):
        hrs, long_pnl, long_n = [], 0.0, 0
        for t in rows:
            a, b = parse(t.get("date")), parse(t.get("exitTime"))
            if not (a and b):
                continue
            h = (b - a).total_seconds() / 3600
            hrs.append(h)
            if h > 24:
                long_n += 1
                long_pnl += float(t.get("pnl") or 0)
        if not hrs:
            continue
        hrs.sort()
        med = hrs[len(hrs) // 2]
        print(f"  {strat:<14}{len(rows):>4}{fmt(med,12,1)}{fmt(max(hrs),10,1)}"
              f"{long_n:>7}{fmt(long_pnl,11)}")

    # ── 4. Net result per strategy ─────────────────────────────────────────
    print()
    rule()
    print("  NET RESULT — what each strategy actually produced")
    rule()
    print(f"  {'strategy':<14}{'n':>4}{'wins':>6}{'win%':>7}{'total $':>11}"
          f"{'avg $':>9}{'best':>9}{'worst':>9}")
    rule("·")

    for strat, rows in sorted(by_strat.items()):
        pnls = [float(t.get("pnl") or 0) for t in rows]
        w = sum(1 for p in pnls if p > 0)
        print(f"  {strat:<14}{len(rows):>4}{w:>6}{fmt(w/len(pnls)*100,6,0)}%"
              f"{fmt(sum(pnls),11)}{fmt(sum(pnls)/len(pnls),9)}"
              f"{fmt(max(pnls),9)}{fmt(min(pnls),9)}")

    print()
    rule("═")
    print("  Slippage above is the portion of your result that has nothing to do")
    print("  with whether the strategy was right. Everything else is signal.")
    rule("═")
    print()


if __name__ == "__main__":
    analyze(load())
