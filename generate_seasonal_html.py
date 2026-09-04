#!/usr/bin/env python3
"""
Generates ~/Desktop/seasonal_calendar.html from seasonal_data.json.
Shows ES, US30, NAS100 as switchable tabs.
"""
import json, calendar
from pathlib import Path
from datetime import date, timedelta

BOT  = Path.home() / "tradelocker-bot"
DATA = BOT / "seasonal_data.json"
OUT  = Path.home() / "Desktop" / "seasonal_calendar.html"

raw    = json.loads(DATA.read_text())
YEAR   = raw["year"]
MONTH  = raw["month"]
UPDATED = raw.get("updated", "unknown")

# Support both old (trading_days) and new (instruments) format
if "instruments" in raw:
    INSTRUMENTS = {
        k: {int(d): float(v) for d, v in days.items()}
        for k, days in raw["instruments"].items()
    }
else:
    INSTRUMENTS = {"ES": {int(d): float(v) for d, v in raw["trading_days"].items()}}

LABELS = {"ES": "S&P 500 / ES", "US30": "US30 / Dow", "NAS100": "NAS100 / QQQ"}

today_dt = date.today()
TODAY = today_dt.day if (today_dt.year == YEAR and today_dt.month == MONTH) else -1

# ── 13-WEEK CYCLE ─────────────────────────────────────────────────────────────
# Aug 3-4 2026 low = cycle start (Iran de-escalation flush)
CYCLE_START = date(2026, 8, 3)
CYCLE_DAYS  = 91  # 13 weeks
cycle_day     = (today_dt - CYCLE_START).days + 1
cycle_week    = (cycle_day - 1) // 7 + 1
cycle_pct     = min(100, round(cycle_day / CYCLE_DAYS * 100))
cycle_end     = CYCLE_START + timedelta(days=CYCLE_DAYS - 1)
mid_cycle     = CYCLE_START + timedelta(days=45)
days_to_end   = (cycle_end - today_dt).days
days_to_mid   = (mid_cycle - today_dt).days

if cycle_day <= 0:
    cycle_phase = "PRE-CYCLE"
    phase_color = "#475569"
elif cycle_day <= 20:
    cycle_phase = "EARLY BULL"
    phase_color = "#10B981"
elif cycle_day <= 45:
    cycle_phase = "TRENDING UP"
    phase_color = "#3B82F6"
elif cycle_day <= 55:
    cycle_phase = "MID-CYCLE TOP"
    phase_color = "#F59E0B"
elif cycle_day <= 75:
    cycle_phase = "LATE BEAR"
    phase_color = "#F43F5E"
else:
    cycle_phase = "CYCLE END / NEW LOW"
    phase_color = "#A855F7"
_, days_in_month = calendar.monthrange(YEAR, MONTH)
first_weekday, _ = calendar.monthrange(YEAR, MONTH)
first_col = (first_weekday + 1) % 7  # Sun=0

def bias(v):
    if v is None: return "dim"
    if v >= 0.20: return "bull"
    if v <= -0.20: return "bear"
    return "neut"

def fmt(v):
    if v is None: return "—"
    return ("+" if v >= 0 else "") + f"{v:.2f}"

def day_name(d):
    return date(YEAR, MONTH, d).strftime("%a")

def build_grid(days):
    cells = ""
    for _ in range(first_col):
        cells += '<div class="cal-cell empty"></div>'
    for d in range(1, days_in_month + 1):
        dow = date(YEAR, MONTH, d).weekday()
        is_weekend = dow >= 5
        is_today   = d == TODAY
        val = days.get(d)
        b   = bias(val) if not is_weekend else "dim"
        sorted_days = sorted(days.keys())
        tdom = sorted_days.index(d) + 1 if d in sorted_days else ""

        classes = "cal-cell" + (" empty weekend" if is_weekend else " trading")
        if is_today: classes += " today-cell"
        if not is_weekend and val is not None: classes += f" {b}-cell"

        tdom_str  = f'<div class="cal-tdom">TDOM {tdom}</div>' if tdom else ""
        val_str   = f'<div class="cal-seasonal {b}">{fmt(val)}</div>' if not is_weekend else ""
        today_tag = " ◀ TODAY" if is_today else ""
        hint      = '<div class="edit-hint">click to edit</div>' if not is_weekend else ""
        onclick   = f' onclick="openModal({d}, {val if val is not None else 0})"' if not is_weekend else ""

        cells += f'<div class="{classes}"{onclick}><div class="cal-date">{d}{today_tag}</div>{tdom_str}{val_str}{hint}</div>'

    total = first_col + days_in_month
    rem   = total % 7
    if rem:
        for _ in range(7 - rem):
            cells += '<div class="cal-cell empty"></div>'
    return cells

def build_today_card(days):
    val = days.get(TODAY)
    b   = bias(val)
    bias_label = {"bull":"▲ LONG BIAS","bear":"▼ SHORT BIAS","neut":"→ NEUTRAL","dim":"— NO DATA"}[b]
    sorted_days = sorted(days.keys())
    upcoming = [(d, days[d]) for d in sorted_days if d >= TODAY][:6]
    chips = "".join(
        f'<div class="week-day-chip"><div class="wd-name">{day_name(d)} {d}</div>'
        f'<div class="wd-val {bias(v)}">{fmt(v)}</div></div>'
        for d, v in upcoming
    )
    return f'''
    <div>
      <div class="today-label">Today · {"Aug " + str(TODAY) if TODAY > 0 else "—"}</div>
      <div class="today-value {b}">{fmt(val)}</div>
    </div>
    <div class="divider"></div>
    <div>
      <div class="today-label">Seasonal Bias</div>
      <div class="bias-pill {b}">{bias_label}</div>
    </div>
    <div class="divider"></div>
    <div>
      <div class="today-label">Next Trading Days</div>
      <div class="week-summary">{chips}</div>
    </div>'''

# Build per-instrument HTML blocks
tab_buttons = ""
tab_contents = ""
for i, (key, days) in enumerate(INSTRUMENTS.items()):
    label   = LABELS.get(key, key)
    active  = "active" if i == 0 else ""
    tab_buttons += f'<button class="tab-btn {active}" onclick="switchTab(\'{key}\')" id="btn-{key}">{label}</button>'
    card  = build_today_card(days)
    grid  = build_grid(days)
    tab_contents += f'''
    <div class="tab-content {active}" id="tab-{key}">
      <div class="today-card">{card}</div>
      <div class="cal-wrap">
        <div class="cal-header">
          <div class="cal-header-cell">Sun</div><div class="cal-header-cell">Mon</div>
          <div class="cal-header-cell">Tue</div><div class="cal-header-cell">Wed</div>
          <div class="cal-header-cell">Thu</div><div class="cal-header-cell">Fri</div>
          <div class="cal-header-cell">Sat</div>
        </div>
        <div class="cal-grid">{grid}</div>
      </div>
    </div>'''

# All days data for JS modal editing
all_days_js = json.dumps({k: {str(d): v for d, v in days.items()} for k, days in INSTRUMENTS.items()})

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seasonal Calendar — ES/US30/NAS100</title>
<style>
  :root{{--bg:#080C14;--bg2:#0F1522;--bg3:#161D2E;--border:#1E2A40;
        --text:#94A3B8;--text-hi:#E2E8F0;--text-dim:#475569;
        --bull:#10B981;--bull-bg:rgba(16,185,129,.12);
        --bear:#F43F5E;--bear-bg:rgba(244,63,94,.12);
        --neut:#F59E0B;--neut-bg:rgba(245,158,11,.10);
        --today:#3B82F6;--today-bg:rgba(59,130,246,.15);}}
  @media(prefers-color-scheme:light){{:root{{--bg:#F0F4FA;--bg2:#fff;--bg3:#E8EEF8;
    --border:#CBD5E1;--text:#475569;--text-hi:#0F172A;--text-dim:#94A3B8;}}}}
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-size:14px;min-height:100vh;padding:20px}}
  .header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}}
  .header h1{{font-size:18px;font-weight:600;color:var(--text-hi)}}
  .header p{{font-size:12px;color:var(--text-dim);margin-top:2px}}
  .updated{{font-size:11px;color:var(--text-dim);background:var(--bg3);border:1px solid var(--border);padding:5px 10px;border-radius:6px}}
  .tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
  .tab-btn{{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:8px 18px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .15s}}
  .tab-btn.active{{background:var(--today);border-color:var(--today);color:#fff;font-weight:600}}
  .tab-content{{display:none}}.tab-content.active{{display:block}}
  .today-card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}}
  .today-label{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim);margin-bottom:4px}}
  .today-value{{font-size:28px;font-weight:700;font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums}}
  .today-value.bull{{color:var(--bull)}}.today-value.bear{{color:var(--bear)}}.today-value.neut{{color:var(--neut)}}.today-value.dim{{color:var(--text-dim)}}
  .bias-pill{{display:inline-flex;align-items:center;padding:6px 14px;border-radius:99px;font-size:13px;font-weight:600}}
  .bias-pill.bull{{background:var(--bull-bg);color:var(--bull)}}.bias-pill.bear{{background:var(--bear-bg);color:var(--bear)}}.bias-pill.neut{{background:var(--neut-bg);color:var(--neut)}}.bias-pill.dim{{color:var(--text-dim)}}
  .divider{{width:1px;height:40px;background:var(--border)}}
  .week-summary{{display:flex;gap:16px;flex-wrap:wrap}}
  .week-day-chip{{text-align:center}}
  .wd-name{{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-dim);margin-bottom:4px}}
  .wd-val{{font-size:15px;font-weight:600;font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums}}
  .wd-val.bull{{color:var(--bull)}}.wd-val.bear{{color:var(--bear)}}.wd-val.neut{{color:var(--neut)}}.wd-val.dim{{color:var(--text-dim)}}
  .cal-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;overflow:hidden}}
  .cal-header{{display:grid;grid-template-columns:repeat(7,1fr);border-bottom:1px solid var(--border)}}
  .cal-header-cell{{padding:10px 0;text-align:center;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim);font-weight:600}}
  .cal-grid{{display:grid;grid-template-columns:repeat(7,1fr)}}
  .cal-cell{{border-right:1px solid var(--border);border-bottom:1px solid var(--border);min-height:80px;padding:10px;position:relative}}
  .cal-cell:nth-child(7n){{border-right:none}}
  .cal-cell.empty,.cal-cell.weekend{{background:var(--bg);opacity:.4}}
  .cal-cell.trading{{cursor:pointer}}.cal-cell.trading:hover{{background:var(--bg3)}}
  .cal-cell.today-cell{{background:var(--today-bg)!important;outline:1px solid var(--today)}}
  .cal-cell.bull-cell{{background:var(--bull-bg)}}.cal-cell.bear-cell{{background:var(--bear-bg)}}.cal-cell.neut-cell{{background:var(--neut-bg)}}
  .cal-date{{font-size:12px;font-weight:700;color:var(--text-dim);margin-bottom:6px}}
  .today-cell .cal-date{{color:var(--today)}}
  .cal-tdom{{font-size:10px;color:var(--text-dim);margin-bottom:4px}}
  .cal-seasonal{{font-size:20px;font-weight:700;font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums}}
  .cal-seasonal.bull{{color:var(--bull)}}.cal-seasonal.bear{{color:var(--bear)}}.cal-seasonal.neut{{color:var(--neut)}}.cal-seasonal.dim{{color:var(--text-dim);font-size:13px}}
  .edit-hint{{position:absolute;bottom:6px;right:8px;font-size:9px;color:var(--text-dim);opacity:0;transition:opacity .15s}}
  .cal-cell.trading:hover .edit-hint{{opacity:1}}
  .legend{{display:flex;gap:20px;margin-top:14px;flex-wrap:wrap;align-items:center}}
  .legend-item{{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-dim)}}
  .legend-dot{{width:8px;height:8px;border-radius:50%}}
  .legend-dot.bull{{background:var(--bull)}}.legend-dot.bear{{background:var(--bear)}}.legend-dot.neut{{background:var(--neut)}}
  /* 13-week cycle */
  .cycle-card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-bottom:16px}}
  .cycle-title{{font-size:13px;font-weight:700;color:var(--text-hi);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}}
  .cycle-row{{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:12px}}
  .cycle-stat{{text-align:center;min-width:80px}}
  .cycle-stat-label{{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--text-dim);margin-bottom:3px}}
  .cycle-stat-val{{font-size:20px;font-weight:700;font-family:ui-monospace,monospace}}
  .cycle-phase-pill{{display:inline-flex;align-items:center;padding:5px 14px;border-radius:99px;font-size:12px;font-weight:700;letter-spacing:.05em}}
  .cycle-bar-wrap{{width:100%;background:var(--bg3);border-radius:99px;height:10px;overflow:hidden;margin-bottom:8px}}
  .cycle-bar-fill{{height:100%;border-radius:99px;transition:width .4s ease;background:linear-gradient(90deg,#10B981,#3B82F6,#F59E0B,#F43F5E,#A855F7)}}
  .cycle-markers{{display:flex;justify-content:space-between;font-size:10px;color:var(--text-dim);margin-bottom:12px}}
  .cycle-dates{{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--text-dim)}}
  .cycle-dates span{{display:flex;align-items:center;gap:4px}}
  .cycle-dot{{width:7px;height:7px;border-radius:50%;display:inline-block}}
  .modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}}
  .modal-overlay.open{{display:flex}}
  .modal{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;width:280px;box-shadow:0 20px 60px rgba(0,0,0,.5)}}
  .modal h3{{color:var(--text-hi);margin-bottom:4px}}.modal p{{font-size:12px;color:var(--text-dim);margin-bottom:14px}}
  .modal input{{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--text-hi);font-size:18px;font-family:ui-monospace,monospace;text-align:center;outline:none;margin-bottom:14px}}
  .modal input:focus{{border-color:var(--today)}}
  .modal-btns{{display:flex;gap:8px}}
  .modal-btns button{{flex:1;padding:9px;border-radius:8px;border:1px solid var(--border);cursor:pointer;font-size:13px;font-weight:600}}
  .btn-cancel{{background:var(--bg3);color:var(--text)}}.btn-save{{background:var(--today);color:#fff;border-color:var(--today)}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Seasonal Calendar — ES · US30 · NAS100</h1>
    <p>Larry Williams AVGnow · {today_dt.strftime("%B %Y")} · Auto-updated daily from 10yr price history</p>
  </div>
  <div class="updated">Last synced: {UPDATED}</div>
</div>

<div class="cycle-card">
  <div class="cycle-title">⏱ Larry Williams 13-Week Cycle</div>
  <div class="cycle-row">
    <div class="cycle-stat">
      <div class="cycle-stat-label">Day</div>
      <div class="cycle-stat-val" style="color:{phase_color}">{cycle_day}</div>
    </div>
    <div class="cycle-stat">
      <div class="cycle-stat-label">Week</div>
      <div class="cycle-stat-val" style="color:{phase_color}">{cycle_week} / 13</div>
    </div>
    <div class="cycle-stat">
      <div class="cycle-stat-label">Progress</div>
      <div class="cycle-stat-val" style="color:{phase_color}">{cycle_pct}%</div>
    </div>
    <div>
      <div class="cycle-stat-label">Phase</div>
      <div class="cycle-phase-pill" style="background:{phase_color}22;color:{phase_color}">{cycle_phase}</div>
    </div>
    <div class="cycle-stat">
      <div class="cycle-stat-label">Days to Mid</div>
      <div class="cycle-stat-val" style="color:#F59E0B">{max(0,days_to_mid)}</div>
    </div>
    <div class="cycle-stat">
      <div class="cycle-stat-label">Days to End</div>
      <div class="cycle-stat-val" style="color:#A855F7">{max(0,days_to_end)}</div>
    </div>
  </div>
  <div class="cycle-bar-wrap">
    <div class="cycle-bar-fill" style="width:{cycle_pct}%"></div>
  </div>
  <div class="cycle-markers">
    <span>▼ Cycle Low (Aug 3)</span>
    <span>↑ Mid-Top (~{mid_cycle.strftime("%b %d")})</span>
    <span>▼ Cycle End (~{cycle_end.strftime("%b %d")})</span>
  </div>
  <div class="cycle-dates">
    <span><span class="cycle-dot" style="background:#10B981"></span> Early Bull: Wk 1–3 → go long</span>
    <span><span class="cycle-dot" style="background:#F59E0B"></span> Mid-Cycle Top: Wk 6–8 → watch for short</span>
    <span><span class="cycle-dot" style="background:#F43F5E"></span> Late Bear: Wk 9–12 → trend down to new low</span>
    <span><span class="cycle-dot" style="background:#A855F7"></span> Cycle End: Wk 13 → next low / reset</span>
  </div>
</div>

<div class="tabs">{tab_buttons}</div>
{tab_contents}

<div class="legend">
  <div class="legend-item"><div class="legend-dot bull"></div> Bullish (≥ +0.20)</div>
  <div class="legend-item"><div class="legend-dot neut"></div> Neutral (±0.20)</div>
  <div class="legend-item"><div class="legend-dot bear"></div> Bearish (≤ −0.20)</div>
</div>

<div class="modal-overlay" id="modal">
  <div class="modal">
    <h3 id="modalTitle">Edit Value</h3>
    <p id="modalSub">Manual override for this day</p>
    <input type="number" id="modalInput" step="0.01" placeholder="e.g. -0.83">
    <div class="modal-btns">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-save" onclick="saveModal()">Save</button>
    </div>
  </div>
</div>

<script>
const ALL_DATA = {all_days_js};
let activeTab = '{list(INSTRUMENTS.keys())[0]}';
let editDay   = null;

function switchTab(key) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('btn-' + key).classList.add('active');
  document.getElementById('tab-' + key).classList.add('active');
  activeTab = key;
}}

function openModal(d, cur) {{
  editDay = d;
  const dt = new Date({YEAR}, {MONTH-1}, d);
  document.getElementById('modalTitle').textContent = 'Aug ' + d + ' — ' + dt.toLocaleDateString('en-US',{{weekday:'long'}});
  document.getElementById('modalSub').textContent = activeTab + ' manual override';
  document.getElementById('modalInput').value = cur || '';
  document.getElementById('modal').classList.add('open');
  document.getElementById('modalInput').focus();
}}
function closeModal() {{
  document.getElementById('modal').classList.remove('open');
  editDay = null;
}}
function saveModal() {{
  const v = parseFloat(document.getElementById('modalInput').value);
  if (!isNaN(v)) {{
    ALL_DATA[activeTab][editDay] = v;
    const key = 'seasonal_overrides_{YEAR}_{MONTH}_' + activeTab;
    localStorage.setItem(key, JSON.stringify(ALL_DATA[activeTab]));
    closeModal();
    location.reload();
  }} else {{ closeModal(); }}
}}
document.getElementById('modal').addEventListener('click', e => {{
  if (e.target === document.getElementById('modal')) closeModal();
}});
document.getElementById('modalInput').addEventListener('keydown', e => {{
  if (e.key === 'Enter') saveModal();
  if (e.key === 'Escape') closeModal();
}});
</script>
</body>
</html>"""

OUT.write_text(html, encoding="utf-8")
print(f"✅  Seasonal calendar (3 instruments) → {OUT}")
