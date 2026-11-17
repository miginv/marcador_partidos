# Modo mensajes del marcador 24x8: reloj y API HTTP tipo Awtrix (/api/notify, /api/custom,
# /api/settings, /api/reboot, /api/scoreboard) mientras no haya partido. Cada minuto mira
# la lista; 15 min antes de un partido reinicia en modo marcador (modo_fbm).
# Textos de hasta 16 px se quedan fijos y centrados; los mas anchos pasan en scroll.
# Todo sin bloquear: entre fotograma y fotograma se atienden las peticiones.
import gc
import json
import socket
import time
import machine
import network
import modo_fbm
import my_display
import my_shared

MAX_FIJO = 16               # px: hasta aqui texto fijo, mas ancho en scroll
COLA_MAX = 10
PASO_MS = 50                # ms por paso si no llega "scrollspeed" (como la Awtrix)
FIJO_SEG = 4                # texto fijo: 4 s por repeticion (como la Awtrix)
COLOR_RELOJ = (255, 255, 255)   # blanco, como el reloj de la Awtrix
REVISAR_SEG = 60
DESCARGA_SEG = 15 * 60
REFRESCO_SEG = 3600         # sin lista nueva en 1 h: reinicio y se baja al arrancar
OTA_SEG = 6 * 3600

_sta = network.WLAN(network.STA_IF)
_cola = []
_t = {"rev": 0, "desc": 0, "ok": 0, "ota": 0}
_hora_ok = False
_ACENTOS = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
            "°": "º", "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U", "Ñ": "N"}


# ---------- hora ----------

def _offset_es(t):
    """UTC+1 en invierno, UTC+2 entre el ultimo domingo de marzo y el de octubre."""
    y = time.localtime(t)[0]

    def ultimo_domingo(mes):
        d = 31
        while time.localtime(time.mktime((y, mes, d, 1, 0, 0, 0, 0)))[6] != 6:
            d -= 1
        return time.mktime((y, mes, d, 1, 0, 0, 0, 0))
    return 7200 if ultimo_domingo(3) <= t < ultimo_domingo(10) else 3600


def _sync_hora():
    global _hora_ok
    try:
        import ntptime
        ntptime.settime()                       # RTC en UTC, como el marcador
        _hora_ok = time.localtime()[0] >= 2024
    except Exception as e:
        print("[NTP] fallo:", e)


# ---------- pantalla ----------

def _limpia(txt):
    return "".join(_ACENTOS.get(c, c) for c in str(txt))


def _ancho(txt):
    return sum(my_display._ancho_scroll(c) + 1 for c in txt) - 1 if txt else 0


def _pinta(txt, x, color):
    my_display.fb.fill(0)
    for c in txt:
        my_display.draw_char_at_position(c, x, 3)
        x += my_display._ancho_scroll(c) + 1
    my_display.show_framebuffer(color)


def _color(c, defecto=(255, 255, 255)):
    try:
        if isinstance(c, str):
            c = c.lstrip("#")
            return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
        return (int(c[0]), int(c[1]), int(c[2]))
    except Exception:
        return defecto


class _Mensaje:
    """Un mensaje en pantalla; paso() dibuja un fotograma y dice si sigue."""

    def __init__(self, p):
        txt = _limpia(p.get("text", ""))
        if p.get("textCase") == 1:              # como la Awtrix: 1 minusculas, 2 mayusculas,
            txt = txt.lower()                   # cualquier otro valor tal cual
        elif p.get("textCase") == 2:
            txt = txt.upper()
        self.txt = txt
        self.color = _color(p.get("color"))
        self.w = _ancho(txt)
        self.scroll = self.w > MAX_FIJO
        try:
            self.paso_ms = max(10, min(500, int(p.get("scrollspeed", p.get("scrollSpeed", PASO_MS)))))
        except (TypeError, ValueError):
            self.paso_ms = PASO_MS
        try:
            self.vueltas = max(1, min(8, int(p.get("repeat", 1))))
        except (TypeError, ValueError):
            self.vueltas = 1
        dur = p.get("duration") or FIJO_SEG * self.vueltas
        self.fin = time.ticks_add(time.ticks_ms(), int(dur) * 1000)
        self.k = 0
        self.prox = time.ticks_ms()

    def paso(self):
        if time.ticks_diff(time.ticks_ms(), self.prox) < 0:
            return True
        if not self.scroll:
            if self.k == 0:
                _pinta(self.txt, (my_display.WIDTH - self.w) // 2, self.color)
                self.k = 1
            return time.ticks_diff(self.fin, time.ticks_ms()) > 0
        _pinta(self.txt, my_display.WIDTH - self.k, self.color)
        self.k += 1
        self.prox = time.ticks_add(self.prox, self.paso_ms)
        if self.k > self.w + my_display.WIDTH:
            self.k = 0
            self.vueltas -= 1
        return self.vueltas > 0


def _reloj(estado):
    """Dibuja HH:MM (dos puntos parpadeando) solo cuando cambia."""
    if _hora_ok:
        t = time.time()
        lt = time.localtime(t + _offset_es(t))
        txt = "%02d%s%02d" % (lt[3], ":" if lt[5] % 2 == 0 else " ", lt[4])
    else:
        txt = "--:--"
    if txt != estado.get("reloj"):
        estado["reloj"] = txt
        my_display.fb.fill(0)
        x = (my_display.WIDTH - _ancho(txt.replace(" ", ":"))) // 2
        for c in txt:
            if c != " ":
                my_display.draw_char_at_position(c, x, 3)
            x += my_display._ancho_scroll(":" if c == " " else c) + 1
        my_display.show_framebuffer(COLOR_RELOJ)


# ---------- HTTP ----------

def _responder(cl, codigo, cuerpo):
    txt = "OK" if codigo == 200 else "Service Unavailable" if codigo == 503 else "Not Found"
    cl.send("HTTP/1.1 %d %s\r\nContent-Type: application/json\r\nConnection: close\r\n"
            "Content-Length: %d\r\n\r\n%s" % (codigo, txt, len(cuerpo), cuerpo))


def _leer(cl):
    cl.settimeout(3)
    raw = b""
    while b"\r\n\r\n" not in raw and len(raw) < 4096:
        c = cl.recv(512)
        if not c:
            break
        raw += c
    cab, _, cuerpo = raw.partition(b"\r\n\r\n")
    largo = 0
    for l in cab.split(b"\r\n"):
        if l.lower().startswith(b"content-length:"):
            try:
                largo = int(l.split(b":", 1)[1].strip())
            except ValueError:
                pass
    while len(cuerpo) < largo and len(cuerpo) < 4096:
        c = cl.recv(512)
        if not c:
            break
        cuerpo += c
    linea = cab.split(b"\r\n", 1)[0].decode("utf-8", "ignore")
    return linea, cuerpo.decode("utf-8", "ignore")


def _encolar(cl, p):
    if len(_cola) >= COLA_MAX:
        _responder(cl, 503, '{"success": false, "error": "queue full"}')
        print("[MSG] cola llena")
    else:
        _cola.append(p)
        _responder(cl, 200, '{"success": true}')
        print("[MSG] encolado, cola:", len(_cola))


def _atender(cl):
    try:
        linea, cuerpo = _leer(cl)
        if linea.startswith("POST /api/notify") or linea.startswith("POST /api/custom"):
            _encolar(cl, json.loads(cuerpo))
        elif linea.startswith("POST /api/scoreboard"):
            d = json.loads(cuerpo)
            d["_type"] = "scoreboard"
            _encolar(cl, d)
        elif linea.startswith("GET /api/settings"):
            _responder(cl, 200, json.dumps({"BRI": int(my_shared.BRIGHTNESS * 100)}))
        elif linea.startswith("POST /api/settings"):
            d = json.loads(cuerpo)
            if "BRI" in d:
                my_shared.BRIGHTNESS = max(0, min(100, int(float(d["BRI"])))) / 100.0
            _responder(cl, 200, json.dumps({"success": True, "BRI": int(my_shared.BRIGHTNESS * 100)}))
        elif linea.startswith("POST /api/reboot"):
            _responder(cl, 200, '{"success": true}')
            cl.close()
            time.sleep(1)
            machine.reset()
        else:
            _responder(cl, 404, '{"success": false}')
    except Exception as e:
        print("[MSG] peticion:", e)
        try:
            _responder(cl, 404, '{"success": false}')
        except Exception:
            pass
    finally:
        try:
            cl.close()
        except Exception:
            pass


def _marcador_msg(d):
    """Marcador enviado por /api/scoreboard (bloquea lo que dura, como en la Awtrix)."""
    try:
        my_display.display_scoreboard(
            str(d.get("local", "LOC")), str(d.get("visitor", "VIS")),
            d.get("local_color", [255, 255, 255]), d.get("visitor_color", [255, 255, 255]),
            int(d.get("local_pts", 0)), int(d.get("visitor_pts", 0)),
            int(d.get("minutes", 0)), int(d.get("seconds", 0)), int(d.get("quarter", 1)))
    except Exception as e:
        print("[MSG] scoreboard:", e)


# ---------- partidos ----------

def _revisar():
    ahora = time.time()
    if not _hora_ok and _sta.isconnected():
        _sync_hora()
    if ahora - _t["ota"] >= OTA_SEG:
        _t["ota"] = ahora
        try:
            modo_fbm.actualizar()               # si instala algo, reinicia
        except Exception as e:
            print("[OTA] error:", e)
    if ahora - _t["desc"] >= DESCARGA_SEG:
        _t["desc"] = ahora
        if modo_fbm.descargar():
            _t["ok"] = ahora
    p = modo_fbm.partido_cercano()
    if p:
        print("[MODO] partido cerca:", p.get("hora"), p.get("local"), "vs", p.get("visit"))
        my_display.clear()
        modo_fbm.cambiar("marcador")
    if ahora - _t["ok"] >= REFRESCO_SEG:
        print("[MODO] sin lista nueva en 1 h: reinicio")
        modo_fbm.cambiar("mensajes")
    if not _sta.isconnected():
        import wifi_portal
        wifi_portal.conectar()


# ---------- arranque ----------

_sync_hora()
try:
    modo_fbm.actualizar()
except Exception as _e:
    print("[OTA] error:", _e)
if modo_fbm.descargar():
    print("[MODO] lista descargada")
_t["ota"] = _t["ok"] = _t["desc"] = _t["rev"] = time.time()
gc.collect()

_srv = socket.socket()
_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
_srv.bind(socket.getaddrinfo("0.0.0.0", 80)[0][-1])
_srv.listen(2)
_srv.setblocking(False)
_ip = _sta.ifconfig()[0] if _sta.isconnected() else ""
print("[MSG] API Awtrix en", _ip, "puerto 80, libre", gc.mem_free())
if _ip:
    _cola.append({"text": _ip, "color": [0, 255, 0], "repeat": 1})

_actual = None
_estado = {}
while True:
    try:
        cl, _ = _srv.accept()
    except OSError:
        cl = None
    if cl is not None:
        _atender(cl)

    if _actual is None and _cola:
        p = _cola.pop(0)
        if p.get("_type") == "scoreboard":
            _marcador_msg(p)
        else:
            _actual = _Mensaje(p)
        _estado.clear()
    if _actual is not None:
        if not _actual.paso():
            _actual = None
            _estado.clear()
    else:
        _reloj(_estado)
        if time.time() - _t["rev"] >= REVISAR_SEG:
            _t["rev"] = time.time()
            try:
                _revisar()
            except Exception as e:
                print("[MODO] error revisando:", e)
    time.sleep_ms(10)
