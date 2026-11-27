# Pantalla 16x16: un solo programa con tres modos, sin reinicios entre ellos.
#   1) posesion  si el emisor de la MONDO esta mandando (UDP 4210 y/o Bluetooth LE, ver
#                posesion16 y ble16; las lineas repetidas por los dos canales se descartan)
#   2) marcador  si hay partido de la lista dentro de su ventana (servidor propio, relay.json)
#   3) mensajes  el resto del tiempo: reloj + API HTTP tipo Awtrix (puerto 80)
# API: POST /api/notify | /api/custom (mensaje), GET/POST /api/settings (BRI 0-100,
# RELAY_CLAVE/RELAY_URL, BLE 1/0 = activar/desactivar el Bluetooth y reiniciar), POST /api/reboot, GET /api/version, POST /api/posesion
# {"cmd": "24"|"14"|"R"|"S"|"OFF"} (pruebas), POST /api/icon?name=<n> (cuerpo = GIF ->
# /ICONS/<n>.gif, para iconos propios de hasta 16x8).
import gc
import json
import os
import socket
import time
import machine
import network
import pantalla16
import sistema16
import mensajes16
import posesion16
import marcador16

PUERTO_UDP = 4210
COLA_MAX = 10
MSG_CADUCA_SEG = 15 * 60     # un mensaje que espera mas de esto (p. ej. durante un partido) se tira
REVISAR_SEG = 60
OTA_SEG = 6 * 3600

sta = network.WLAN(network.STA_IF)
sistema16.leer_ajustes()
pos = posesion16.Posesion()
cola = []
_t = {"rev": 0, "ota": 0}


def version():
    return sistema16.version_local()


# ---------- lineas de posesion (WiFi y Bluetooth) ----------

_seq = {"n": None, "t": 0}
SEQ_REINICIO_MS = 3000       # sin nada en 3 s se acepta cualquier numero (emisor reiniciado)


def _linea_pos(linea):
    """"POS ... #n": la misma linea llega por WiFi y por BLE; solo vale la primera."""
    if " #" in linea:
        linea, _, n = linea.rpartition(" #")
        try:
            n = int(n) & 0xFFFF
        except ValueError:
            n = None
        ahora = time.ticks_ms()
        if n is not None:
            u = _seq["n"]
            if (u is not None and time.ticks_diff(ahora, _seq["t"]) < SEQ_REINICIO_MS
                    and not 0 < (n - u) & 0xFFFF < 0x8000):
                return                    # repetida o vieja
            _seq["n"], _seq["t"] = n, ahora
    pos.mensaje(linea)


# ---------- UDP (Raspberry de la MONDO) ----------

udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(socket.getaddrinfo("0.0.0.0", PUERTO_UDP)[0][-1])
udp.setblocking(False)


def _udp():
    for _ in range(20):
        try:
            datos, addr = udp.recvfrom(256)
        except OSError:
            return
        txt = datos.decode("utf-8", "ignore").strip()
        for linea in txt.split("\n"):
            linea = linea.strip()
            if linea == "VERSION?":
                r = {"tipo": "16x16", "version": version(), "ip": sta.ifconfig()[0],
                     "modo": modo_actual[0]}
                try:
                    udp.sendto(json.dumps(r).encode(), addr)
                except OSError:
                    pass
            elif linea:
                _linea_pos(linea)


# ---------- HTTP ----------

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(socket.getaddrinfo("0.0.0.0", 80)[0][-1])
srv.listen(2)
srv.setblocking(False)


def _responder(cl, codigo, cuerpo):
    txt = {200: "OK", 400: "Bad Request", 503: "Service Unavailable"}.get(codigo, "Not Found")
    cl.send(("HTTP/1.1 %d %s\r\nContent-Type: application/json\r\nConnection: close\r\n"
             "Content-Length: %d\r\n\r\n%s" % (codigo, txt, len(cuerpo), cuerpo)).encode())


def _cabecera(cl):
    cl.settimeout(3)
    raw = b""
    while b"\r\n\r\n" not in raw and len(raw) < 4096:
        c = cl.recv(512)
        if not c:
            break
        raw += c
    cab, _, resto = raw.partition(b"\r\n\r\n")
    largo = 0
    for l in cab.split(b"\r\n"):
        if l.lower().startswith(b"content-length:"):
            try:
                largo = int(l.split(b":", 1)[1].strip())
            except ValueError:
                pass
    linea = cab.split(b"\r\n", 1)[0].decode("utf-8", "ignore")
    return linea, resto, largo


def _cuerpo(cl, resto, largo, maximo=4096):
    while len(resto) < min(largo, maximo):
        c = cl.recv(512)
        if not c:
            break
        resto += c
    return resto.decode("utf-8", "ignore")


def _guardar_icono(cl, ruta, resto, largo):
    nombre = ""
    if "name=" in ruta:
        nombre = ruta.split("name=", 1)[1].split("&")[0]
    nombre = "".join(c for c in nombre if c.isalpha() or c.isdigit() or c in "_-")
    if not nombre or not 0 < largo <= 32768:
        return _responder(cl, 400, '{"success": false, "error": "name/size"}')
    try:
        os.mkdir("/ICONS")
    except OSError:
        pass
    n = 0
    with open("/ICONS/%s.gif" % nombre, "wb") as f:
        f.write(resto)
        n = len(resto)
        while n < largo:
            c = cl.recv(1024)
            if not c:
                break
            f.write(c)
            n += len(c)
    _responder(cl, 200, json.dumps({"success": n == largo, "bytes": n}))


def _atender(cl):
    try:
        linea, resto, largo = _cabecera(cl)
        metodo, _, ruta = linea.partition(" ")
        ruta = ruta.split(" ")[0]
        if metodo == "POST" and ruta.startswith("/api/icon"):
            return _guardar_icono(cl, ruta, resto, largo)
        cuerpo = _cuerpo(cl, resto, largo)
        if metodo == "POST" and (ruta.startswith("/api/notify") or ruta.startswith("/api/custom")):
            if len(cola) >= COLA_MAX:
                return _responder(cl, 503, '{"success": false, "error": "queue full"}')
            p = json.loads(cuerpo)
            p["_t"] = time.time()
            cola.append(p)
            _responder(cl, 200, '{"success": true}')
        elif ruta.startswith("/api/settings"):
            if metodo == "POST":
                d = json.loads(cuerpo)
                if "RELAY_CLAVE" in d:
                    r = {"clave": str(d["RELAY_CLAVE"])}
                    if d.get("RELAY_URL"):
                        r["url"] = str(d["RELAY_URL"])
                    with open("relay.json", "w") as f:
                        json.dump(r, f)
                    marcador.__init__()
                    marcador.bajar_lista()
                    return _responder(cl, 200, json.dumps({"success": True, "relay": r.get("url", "defecto"),
                                                           "clave": bool(r["clave"])}))
                if "BLE" in d:        # 1 = reintentar el Bluetooth, 0 = desactivarlo (reinicia)
                    if d["BLE"]:
                        try:
                            os.remove("ble.fallo")
                        except OSError:
                            pass
                    else:
                        with open("ble.fallo", "w") as f:
                            f.write("0")
                    _responder(cl, 200, '{"success": true, "reinicio": true}')
                    cl.close()
                    time.sleep(1)
                    machine.reset()
                if "BRI" in d:
                    b = max(1, min(100, int(float(d["BRI"])))) / 100.0
                    sistema16.my_shared.BRIGHTNESS = b
                    sistema16.guardar_ajustes(brillo=b)
                    pos.pintado = None
                    marcador.olvidar()
                    mensajes16.olvidar()
            _responder(cl, 200, json.dumps({"success": True,
                                            "BRI": int(sistema16.my_shared.BRIGHTNESS * 100)}))
        elif ruta.startswith("/api/version"):
            _responder(cl, 200, json.dumps({"tipo": "16x16", "version": version(), "modo": modo_actual[0],
                                            "relay": bool(marcador.url), "libre": gc.mem_free(),
                                            "ble": ble[0].nombre if ble[0] else None,
                                            "ble_conectado": bool(ble[0] and ble[0].conectados)}))
        elif metodo == "POST" and ruta.startswith("/api/posesion"):
            d = json.loads(cuerpo or "{}")
            pos.mensaje("POS " + str(d.get("cmd", "")))
            _responder(cl, 200, '{"success": true}')
        elif metodo == "POST" and ruta.startswith("/api/reboot"):
            _responder(cl, 200, '{"success": true}')
            cl.close()
            time.sleep(1)
            machine.reset()
        else:
            _responder(cl, 404, '{"success": false}')
    except Exception as e:
        print("[HTTP]", e)
        try:
            _responder(cl, 400, '{"success": false}')
        except Exception:
            pass
    finally:
        try:
            cl.close()
        except Exception:
            pass


def _http():
    try:
        cl, _ = srv.accept()
    except OSError:
        return
    _atender(cl)


ble = [None]


def _ble():
    if ble[0]:
        for d in ble[0].leer():
            for linea in d.decode("utf-8", "ignore").split("\n"):
                linea = linea.strip()
                if linea:
                    _linea_pos(linea)


def atender():
    _udp()
    _ble()
    _http()


def _cortar_mensaje():
    """Durante un mensaje: atiende la red y corta si entra la posesion."""
    atender()
    return pos.activo()


# ---------- revision periodica ----------

def revisar():
    if not sta.isconnected():
        import wifi_portal
        wifi_portal.conectar()
    if not sistema16.hora_ok[0] and sta.isconnected():
        sistema16.sync_hora()
    marcador.revisar()
    if modo_actual[0] == "mensajes" and time.time() - _t["ota"] >= OTA_SEG:
        _t["ota"] = time.time()
        sistema16.actualizar(_aviso_ota)


def _aviso_ota(v):
    mensajes16.mostrar({"text": "OTA " + v, "color": [0, 120, 255], "duration": 2})


# ---------- arranque ----------

pantalla16.clear()
if sta.isconnected():
    sistema16.sync_hora()
    try:
        sistema16.actualizar(_aviso_ota)
    except Exception as _e:
        print("[OTA]", _e)
_t["ota"] = _t["rev"] = time.time()
try:                         # el Bluetooth lo arranca boot.py (ver ble16)
    import ble16
    ble[0] = ble16.activo
except Exception as _e:
    print("[BLE]", _e)
marcador = marcador16.Marcador()
marcador.bajar_lista()
modo_actual = ["mensajes"]
_ip = sta.ifconfig()[0] if sta.isconnected() else ""
print("[16x16]", version(), "IP", _ip, "relay", bool(marcador.url), "BLE",
      ble[0].nombre if ble[0] else None, "libre", gc.mem_free())
if _ip:
    cola.append({"text": _ip, "color": [0, 255, 0], "icon": "32930", "_t": time.time()})


def _modo(m):
    if m != modo_actual[0]:
        print("[MODO]", modo_actual[0], "->", m)
        modo_actual[0] = m
        pos.pintado = None
        marcador.olvidar()
        mensajes16.olvidar()


while True:
    try:
        atender()
        if pos.activo():
            _modo("posesion")
            pos.pintar()
            time.sleep_ms(10)
            continue
        if marcador.activo():
            _modo("marcador")
            marcador.paso()
        else:
            _modo("mensajes")
            if cola:
                p = cola.pop(0)
                if time.time() - p.get("_t", 0) <= MSG_CADUCA_SEG:
                    mensajes16.mostrar(p, _cortar_mensaje)
                mensajes16.olvidar()
            else:
                mensajes16.reloj()
        if time.time() - _t["rev"] >= REVISAR_SEG:
            _t["rev"] = time.time()
            revisar()
        time.sleep_ms(20)
    except Exception as e:
        import sys
        sys.print_exception(e)
        time.sleep(2)
