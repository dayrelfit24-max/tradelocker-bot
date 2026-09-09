#!/usr/bin/env python3
"""
Reporte de rendimiento por indicador — solo operaciones verificadas.

Una operación cuenta acá únicamente si se puede probar qué señal la originó:
el bot guarda el id de orden que devuelve el broker al abrirla, y ese id
aparece igual en el historial de órdenes. Eso liga la operación a su señal sin
ambigüedad.

Las operaciones atribuidas por parecido de precio y hora quedan FUERA a
propósito. Ese método produjo atribuciones falsas — 46 operaciones de EURUSD de
octubre 2025 quedaron asignadas a un indicador que ni siquiera registraba
señales en esa fecha. Un reporte que se muestra a terceros no puede apoyarse en
eso.

Genera:  ~/Desktop/reporte-indicadores.html
"""
import json, html
from pathlib import Path
from datetime import datetime
from collections import defaultdict

TRADES = Path.home() / "tradelocker-bot" / "tradelocker_trades.json"
OUT    = Path.home() / "Desktop" / "reporte-indicadores.html"

NOMBRES = {
    "dual_vwap":  "Dual VWAP",
    "ema50_vwap": "EMA50 + VWAP",
}


def clasificar_salida(t):
    """Dónde terminó la operación respecto al plan de la señal."""
    try:
        sl, tp, ex = float(t["signalSL"]), float(t["signalTP"]), float(t["exit"])
    except (KeyError, TypeError, ValueError):
        return "—"
    tol = abs(tp - sl) * 0.05
    if abs(ex - tp) <= tol:
        return "objetivo"
    if abs(ex - sl) <= tol:
        return "stop"
    return "otro"


def estadisticas(rows):
    p = [float(t.get("pnl") or 0) for t in rows]
    if not p:
        return None
    g = [v for v in p if v > 0]
    l = [v for v in p if v < 0]

    racha = peor_racha = 0
    eq = pico = 0.0
    dd = 0.0
    curva = []
    for v in p:
        racha = racha + 1 if v < 0 else 0
        peor_racha = max(peor_racha, racha)
        eq += v
        curva.append(eq)
        pico = max(pico, eq)
        dd = min(dd, eq - pico)

    salidas = defaultdict(int)
    for t in rows:
        salidas[clasificar_salida(t)] += 1

    por_simbolo = defaultdict(lambda: [0.0, 0])
    for t in rows:
        s = por_simbolo[t["symbol"]]
        s[0] += float(t.get("pnl") or 0)
        s[1] += 1

    return {
        "n": len(p),
        "neto": sum(p),
        "ganadoras": len(g),
        "perdedoras": len(l),
        "acierto": len(g) / len(p) * 100,
        "media_ganancia": sum(g) / len(g) if g else 0,
        "media_perdida": sum(l) / len(l) if l else 0,
        "factor": (sum(g) / abs(sum(l))) if l else float("inf"),
        "esperanza": sum(p) / len(p),
        "mejor": max(p),
        "peor": min(p),
        "peor_racha": peor_racha,
        "drawdown": dd,
        "curva": curva,
        "salidas": dict(salidas),
        "por_simbolo": sorted(por_simbolo.items(), key=lambda i: -i[1][0]),
        "desde": min(t["date"] for t in rows)[:10],
        "hasta": max(t["date"] for t in rows)[:10],
    }


def money(v, signo=True):
    s = f"{v:+,.2f}" if signo else f"{v:,.2f}"
    return s.replace(",", " ")


def sparkline(curva, ancho=260, alto=64):
    """Curva acumulada dibujada a escala, con la línea de cero visible."""
    if len(curva) < 2:
        return ""
    serie = [0.0] + curva
    lo, hi = min(serie), max(serie)
    if hi - lo < 1e-9:
        hi = lo + 1
    pad = 8
    ax, ay = ancho - pad * 2, alto - pad * 2

    def punto(i, v):
        x = pad + ax * i / (len(serie) - 1)
        y = pad + ay * (1 - (v - lo) / (hi - lo))
        return x, y

    pts = [punto(i, v) for i, v in enumerate(serie)]
    linea = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"{pts[0][0]:.1f},{alto - pad:.1f} " + linea +
            f" {pts[-1][0]:.1f},{alto - pad:.1f}")
    cero_y = pad + ay * (1 - (0 - lo) / (hi - lo))
    positivo = curva[-1] >= 0
    color = "var(--pos)" if positivo else "var(--neg)"
    fx, fy = pts[-1]
    return f'''<svg class="spark" viewBox="0 0 {ancho} {alto}" role="img"
      aria-label="Resultado acumulado: {money(curva[-1])} dólares">
  <line x1="{pad}" y1="{cero_y:.1f}" x2="{ancho - pad}" y2="{cero_y:.1f}"
        stroke="var(--linea)" stroke-width="1" stroke-dasharray="2 3"/>
  <polygon points="{area}" fill="{color}" opacity=".10"/>
  <polyline points="{linea}" fill="none" stroke="{color}"
            stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{fx:.1f}" cy="{fy:.1f}" r="3" fill="{color}"/>
</svg>'''


def panel(clave, st):
    nombre = NOMBRES.get(clave, clave)
    pos = st["neto"] >= 0
    factor = "∞" if st["factor"] == float("inf") else f"{st['factor']:.2f}"
    filas = [
        ("Operaciones", str(st["n"])),
        ("Ganadoras", f"{st['ganadoras']} de {st['n']} · {st['acierto']:.0f}%"),
        ("Ganancia media", money(st["media_ganancia"])),
        ("Pérdida media", money(st["media_perdida"])),
        ("Factor de beneficio", factor),
        ("Resultado por operación", money(st["esperanza"])),
        ("Mejor / peor", f"{money(st['mejor'])} / {money(st['peor'])}"),
        ("Racha perdedora máxima", f"{st['peor_racha']} seguidas"),
        ("Caída máxima", money(st["drawdown"], signo=False)),
    ]
    cuerpo = "".join(
        f'<div class="fila"><dt>{html.escape(k)}</dt>'
        f'<dd class="num">{html.escape(v)}</dd></div>'
        for k, v in filas
    )
    simbolos = "".join(
        f'<li><span>{html.escape(s)}</span>'
        f'<span class="num {"pos" if v[0] >= 0 else "neg"}">{money(v[0])}'
        f'<em>{v[1]}</em></span></li>'
        for s, v in st["por_simbolo"]
    )
    sal = st["salidas"]
    orden = [("objetivo", "al objetivo"), ("stop", "al stop"), ("otro", "otro cierre")]
    salidas = "".join(
        f'<li><span>{etq}</span><span class="num">{sal.get(k, 0)}</span></li>'
        for k, etq in orden if sal.get(k)
    )
    return f'''<article class="panel">
  <header class="panel-cab">
    <h3>{html.escape(nombre)}</h3>
    <p class="clave">{html.escape(clave)}</p>
  </header>
  <div class="resultado {'pos' if pos else 'neg'}">
    <span class="cifra num">{money(st['neto'])}</span>
    <span class="unidad">USD · {st['n']} operaciones</span>
  </div>
  {sparkline(st['curva'])}
  <dl class="tabla">{cuerpo}</dl>
  <div class="desglose">
    <h4>Por instrumento</h4>
    <ul>{simbolos}</ul>
  </div>
  <div class="desglose">
    <h4>Cómo cerraron</h4>
    <ul>{salidas}</ul>
  </div>
</article>'''


def construir():
    if not TRADES.exists():
        raise SystemExit(f"no encuentro {TRADES}")
    todo = json.loads(TRADES.read_text())

    # Solo lo que se puede probar: señal ligada por id de orden.
    ver = [t for t in todo
           if t.get("signalEntry") is not None
           and t.get("strategy") in NOMBRES]
    ver.sort(key=lambda t: t.get("date") or "")

    if not ver:
        raise SystemExit("todavía no hay operaciones con señal verificada")

    por_ind = defaultdict(list)
    for t in ver:
        por_ind[t["strategy"]].append(t)
    stats = {k: estadisticas(v) for k, v in por_ind.items()}

    total = sum(float(t.get("pnl") or 0) for t in ver)
    desde, hasta = ver[0]["date"][:10], ver[-1]["date"][:10]
    dias = (datetime.fromisoformat(ver[-1]["date"])
            - datetime.fromisoformat(ver[0]["date"])).days + 1
    excluidas = sum(1 for t in todo
                    if t.get("strategy") in NOMBRES and t.get("signalEntry") is None)

    paneles = "".join(panel(k, stats[k]) for k in sorted(stats, key=lambda k: -stats[k]["n"]))

    filas = []
    for t in ver:
        p = float(t.get("pnl") or 0)
        salida = clasificar_salida(t)
        filas.append(
            f'<tr>'
            f'<td class="num fecha">{t["date"][:10]}</td>'
            f'<td>{html.escape(t["symbol"])}</td>'
            f'<td class="dir">{"Compra" if t["direction"] == "Long" else "Venta"}</td>'
            f'<td>{html.escape(NOMBRES.get(t["strategy"], t["strategy"]))}</td>'
            f'<td><span class="pill p-{salida}">{salida}</span></td>'
            f'<td class="num {"pos" if p >= 0 else "neg"}">{money(p)}</td>'
            f'</tr>'
        )
    ledger = "".join(filas)

    generado = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f'''<title>Señales Verificadas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
  :root {{
    --tinta:    #16191d;
    --papel:    #f7f6f3;
    --sup:      #fffefc;
    --tenue:    #6e727a;
    --linea:    #d9d6d0;
    --teal:     #1f5f66;
    --pos:      #2f7d52;
    --neg:      #a63d3d;
    --aviso-bg: #fdf6e7;
    --aviso-bd: #e0c98a;
    --aviso-tx: #6b5310;
    --sombra:   0 1px 2px rgba(22,25,29,.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --tinta:#e9e7e3; --papel:#131619; --sup:#191d21; --tenue:#9298a1;
      --linea:#2c3238; --teal:#63b6bd; --pos:#5fbb87; --neg:#e08585;
      --aviso-bg:#241f12; --aviso-bd:#5e4d20; --aviso-tx:#e0c98a;
      --sombra:0 1px 2px rgba(0,0,0,.3);
    }}
  }}
  :root[data-theme="dark"] {{
    --tinta:#e9e7e3; --papel:#131619; --sup:#191d21; --tenue:#9298a1;
    --linea:#2c3238; --teal:#63b6bd; --pos:#5fbb87; --neg:#e08585;
    --aviso-bg:#241f12; --aviso-bd:#5e4d20; --aviso-tx:#e0c98a;
    --sombra:0 1px 2px rgba(0,0,0,.3);
  }}

  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--papel); color: var(--tinta);
    font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
    font-size: 15px; line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  .num {{ font-family: "IBM Plex Mono", ui-monospace, monospace;
          font-variant-numeric: tabular-nums; }}
  .pos {{ color: var(--pos); }}
  .neg {{ color: var(--neg); }}

  .hoja {{ max-width: 940px; margin: 0 auto; padding: 44px 24px 72px;
           display: flex; flex-direction: column; gap: 34px; }}

  .cab {{ display: flex; flex-direction: column; gap: 12px;
          border-bottom: 2px solid var(--tinta); padding-bottom: 20px; }}
  .sello {{ font-size: 11px; letter-spacing: .13em; text-transform: uppercase;
            color: var(--teal); font-weight: 600; }}
  h1 {{ font-family: Newsreader, Georgia, serif; font-weight: 400;
        font-size: clamp(30px, 5vw, 42px); line-height: 1.12; margin: 0;
        text-wrap: balance; letter-spacing: -.01em; }}
  .bajada {{ margin: 0; color: var(--tenue); max-width: 62ch; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 13px;
           color: var(--tenue); }}
  .meta b {{ color: var(--tinta); font-weight: 500; }}

  .aviso {{ background: var(--aviso-bg); border: 1px solid var(--aviso-bd);
            color: var(--aviso-tx); border-radius: 3px; padding: 16px 18px;
            font-size: 13.5px; line-height: 1.55; }}
  .aviso b {{ font-weight: 600; }}

  h2 {{ font-family: Newsreader, Georgia, serif; font-weight: 400;
        font-size: 23px; margin: 0 0 2px; letter-spacing: -.005em; }}
  .seccion > p {{ margin: 0 0 16px; color: var(--tenue); font-size: 14px;
                  max-width: 64ch; }}

  .paneles {{ display: grid; gap: 18px;
              grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
  .panel {{ background: var(--sup); border: 1px solid var(--linea);
            border-radius: 3px; padding: 22px; box-shadow: var(--sombra);
            display: flex; flex-direction: column; gap: 16px; }}
  .panel-cab h3 {{ font-family: Newsreader, Georgia, serif; font-weight: 500;
                   font-size: 21px; margin: 0; }}
  .clave {{ margin: 2px 0 0; font-family: "IBM Plex Mono", monospace;
            font-size: 11.5px; color: var(--tenue); }}
  .resultado {{ display: flex; align-items: baseline; gap: 10px;
                flex-wrap: wrap; }}
  .cifra {{ font-size: 30px; font-weight: 600; letter-spacing: -.02em; }}
  .resultado.pos .cifra {{ color: var(--pos); }}
  .resultado.neg .cifra {{ color: var(--neg); }}
  .unidad {{ font-size: 12.5px; color: var(--tenue); }}
  .spark {{ width: 100%; height: 64px; display: block; }}

  .tabla {{ margin: 0; display: flex; flex-direction: column; }}
  .fila {{ display: flex; justify-content: space-between; align-items: baseline;
           gap: 14px; padding: 7px 0; border-bottom: 1px solid var(--linea);
           font-size: 13.5px; }}
  .fila:last-child {{ border-bottom: 0; }}
  .fila dt {{ color: var(--tenue); }}
  .fila dd {{ margin: 0; font-weight: 500; text-align: right; }}

  .desglose h4 {{ font-size: 10.5px; letter-spacing: .11em;
                  text-transform: uppercase; color: var(--tenue);
                  margin: 0 0 7px; font-weight: 600; }}
  .desglose ul {{ list-style: none; margin: 0; padding: 0;
                  display: flex; flex-direction: column; gap: 5px; }}
  .desglose li {{ display: flex; justify-content: space-between;
                  font-size: 13.5px; gap: 12px; }}
  .desglose em {{ font-style: normal; color: var(--tenue); font-size: 11.5px;
                  margin-left: 8px; }}

  .envoltura {{ overflow-x: auto; border: 1px solid var(--linea);
                border-radius: 3px; background: var(--sup);
                box-shadow: var(--sombra); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13.5px;
           min-width: 620px; }}
  th {{ text-align: left; font-size: 10.5px; letter-spacing: .1em;
        text-transform: uppercase; color: var(--tenue); font-weight: 600;
        padding: 12px 14px; border-bottom: 1px solid var(--linea);
        white-space: nowrap; }}
  td {{ padding: 9px 14px; border-bottom: 1px solid var(--linea); }}
  tbody tr:last-child td {{ border-bottom: 0; }}
  th:last-child, td:last-child {{ text-align: right; }}
  .fecha {{ color: var(--tenue); font-size: 12.5px; }}
  .dir {{ color: var(--tenue); }}
  .pill {{ display: inline-block; font-size: 11px; padding: 1px 8px;
           border-radius: 2px; border: 1px solid var(--linea);
           color: var(--tenue); white-space: nowrap; }}
  .p-objetivo {{ color: var(--pos); border-color: var(--pos); }}
  .p-stop {{ color: var(--neg); border-color: var(--neg); }}

  .metodo {{ display: grid; gap: 16px;
             grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }}
  .metodo section {{ border-top: 2px solid var(--teal); padding-top: 12px; }}
  .metodo h3 {{ font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
                margin: 0 0 6px; color: var(--teal); font-weight: 600; }}
  .metodo p {{ margin: 0; font-size: 13.5px; color: var(--tenue); }}

  footer {{ border-top: 1px solid var(--linea); padding-top: 18px;
            font-size: 12px; color: var(--tenue); line-height: 1.6; }}
</style>

<div class="hoja">

  <header class="cab">
    <p class="sello">Registro de operaciones · cuenta real</p>
    <h1>Qué hicieron los dos indicadores en operaciones verificadas</h1>
    <p class="bajada">Cada operación de esta página está ligada por número de
    orden a la señal que la originó. Están todas, ganadoras y perdedoras.</p>
    <div class="meta">
      <span><b>{len(ver)}</b> operaciones</span>
      <span><b>{dias}</b> días · {desde} a {hasta}</span>
      <span>Resultado conjunto <b class="num {'pos' if total >= 0 else 'neg'}">{money(total)}</b> USD</span>
    </div>
  </header>

  <div class="aviso">
    <b>Muestra pequeña.</b> {len(ver)} operaciones en {dias} días no alcanzan
    para afirmar que un resultado se repetirá. Sirven para mostrar cómo opera
    cada indicador, no para proyectar rendimiento futuro. Con este número de
    operaciones, el orden de los dos indicadores puede darse vuelta con unas
    pocas más.
  </div>

  <div class="seccion">
    <h2>Los dos indicadores</h2>
    <p>Mismo período, misma cuenta, mismas condiciones de ejecución.</p>
    <div class="paneles">{paneles}</div>
  </div>

  <div class="seccion">
    <h2>Las {len(ver)} operaciones, una por una</h2>
    <p>Sin filtrar. La columna de cierre indica si la operación terminó en su
    objetivo, en su stop, o se cerró de otra forma.</p>
    <div class="envoltura">
      <table>
        <thead><tr>
          <th>Fecha</th><th>Instrumento</th><th>Dirección</th>
          <th>Indicador</th><th>Cierre</th><th>Resultado</th>
        </tr></thead>
        <tbody>{ledger}</tbody>
      </table>
    </div>
  </div>

  <div class="seccion">
    <h2>Cómo se armó</h2>
    <div class="metodo">
      <section>
        <h3>Qué cuenta como verificado</h3>
        <p>Al abrir una operación el bot guarda el número de orden que devuelve
        el broker. Ese mismo número aparece en el historial de la cuenta, así
        que cada operación queda unida a su señal sin ambigüedad.</p>
      </section>
      <section>
        <h3>Qué quedó afuera</h3>
        <p>{excluidas} operaciones anteriores, atribuidas por parecido de precio
        y hora. Ese método asignó operaciones a indicadores que todavía no
        registraban señales, así que no son confiables y no se muestran.</p>
      </section>
      <section>
        <h3>De dónde salen las cifras</h3>
        <p>Del historial de órdenes del broker, no de un backtest. Los
        resultados incluyen el precio real de ejecución, con su deslizamiento.
        No incluyen swap ni comisiones, que el broker no expone por operación.</p>
      </section>
    </div>
  </div>

  <footer>
    <p>Generado el {generado} desde el historial de la cuenta.
    Operar instrumentos apalancados implica riesgo de pérdida.
    Los resultados pasados no garantizan resultados futuros.
    Esta página describe el comportamiento de dos herramientas de análisis y
    no es una recomendación de inversión.</p>
  </footer>

</div>'''


if __name__ == "__main__":
    contenido = construir()

    # Copia local: documento completo. Sin declarar el charset, el navegador
    # adivina la codificación y los acentos salen rotos al abrirlo con file://.
    OUT.write_text(
        '<!doctype html>\n<html lang="es">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'{contenido}\n</html>\n',
        encoding="utf-8",
    )
    # Copia para publicar: solo el contenido, el envoltorio lo pone la web.
    OUT.with_suffix(".cuerpo.html").write_text(contenido, encoding="utf-8")
    print(f"✅  {OUT}")
