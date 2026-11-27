# Modo pabellon: la placa solo hace de reloj de posesion y escucha al emisor de la MONDO por
# los dos canales a la vez, WiFi (UDP 4210) y Bluetooth LE (ble16, lo arranca boot.py); las
# copias repetidas se descartan por el numero de secuencia (posesion16.linea). Sin marcador
# de la federacion, ni mensajes, ni GIF: con el Bluetooth no cabe todo en la memoria de la C3.
# Siempre muestra la posesion (24 al arrancar, preparada). No depende de la WiFi: la conecta en
# segundo plano (sin esperar ni abrir portal) y, si no hay, sigue solo por Bluetooth.
# Todo tiene que caber en los 64 KB con los que arranca MicroPython (si crece, deja sin
# memoria a la WiFi): nada de GIF, ni HTTPS, ni OTA (ver boot).
# API: GET /api/version, GET/POST /api/settings (BRI 0-100; PABELLON 0 = volver al modo
# normal y reiniciar), POST /api/posesion {"cmd": ...}, POST /api/reboot.
import gc
import json
import socket
import time
import machine
import network
import pantalla16
import sistema16
import posesion16
import ble16
gc.collect()

PUERTO_UDP = 4210
GC_MS = 1000
WDT_MS = 90000

WIFI_REINTENTO_MS = 20000    # sin WiFi: cada 20 s prueba la siguiente red guardada

sta = network.WLAN(network.STA_IF)
sistema16.leer_ajustes()
pos = posesion16.Posesion()
ble = ble16.activo
_t = {"gc": 0, "wifi": 0, "red": 0, "ip": ""}
modo = ["espera"]


def _redes():
    try:
        with open("config.json") as f:
            return [c for c in json.load(f).get("wifi_credentials", []) if c.get("ssid")]
    except Exception:
        return []


REDES = _redes()


def _wifi():
    """Sin bloquear: lanza la conexion y vuelve; si a los 20 s no hay, prueba la siguiente."""
    if sta.isconnected():
        if not _t["ip"]:
            _t["ip"] = sta.ifconfig()[0]
            print("[WIFI] conectada", _t["ip"])
        return
    if _t["ip"]:
        print("[WIFI] perdida")
        _t["ip"] = ""
    if not REDES or (_t["wifi"] and time.ticks_diff(time.ticks_ms(), _t["wifi"]) < WIFI_REINTENTO_MS):
        return
    _t["wifi"] = time.ticks_ms()
    c = REDES[_t["red"] % len(REDES)]
    _t["red"] += 1
    try:
        sta.active(True)
        try:
            sta.disconnect()
        except Exception:
            pass
        sta.connect(c["ssid"], c.get("password", ""))
    except Exception as e:
        print("[WIFI]", e)


sta.active(True)
try:
    network.hostname("marcador-" + "".join("%02x" % b for b in sta.config("mac")[-2:]))
except Exception:
    pass


def version():
    return sistema16.version_local()


def _estado():
    import esp32
    return {"tipo": "16x16", "version": version(), "modo": "pabellon-" + modo[0],
            "ip": _t["ip"], "vista": pos.vista, "reloj": pos.reloj, "posesion": pos.texto(), "ble": ble.nombre if ble else None,
            "ble_conectado": bool(ble and ble.conectados), "libre": gc.mem_free(),
            "heap": gc.mem_free() + gc.mem_alloc(),
            "sistema": sum(h[1] for h in esp32.idf_heap_info(esp32.HEAP_DATA))}


gc.collect()
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(socket.getaddrinfo("0.0.0.0", PUERTO_UDP)[0][-1])
udp.setblocking(False)
gc.collect()
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(socket.getaddrinfo("0.0.0.0", 80)[0][-1])
srv.listen(2)
srv.setblocking(False)


def _udp():
    for _ in range(20):
        try:
            datos, addr = udp.recvfrom(256)
        except OSError:
            return
        for linea in datos.decode("utf-8", "ignore").split("\n"):
            linea = linea.strip()
            if linea == "VERSION?":
                try:
                    udp.sendto(json.dumps(_estado()).encode(), addr)
                except OSError:
                    pass
            elif linea:
                pos.linea(linea)


def _ble():
    if ble:
        for d in ble.leer():
            for linea in d.decode("utf-8", "ignore").split("\n"):
                linea = linea.strip()
                if linea:
                    pos.linea(linea)


def _responder(cl, codigo, cuerpo):
    cl.send(("HTTP/1.1 %d %s\r\nContent-Type: application/json\r\nConnection: close\r\n"
             "Content-Length: %d\r\n\r\n%s" % (codigo, "OK" if codigo == 200 else "Error",
                                               len(cuerpo), cuerpo)).encode())


def _reiniciar(cl):
    _responder(cl, 200, '{"success": true, "reinicio": true}')
    cl.close()
    time.sleep(1)
    machine.reset()


def _http():
    try:
        cl, _ = srv.accept()
    except OSError:
        return
    try:
        cl.settimeout(3)
        raw = b""
        while b"\r\n\r\n" not in raw and len(raw) < 2048:
            c = cl.recv(512)
            if not c:
                break
            raw += c
        cab, _, cuerpo = raw.partition(b"\r\n\r\n")
        largo = 0
        for l in cab.split(b"\r\n"):
            if l.lower().startswith(b"content-length:"):
                largo = int(l.split(b":", 1)[1].strip() or 0)
        while len(cuerpo) < min(largo, 1024):
            c = cl.recv(512)
            if not c:
                break
            cuerpo += c
        metodo, _, ruta = cab.split(b"\r\n", 1)[0].decode().partition(" ")
        d = json.loads(cuerpo or "{}") if metodo == "POST" else {}
        if ruta.startswith("/api/settings"):
            if "PABELLON" in d and not d["PABELLON"]:
                sistema16.modo_pabellon(False)
                return _reiniciar(cl)
            if "BRI" in d:
                b = max(1, min(100, int(float(d["BRI"])))) / 100.0
                sistema16.my_shared.BRIGHTNESS = b
                sistema16.guardar_ajustes(brillo=b)
                pos.pintado = None
            _responder(cl, 200, json.dumps({"success": True, "PABELLON": 1,
                                            "BRI": int(sistema16.my_shared.BRIGHTNESS * 100)}))
        elif ruta.startswith("/api/version"):
            _responder(cl, 200, json.dumps(_estado()))
        elif metodo == "POST" and ruta.startswith("/api/posesion"):
            pos.mensaje("POS " + str(d.get("cmd", "")))
            _responder(cl, 200, '{"success": true}')
        elif metodo == "POST" and ruta.startswith("/api/reboot"):
            _reiniciar(cl)
        else:
            _responder(cl, 404, '{"success": false, "error": "modo pabellon"}')
    except Exception as e:
        print("[HTTP]", e)
    finally:
        try:
            cl.close()
        except Exception:
            pass


try:
    wdt = machine.WDT(timeout=WDT_MS)
except Exception as _e:
    wdt = None
    print("[WDT]", _e)
pantalla16.clear()
print("[PABELLON]", version(), "redes", len(REDES), "BLE", ble.nombre if ble else None,
      "libre", gc.mem_free())

while True:
    try:
        if wdt:
            wdt.feed()
        if time.ticks_diff(time.ticks_ms(), _t["gc"]) >= GC_MS:
            _t["gc"] = time.ticks_ms()
            gc.collect()
        _udp()
        _ble()
        _http()
        _wifi()
        m = "posesion" if pos.activo() else "espera"
        if m != modo[0]:
            print("[MODO]", m)
            modo[0] = m
        pos.pintar()
        time.sleep_ms(10)
    except Exception as e:
        import sys
        sys.print_exception(e)
        time.sleep(1)
