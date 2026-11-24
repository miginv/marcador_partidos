# Ulanzi TC001 en modo solo mensajes: reloj + API Awtrix (my_server) para auto_power.
# El ESP32 del TC001 no tiene PSRAM: las conexiones https (TLS) necesitan ~40 KB de
# memoria del sistema y, cuando el heap de MicroPython crece, ya no la devuelve. Por eso
# todo lo que va por https (OTA del canal tc001 e iconos de LaMetric) se hace AQUI, al
# arrancar y con casi nada cargado; despues se cargan my_display/my_network/my_server.
# Un icono que falte mientras funciona no se descarga (podria colgar la pantalla): se
# apunta en ICONS_PENDIENTES y se baja en el siguiente arranque.
import gc
import json
import os
import time
import network
import ubinascii

OTA_BASE = "https://raw.githubusercontent.com/miginv/marcador_partidos/main/ota/tc001/"
OTA_VERSION_FILE = "ota_version.txt"
ICONS_PENDIENTES = "icons_pendientes.txt"
# iconos que manda auto_power: se tienen siempre en /ICONS
ICONOS_AUTO_POWER = ("858", "2012", "61396", "34394", "1545", "55027", "2422", "32930",
                     "55274", "8644")

sta = network.WLAN(network.STA_IF)


def _hostname():
    return "matrix_" + ubinascii.hexlify(sta.config("mac")).decode()


def conectar_wifi():
    """Prueba las redes de config.json (wifi_credentials). True si conecta."""
    sta.active(True)
    try:
        network.hostname(_hostname())
    except Exception as e:
        print("[WIFI] hostname:", e)
    if sta.isconnected():
        return True
    try:
        with open("config.json") as f:
            creds = json.load(f).get("wifi_credentials", [])
    except Exception:
        creds = []
    for c in creds:
        print("[WIFI] conectando a", c.get("ssid"))
        try:
            sta.connect(c["ssid"], c.get("password", ""))
        except Exception as e:
            print("[WIFI]", e)
            continue
        t0 = time.time()
        while not sta.isconnected() and time.time() - t0 < 10:
            time.sleep(0.5)
        if sta.isconnected():
            print("[WIFI] conectado a", c["ssid"], sta.ifconfig()[0])
            return True
        try:
            sta.disconnect()
        except Exception:
            pass
    return False


def _ver(s):
    try:
        return tuple(int(x) for x in s.strip().split("."))
    except Exception:
        return (0,)


def _get(url):
    import requests
    gc.collect()
    r = requests.get(url, headers={"Cache-Control": "no-cache"}, timeout=15)
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        return r.content
    finally:
        r.close()


def actualizar():
    """OTA del canal tc001: baja todo a .new y solo si llega todo lo sustituye y reinicia."""
    try:
        remoto = json.loads(_get(OTA_BASE + "version.json"))
    except Exception as e:
        print("[OTA] sin version.json:", e)
        return
    try:
        with open(OTA_VERSION_FILE) as f:
            local = f.read().strip()
    except Exception:
        local = "0.0.0"
    nueva = remoto.get("version", "0.0.0")
    if _ver(nueva) <= _ver(local):
        print("[OTA] al dia:", local)
        return
    ficheros = remoto.get("files", [])
    print("[OTA]", local, "->", nueva, ficheros)
    for fn in ficheros:
        try:
            datos = _get(OTA_BASE + fn)
            if not datos:
                raise OSError("vacio")
            with open(fn + ".new", "wb") as f:
                f.write(datos)
            del datos
        except Exception as e:
            print("[OTA] fallo", fn, e, "-> no se instala nada")
            for g in ficheros:
                try:
                    os.remove(g + ".new")
                except OSError:
                    pass
            return
    for fn in ficheros:
        try:
            os.remove(fn)
        except OSError:
            pass
        os.rename(fn + ".new", fn)
    with open(OTA_VERSION_FILE, "w") as f:
        f.write(nueva)
    print("[OTA] instalada", nueva, "-> reinicio")
    import machine
    time.sleep(1)
    machine.reset()


def _tiene_icono(i):
    try:
        return os.stat("/ICONS/%s.gif" % i)[6] > 0
    except OSError:
        return False


def bajar_iconos():
    """Iconos de auto_power y los apuntados como pendientes, solo si faltan."""
    try:
        os.mkdir("/ICONS")
    except OSError:
        pass
    pend = []
    try:
        with open(ICONS_PENDIENTES) as f:
            pend = [l.strip() for l in f if l.strip()]
    except OSError:
        pass
    faltan = [i for i in list(ICONOS_AUTO_POWER) + pend if not _tiene_icono(i)]
    quedan = []
    for i in faltan:
        ok = False
        for url in ("https://developer.lametric.com/content/apps/icon_thumbs/%s.gif" % i,
                    "https://developer.lametric.com/content/apps/icon_thumbs/%s_icon.gif" % i):
            try:
                d = _get(url)
                if len(d) > 10 and d[:3] == b"GIF":
                    with open("/ICONS/%s.gif" % i, "wb") as f:
                        f.write(d)
                    print("[ICONO]", i, len(d), "bytes")
                    ok = True
                    break
            except Exception as e:
                print("[ICONO]", i, "fallo:", e)
        if not ok and i in pend:
            quedan.append(i)            # se reintenta en el siguiente arranque
    try:
        if quedan:
            with open(ICONS_PENDIENTES, "w") as f:
                f.write("\n".join(quedan) + "\n")
        else:
            os.remove(ICONS_PENDIENTES)
    except OSError:
        pass


# ---------- arranque ----------
if not conectar_wifi():
    import wifi_portal                       # sin red: portal abierto "scoreboard"
    wifi_portal.asegurar(_hostname())        # no vuelve (reinicia al dar de alta una red)
try:
    import ntptime
    ntptime.settime()
except Exception as e:
    print("[NTP] fallo:", e)
actualizar()
bajar_iconos()
gc.collect()

# a partir de aqui no hay mas https: ya se puede cargar todo lo grande
import my_network
import my_display
import my_server

# ---------- paso automatico a marcador (servidor propio por http, sin TLS) ----------
import ajustes_tc001
_rel = ajustes_tc001.AJUSTES.get("relay", {})
if _rel.get("url") and _rel.get("auto"):
    import modo_fbm
    _t = {"rev": 0, "lista": 0}
    _frame_orig = my_display.display_clock_frame

    def _frame(*a, **k):
        # my_server dibuja el reloj varias veces por segundo: se aprovecha para revisar
        ahora = time.time()
        if ahora - _t["rev"] >= 60:
            _t["rev"] = ahora
            try:
                if ahora - _t["lista"] >= 15 * 60:
                    if modo_fbm.descargar(_rel["url"] + "/partidos.json"):
                        _t["lista"] = ahora
                if modo_fbm.partido_cercano():
                    modo_fbm.cambiar("marcador")
            except Exception as e:
                print("[MODO] error revisando:", e)
        return _frame_orig(*a, **k)

    my_display.display_clock_frame = _frame

my_display.process_awtrix({
    "text": "{} {}".format(my_network.get_ip(), my_network.get_hostname()),
    "color": [0, 80, 255], "icon": 32930, "repeat": 1, "textCase": 3, "scrollspeed": 50})
my_server.start_api_server_with_clock()
