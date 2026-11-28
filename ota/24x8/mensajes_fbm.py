# Modo mensajes del marcador 24x8: reloj y API HTTP tipo Awtrix (/api/notify, /api/custom,
# /api/settings, /api/reboot, /api/scoreboard) mientras no haya partido. Cada minuto mira
# la lista; 15 min antes de un partido reinicia en modo marcador (modo_fbm).
# Los mensajes se pintan con el codigo de la Awtrix (awtrix24: icono 8 px + texto, scroll
# si el texto ocupa mas de 12 px). Mientras se muestra uno, las peticiones esperan.
import gc
import json
import socket
import time
import machine
import network
import modo_fbm
import my_display
import awtrix24
import my_shared
import ajustes_remotos

COLA_MAX = 10
REVISAR_SEG = 60
DESCARGA_SEG = 15 * 60
REFRESCO_SEG = 3600         # sin lista nueva en 1 h: reinicio y se baja al arrancar
OTA_SEG = 6 * 3600

_sta = network.WLAN(network.STA_IF)
_cola = []
_t = {"rev": 0, "desc": 0, "ok": 0, "ota": 0}
_hora_ok = False

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


# ---------- pantalla: mismo codigo que la Awtrix (awtrix24) ----------

ICONOS_AUTO_POWER = ("858", "2012", "61396", "34394", "1545", "55027", "2422", "32930",
                     "55274", "8644")


def _reloj(estado):
    """Reloj de la Awtrix, redibujado solo cuando cambia (parpadeo de los dos puntos)."""
    if _hora_ok:
        t = time.time()
        lt = time.localtime(t + _offset_es(t))
        clave = (lt[3], lt[4], lt[5] % 2 == 0)
    else:
        clave = ("--", "--", True)
    if clave != estado.get("reloj"):
        estado["reloj"] = clave
        h, m, sep = clave
        awtrix24.display_clock_frame(h if isinstance(h, str) else "%02d" % h,
                                     m if isinstance(m, str) else "%02d" % m, sep)


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
            if "RELAY_CLAVE" in d or "RELAY_SECRETO" in d:
                # clave del servidor del marcador y secreto de las WiFis -> relay.json
                # (clave "" = FBM directa); se conserva lo que no venga
                try:
                    with open("relay.json") as f:
                        r = json.load(f)
                except Exception:
                    r = {}
                if "RELAY_CLAVE" in d:
                    r["clave"] = str(d["RELAY_CLAVE"])
                if d.get("RELAY_URL"):
                    r["url"] = str(d["RELAY_URL"])
                if "RELAY_SECRETO" in d:
                    r["secreto"] = str(d["RELAY_SECRETO"])
                with open("relay.json", "w") as f:
                    json.dump(r, f)
                _responder(cl, 200, json.dumps({"success": True, "relay": r.get("url", "defecto"),
                                                "clave": bool(r.get("clave")),
                                                "secreto": bool(r.get("secreto"))}))
                return
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

def _brillo():
    b = ajustes_remotos.brillo()
    if b:
        my_shared.BRIGHTNESS = b


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
        if ajustes_remotos.bajar():
            _brillo()
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
ajustes_remotos.bajar()
_brillo()
if _sta.isconnected():
    for _ic in ICONOS_AUTO_POWER:
        try:
            awtrix24.download_icon(_ic)
        except Exception as _e:
            print("[ICONO]", _ic, _e)
        gc.collect()
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
    _cola.append({"text": _ip, "color": [0, 255, 0], "icon": "32930", "repeat": 1})

_estado = {}
while True:
    try:
        cl, _ = _srv.accept()
    except OSError:
        cl = None
    if cl is not None:
        _atender(cl)

    if _cola:
        p = _cola.pop(0)
        print("[MSG] mostrando, pendientes:", len(_cola))
        if p.get("_type") == "scoreboard":
            _marcador_msg(p)
        else:
            awtrix24.process_awtrix(p)
        _estado.clear()
    else:
        _reloj(_estado)
        if time.time() - _t["rev"] >= REVISAR_SEG:
            _t["rev"] = time.time()
            try:
                _revisar()
            except Exception as e:
                print("[MODO] error revisando:", e)
    time.sleep_ms(20)
