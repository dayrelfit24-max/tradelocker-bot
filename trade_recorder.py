#!/usr/bin/env python3
"""
Graba la pantalla mientras hay un trade abierto — material para TikTok.

Vigila las posiciones abiertas en TradeLocker. Cuando aparece una nueva empieza
a grabar; cuando desaparece (stop loss, take profit o cierre manual) para la
grabación y guarda el archivo con el resultado en el nombre:

    2026-09-09_1432_US30_Long_dual_vwap_TP_+27.43.mp4

Así el archivo ya viene etiquetado y se puede filtrar el material bueno sin
abrir cada video.

Requiere permiso de Grabación de Pantalla para el programa que lo ejecuta
(Ajustes del Sistema → Privacidad y seguridad → Grabación de pantalla).

Uso:
    python3 trade_recorder.py                 # graba la pantalla 1
    python3 trade_recorder.py --screen 2      # otra pantalla
    python3 trade_recorder.py --list-screens  # ver cuáles hay
    python3 trade_recorder.py --test 15       # prueba de 15s sin esperar trade
"""
import os, re, sys, csv, json, time, signal, argparse, subprocess, logging
import requests
from pathlib import Path
from datetime import datetime, timezone

BASE    = "https://live.tradelocker.com/backend-api"
CONFIG  = Path.home() / "tradelocker-bot" / "config.env"
TRADES  = Path.home() / "tradelocker-bot" / "tradelocker_trades.json"
JOURNAL = Path.home() / "tradelocker-bot" / "trades_journal.csv"
OUTDIR  = Path.home() / "Movies" / "TradeClips"

RAILWAY_URL    = "https://web-production-c41f5.up.railway.app"
RAILWAY_SECRET = "tradelocker_dayrel_2026"

POLL_SECONDS  = 5      # cada cuánto se revisan las posiciones
MAX_MINUTES   = 45     # tope por archivo; un trade largo se parte en varios
SETTLE_SECS   = 8      # margen que se sigue grabando tras el cierre

log = logging.getLogger("recorder")


def load_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


# ── TradeLocker ─────────────────────────────────────────────────────────────
class Broker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.th = None
        self.acc_id = cfg.get("TL_ACCOUNT_ID", "")
        self.instruments = {}

    def authenticate(self):
        r = requests.post(f"{BASE}/auth/jwt/token", json={
            "email": self.cfg.get("TL_EMAIL", ""),
            "password": self.cfg.get("TL_PASSWORD", ""),
            "server": self.cfg.get("TL_SERVER", "HEROFX"),
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
        token = data.get("accessToken") or data.get("d", {}).get("accessToken")
        if not token:
            log.error("no se pudo autenticar: %s", data)
            return False
        h = {"Authorization": f"Bearer {token}"}

        d = requests.get(f"{BASE}/auth/jwt/all-accounts", headers=h, timeout=15).json()
        accounts = d.get("accounts") or d.get("d", {}).get("accounts", [])
        if not accounts:
            log.error("sin cuentas")
            return False
        best = max(accounts, key=lambda a: float(a.get("accountBalance", 0) or 0))
        self.acc_id = str(best.get("id", self.acc_id))
        self.th = {**h, "accNum": str(best.get("accNum", 1))}

        try:
            ir = requests.get(f"{BASE}/trade/accounts/{self.acc_id}/instruments",
                              headers=self.th, timeout=15).json()
            for i in ir.get("d", {}).get("instruments", []):
                self.instruments[str(i.get("tradableInstrumentId"))] = i.get("name", "")
        except Exception:
            pass

        log.info("conectado — cuenta %s", self.acc_id)
        return True

    def open_positions(self):
        """{positionId: {symbol, side, qty, entry}} o None si falló la consulta."""
        try:
            r = requests.get(f"{BASE}/trade/accounts/{self.acc_id}/positions",
                             headers=self.th, timeout=15)
            body = r.json()
            if body.get("s") != "ok":
                if r.status_code in (401, 403):
                    self.authenticate()
                return None
            out = {}
            for row in body.get("d", {}).get("positions", []):
                if not isinstance(row, list) or len(row) < 6:
                    continue
                pid = str(row[0])
                out[pid] = {
                    "symbol": self.instruments.get(str(row[1]), f"ID{row[1]}"),
                    "side":   str(row[3]),
                    "qty":    str(row[4]),
                    "entry":  str(row[5]),
                }
            return out
        except Exception as e:
            log.warning("no se pudieron leer posiciones: %s", e)
            return None


# ── Grabación ───────────────────────────────────────────────────────────────
def list_screens():
    out = subprocess.run(["ffmpeg", "-f", "avfoundation", "-list_devices", "true",
                          "-i", ""], capture_output=True, text=True).stderr
    print("\nPantallas disponibles:\n")
    for line in out.splitlines():
        if "Capture screen" in line:
            m = re.search(r"\[(\d+)\]\s*(Capture screen \d+)", line)
            if m:
                print(f"   --screen {m.group(1)}   {m.group(2)}")
    print("\nProbá cuál es cuál con:  python3 trade_recorder.py --test 10 --screen N\n")


def find_window(app_name):
    """Ubica la ventana de una app y en qué pantalla de ffmpeg está.

    Devuelve (indice_ffmpeg, x, y, ancho, alto) con las coordenadas ya
    relativas a esa pantalla, o None si no se encuentra la ventana.
    Solo necesita permiso de Grabación de Pantalla, no de Accesibilidad.
    """
    try:
        import Quartz
    except ImportError:
        log.warning("falta pyobjc-framework-Quartz; grabo la pantalla completa")
        return None

    win = None
    try:
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly |
            Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID)
        for w in wins:
            owner = str(w.get("kCGWindowOwnerName", ""))
            b = w.get("kCGWindowBounds", {})
            if app_name.lower() in owner.lower() and \
               b.get("Width", 0) > 400 and b.get("Height", 0) > 300:
                if win is None or (b["Width"] * b["Height"]) > (win[1] * win[2]):
                    win = ((int(b["X"]), int(b["Y"])), int(b["Width"]), int(b["Height"]))
    except Exception as e:
        log.warning("no se pudo ubicar la ventana: %s", e)
        return None

    if not win:
        return None
    (wx, wy), ww, wh = win

    try:
        import Quartz
        _, ids, _ = Quartz.CGGetActiveDisplayList(16, None, None)
        for idx, did in enumerate(ids):
            db = Quartz.CGDisplayBounds(did)
            dx, dy = int(db.origin.x), int(db.origin.y)
            dw, dh = int(db.size.width), int(db.size.height)
            # centro de la ventana dentro de esta pantalla
            if dx <= wx + ww // 2 < dx + dw and dy <= wy + wh // 2 < dy + dh:
                rx, ry = wx - dx, wy - dy
                # recortar a los límites de la pantalla
                rx, ry = max(0, rx), max(0, ry)
                rw, rh = min(ww, dw - rx), min(wh, dh - ry)
                return (idx, rx, ry, rw, rh)
    except Exception as e:
        log.warning("no se pudo mapear la pantalla: %s", e)
    return None


def join_clips(stem, parts, outdir):
    """Une el clip de apertura y el de cierre en un solo MP4.

    Si alguno falta o la unión falla se devuelve None y el llamador se queda
    con las piezas sueltas — es preferible a perder la grabación.
    """
    parts = [p for p in parts if p and Path(p).exists()]
    if len(parts) < 2:
        return parts[0] if parts else None
    lst = outdir / f".{stem}_lista.txt"
    final = outdir / f"{stem}.mp4"
    try:
        lst.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in parts))
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", str(final)],
            capture_output=True, text=True)
        if r.returncode != 0:
            log.warning("no se pudieron unir los clips: %s", r.stderr[:160])
            return None
        for p in parts:
            Path(p).unlink(missing_ok=True)
        log.info("■ %s (%.1f MB, apertura + cierre)",
                 final.name, final.stat().st_size / 1e6)
        return final
    except Exception as e:
        log.warning("falló la unión: %s", e)
        return None
    finally:
        lst.unlink(missing_ok=True)


def window_title(app_name):
    """Título de la ventana de una app, o '' si no está."""
    try:
        import Quartz
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly |
            Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID)
        for w in wins:
            if app_name.lower() in str(w.get("kCGWindowOwnerName", "")).lower():
                t = str(w.get("kCGWindowName", "") or "")
                if t:
                    return t
    except Exception:
        pass
    return ""


def switch_symbol(symbol, app="TradingView", timeout=12):
    """Pone el gráfico en 'symbol' escribiéndolo en TradingView.

    TradingView abre su buscador con solo empezar a teclear, así que basta con
    poner la app al frente, escribir el símbolo y dar Enter. Se hace antes de
    grabar, nunca durante.

    Necesita permiso de Accesibilidad. Devuelve True solo si el título de la
    ventana confirma el cambio — si no se puede verificar, se avisa y se graba
    igual con lo que haya en pantalla.
    """
    if symbol.upper() in window_title(app).upper():
        log.info("el gráfico ya está en %s", symbol)
        return True

    script = f'''
    tell application "{app}" to activate
    delay 1.2
    tell application "System Events"
        if not (exists process "{app}") then return "sin-proceso"
        tell process "{app}"
            if not frontmost then return "no-al-frente"
            keystroke "{symbol}"
            delay 1.0
            key code 36
        end tell
    end tell
    return "ok"
    '''
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=25)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if "not allowed assistive access" in err or "-25211" in err:
            log.warning("falta permiso de Accesibilidad; no puedo cambiar el símbolo")
            log.warning("Ajustes → Privacidad y seguridad → Accesibilidad → agregá tu Terminal")
            return False
        if out != "ok":
            log.warning("no se pudo cambiar el símbolo (%s)", out or err[:80])
            return False
    except Exception as e:
        log.warning("falló el cambio de símbolo: %s", e)
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if symbol.upper() in window_title(app).upper():
            log.info("gráfico cambiado a %s", symbol)
            return True
        time.sleep(0.5)
    log.warning("no pude confirmar que el gráfico quedó en %s; grabo igual", symbol)
    return False


class Recorder:
    """Envuelve ffmpeg. Un archivo por tramo; los trades largos se parten."""

    def __init__(self, screen, fps, crf, outdir, window=None):
        self.screen = screen
        self.fps = fps
        self.crf = crf
        self.outdir = outdir
        self.window = window      # nombre de app a seguir, o None
        self.proc = None
        self.path = None
        self.started = None

    def _target(self):
        """(pantalla, filtro de recorte). Se resuelve en cada grabación por si
        la ventana se movió o cambió de tamaño."""
        crop = None
        screen = self.screen
        if self.window:
            found = find_window(self.window)
            if found:
                idx, x, y, w, h = found
                screen = str(idx)
                crop = f"crop={w - w % 2}:{h - h % 2}:{x}:{y}"
                log.info("ventana de %s: %dx%d en pantalla %d", self.window, w, h, idx)
            else:
                log.warning("no encontré la ventana de %s; grabo la pantalla %s",
                            self.window, screen)
        return screen, crop

    def start(self, stem):
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.path = self.outdir / f"{stem}.mp4"
        screen, crop = self._target()
        # ancho par: x264 lo exige y algunas pantallas dan ancho impar
        vf = crop if crop else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "avfoundation",
            "-capture_cursor", "1",
            "-framerate", str(self.fps),
            "-i", f"{screen}:none",          # sin audio
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            "-vf", vf,
            str(self.path),
        ]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
        self.started = time.time()
        time.sleep(2)
        if self.proc.poll() is not None:
            err = (self.proc.stderr.read() or b"").decode()[:300]
            log.error("ffmpeg no arrancó: %s", err.strip() or "sin detalle")
            log.error("¿Diste permiso de Grabación de Pantalla?")
            self.proc = None
            return False
        log.info("● grabando → %s", self.path.name)
        return True

    @property
    def active(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def minutes(self):
        return (time.time() - self.started) / 60 if self.started else 0

    def stop_process(self):
        """Cierra ffmpeg con SIGINT para que escriba el índice del MP4.

        Matarlo de golpe deja el archivo sin el 'moov atom' y no se puede
        reproducir, así que hay que darle tiempo a terminar.
        """
        if not self.proc:
            return
        try:
            self.proc.send_signal(signal.SIGINT)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def stop(self):
        if not self.proc:
            return None
        try:
            self.proc.send_signal(signal.SIGINT)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        path = self.path
        self.proc = None
        if path and path.exists() and path.stat().st_size > 0:
            log.info("■ guardado %s (%.1f MB)", path.name,
                     path.stat().st_size / 1e6)
            return path
        log.warning("la grabación salió vacía")
        return None


# ── Contexto del trade ──────────────────────────────────────────────────────
def journal_rows():
    rows = []
    if JOURNAL.exists():
        try:
            rows = list(csv.DictReader(JOURNAL.open(newline="")))
        except Exception:
            pass
    if not rows:
        try:
            r = requests.get(f"{RAILWAY_URL}/journal/csv?secret={RAILWAY_SECRET}",
                             timeout=10)
            rows = list(csv.DictReader(r.text.splitlines()))
        except Exception:
            pass
    return rows


def strategy_for(symbol, side):
    """Indicador más reciente que disparó este símbolo y lado."""
    best, best_ts = None, ""
    for r in journal_rows():
        if r.get("symbol", "").upper() == symbol.upper() and \
           r.get("action", "").lower() == side.lower():
            if r.get("timestamp", "") >= best_ts:
                best_ts, best = r.get("timestamp", ""), r.get("strategy")
    return best or "sin-indicador"


def outcome_for(position_id, wait=25):
    """Cómo terminó: TP, SL, cierre normal — y el P&L.

    El trade tarda unos segundos en aparecer en el historial, así que se
    reintenta un rato antes de rendirse.
    """
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            trades = json.loads(TRADES.read_text())
        except Exception:
            trades = []
        for t in trades:
            if str(t.get("positionId")) != str(position_id):
                continue
            pnl = float(t.get("pnl") or 0)
            label = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "FLAT")
            sl, tp, ex = t.get("signalSL"), t.get("signalTP"), t.get("exit")
            if sl and tp and ex:
                try:
                    sl, tp, ex = float(sl), float(tp), float(ex)
                    tol = abs(tp - sl) * 0.05
                    if abs(ex - tp) <= tol:
                        label = "TP"
                    elif abs(ex - sl) <= tol:
                        label = "SL"
                except Exception:
                    pass
            return label, pnl
        time.sleep(3)
    return None, None


def safe(s):
    return re.sub(r"[^A-Za-z0-9_.+-]", "", str(s).replace(" ", "-"))[:40]


# ── Bucle principal ─────────────────────────────────────────────────────────
def run(args):
    cfg = load_env(CONFIG)
    if not cfg.get("TL_EMAIL"):
        sys.exit("faltan credenciales en config.env")

    broker = Broker(cfg)
    if not broker.authenticate():
        sys.exit(1)

    rec = Recorder(args.screen, args.fps, args.crf, Path(args.outdir), args.window)
    # posición que se está grabando: {id, symbol, side, strategy, part}
    current = None
    known = broker.open_positions() or {}
    if known:
        log.info("ya hay %d posición(es) abierta(s); se ignoran hasta que cierren",
                 len(known))
    log.info("esperando trades… (Ctrl+C para salir)")

    stopping = False

    def bye(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, bye)
    signal.signal(signal.SIGTERM, bye)

    while not stopping:
        positions = broker.open_positions()

        if positions is None:          # error de red: no cortar la grabación
            time.sleep(POLL_SECONDS)
            continue

        # ¿se cerró la que estábamos grabando?
        if current and current["id"] not in positions:
            log.info("posición %s cerrada", current["id"][-8:])
            time.sleep(SETTLE_SECS)    # dejar ver la vela final
            path = rec.stop() if rec.active else None

            if args.clips:
                # El gráfico recién cerrado todavía muestra la entrada, el SL y
                # el TP dibujados por el indicador, así que grabar unos minutos
                # DESPUÉS del cierre captura el trade completo y resuelto —
                # sin tener que dejar la cámara corriendo tres días.
                if args.auto_symbol and args.window:
                    switch_symbol(current["symbol"], args.window)
                if rec.start(current["stem"] + "_cierre"):
                    time.sleep(args.exit_minutes * 60)
                    tail = rec.stop()
                    if tail:
                        path = join_clips(current["stem"], [path, tail],
                                          Path(args.outdir)) or tail
            if path:
                label, pnl = outcome_for(current["id"])
                if label:
                    money = f"{'+' if (pnl or 0) >= 0 else ''}{pnl:.2f}"
                    final = path.with_name(f"{path.stem}_{label}_{money}.mp4")
                else:
                    final = path.with_name(f"{path.stem}_cerrado.mp4")
                    log.warning("no apareció el resultado a tiempo; sin P&L en el nombre")
                try:
                    path.rename(final)
                    log.info("→ %s", final.name)
                except Exception as e:
                    log.warning("no se pudo renombrar: %s", e)
            current = None

        # partir grabaciones largas para que los archivos no crezcan sin control
        elif current and args.clips and rec.active and \
                rec.minutes >= args.entry_minutes:
            log.info("clip de entrada listo; espero el cierre del trade")
            rec.stop()

        elif current and not args.clips and rec.active and \
                rec.minutes >= args.max_minutes:
            log.info("tramo de %d min completo, sigo en otro archivo", args.max_minutes)
            rec.stop()
            current["part"] += 1
            rec.start(f"{current['stem']}_parte{current['part']}")

        # ¿se abrió una nueva?
        if not current:
            fresh = [p for p in positions if p not in known]
            if fresh:
                pid = fresh[0]
                info = positions[pid]
                sym, side = info["symbol"], info["side"]
                strat = strategy_for(sym, side)
                direction = "Long" if side.lower() == "buy" else "Short"
                stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
                stem = f"{stamp}_{safe(sym)}_{direction}_{safe(strat)}"
                log.info("▶ trade nuevo: %s %s @ %s (%s)",
                         sym, direction, info["entry"], strat)
                # Poner el gráfico en el símbolo operado ANTES de grabar, para
                # que el video no muestre otro par.
                if args.auto_symbol and args.window:
                    switch_symbol(sym, args.window)
                if rec.start(stem):
                    current = {"id": pid, "stem": stem, "part": 1,
                               "symbol": sym}
                else:
                    log.error("no se pudo grabar este trade; sigo esperando")
                    known = dict(positions)

        known = dict(positions)
        time.sleep(POLL_SECONDS)

    log.info("cerrando…")
    if rec.active:
        path = rec.stop()
        if path:
            path.rename(path.with_name(f"{path.stem}_interrumpido.mp4"))


def main():
    p = argparse.ArgumentParser(description="Graba la pantalla mientras hay un trade abierto")
    p.add_argument("--screen", default="1", help="pantalla a grabar (--list-screens)")
    p.add_argument("--fps", type=int, default=10, help="cuadros por segundo (10 va bien para gráficos)")
    p.add_argument("--crf", type=int, default=26, help="calidad: menor = mejor y más pesado")
    p.add_argument("--outdir", default=str(OUTDIR), help="carpeta de salida")
    p.add_argument("--max-minutes", type=int, default=MAX_MINUTES,
                   help="minutos por archivo antes de partir")
    p.add_argument("--window", default="TradingView",
                   help="grabar solo la ventana de esta app; --window '' para pantalla completa")
    p.add_argument("--no-auto-symbol", dest="auto_symbol", action="store_false",
                   help="no cambiar el símbolo del gráfico al abrirse un trade")
    p.add_argument("--symbol-test", metavar="SIMBOLO",
                   help="probar el cambio de símbolo (ej: --symbol-test NAS100)")
    p.add_argument("--full", dest="clips", action="store_false",
                   help="grabar el trade entero en vez de arranque + cierre")
    p.add_argument("--entry-minutes", type=float, default=3,
                   help="minutos a grabar desde que abre el trade")
    p.add_argument("--exit-minutes", type=float, default=2,
                   help="minutos a grabar cuando el trade cierra")
    p.add_argument("--list-screens", action="store_true")
    p.add_argument("--test", type=int, metavar="SEGS",
                   help="graba N segundos ya, para probar permisos y pantalla")
    args = p.parse_args()

    # Bajo launchd la salida ya se redirige al log, así que escribir también al
    # archivo duplicaría cada línea. Solo se agrega el archivo en modo terminal.
    handlers = [logging.StreamHandler()]
    if sys.stdout.isatty():
        handlers.append(
            logging.FileHandler(Path.home() / "tradelocker-bot" / "trade_recorder.log"))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S",
        handlers=handlers,
    )

    if args.list_screens:
        list_screens()
        return

    if args.symbol_test:
        ok = switch_symbol(args.symbol_test, args.window or "TradingView")
        print(("\n✅  Cambió a " if ok else "\n⚠️   No se pudo cambiar a ")
              + args.symbol_test + "\n")
        return

    if args.test:
        rec = Recorder(args.screen, args.fps, args.crf, Path(args.outdir), args.window)
        log.info("prueba de %ds…", args.test)
        if not rec.start(f"prueba_{datetime.now():%H%M%S}"):
            sys.exit(1)
        time.sleep(args.test)
        path = rec.stop()
        if path:
            print(f"\n✅  Listo: {path}\n    Abrilo para confirmar que es la pantalla correcta.\n")
        return

    run(args)


if __name__ == "__main__":
    main()
