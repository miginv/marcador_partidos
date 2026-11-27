# Utilidades de la 16x16: hora (NTP, horario de Espana), ajustes guardados, OTA del canal
# ota/16x16 del repo y servidor del marcador (relay.json).
import gc
import json
import os
import time
import my_shared

EPOCH_2000 = 946684800       # time.time() de MicroPython cuenta desde 2000
OTA_BASE = "https://raw.githubusercontent.com/miginv/marcador_partidos/main/ota/16x16/"
OTA_VERSION_FILE = "ota_version.txt"
AJUSTES_FILE = "ajustes16.json"
RELAY_DEFECTO = "http://34.30.243.27"
hora_ok = [False]


# ---------- hora ----------

def sync_hora():
    try:
        import ntptime
        ntptime.settime()                 # RTC en UTC
        hora_ok[0] = time.localtime()[0] >= 2024
    except Exception as e:
        print("[NTP] fallo:", e)
    return hora_ok[0]


def offset_es(t):
    """UTC+1 en invierno, UTC+2 entre el ultimo domingo de marzo y el de octubre."""
    y = time.localtime(t)[0]

    def ultimo_domingo(mes):
        d = 31
        while time.localtime(time.mktime((y, mes, d, 1, 0, 0, 0, 0)))[6] != 6:
            d -= 1
        return time.mktime((y, mes, d, 1, 0, 0, 0, 0))
    return 7200 if ultimo_domingo(3) <= t < ultimo_domingo(10) else 3600


def ahora_local():
    t = time.time()
    return t + offset_es(t)


# ---------- ajustes (brillo) ----------

def leer_ajustes():
    try:
        with open(AJUSTES_FILE) as f:
            d = json.load(f)
        if "brillo" in d:
            my_shared.BRIGHTNESS = max(0.01, min(1.0, float(d["brillo"])))
        return d
    except Exception:
        return {}


def guardar_ajustes(**kw):
    d = leer_ajustes()
    d.update(kw)
    with open(AJUSTES_FILE, "w") as f:
        json.dump(d, f)


# ---------- servidor del marcador ----------

def relay():
    """(url, clave) de relay.json; ("", "") si la placa no tiene clave."""
    try:
        with open("relay.json") as f:
            d = json.load(f)
        if d.get("clave"):
            return d.get("url") or RELAY_DEFECTO, d["clave"]
    except Exception:
        pass
    return "", ""


# ---------- OTA ----------

def _ver(s):
    try:
        return tuple(int(x) for x in s.strip().split("."))
    except Exception:
        return (0,)


def version_local():
    try:
        with open(OTA_VERSION_FILE) as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"


def _get(url):
    import requests
    gc.collect()
    r = requests.get(url, headers={"Cache-Control": "no-cache"})
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        return r.content
    finally:
        r.close()


def _bajar(url, destino):
    """Descarga a fichero por trozos de 1 KB (un .py grande no cabe entero en la RAM)."""
    import requests
    gc.collect()
    r = requests.get(url, headers={"Cache-Control": "no-cache"}, stream=True)
    n = 0
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        buf = bytearray(1024)
        with open(destino, "wb") as f:
            while True:
                k = r.raw.readinto(buf)
                if not k:
                    break
                f.write(buf[:k] if k < 1024 else buf)
                n += k
    finally:
        r.close()
    return n


PABELLON = "pabellon.on"


def es_pabellon():
    """Modo pabellon: solo reloj de posesion, por WiFi y Bluetooth (pabellon16)."""
    try:
        os.stat(PABELLON)
        return True
    except OSError:
        return False


def modo_pabellon(si):
    if si:
        with open(PABELLON, "w") as f:
            f.write("1")
        try:
            os.remove("ble.fallo")          # al pedirlo a mano, se vuelve a intentar el Bluetooth
        except OSError:
            pass
    else:
        try:
            os.remove(PABELLON)
        except OSError:
            pass


def actualizar(aviso=None):
    """Si hay version nueva en GitHub la instala (todo o nada) y reinicia."""
    try:
        remoto = json.loads(_get(OTA_BASE + "version.json"))
    except Exception as e:
        print("[OTA] sin version.json:", e)
        return False
    local = version_local()
    nueva = remoto.get("version", "0.0.0")
    if _ver(nueva) <= _ver(local):
        print("[OTA] al dia:", local)
        return False
    ficheros = remoto.get("files", [])
    print("[OTA]", local, "->", nueva)
    if aviso:
        aviso(nueva)
    for fn in ficheros:
        try:
            if not _bajar(OTA_BASE + fn, fn + ".new"):
                raise OSError("vacio")
        except Exception as e:
            print("[OTA] fallo", fn, e, "-> no se instala nada")
            for g in ficheros:
                try:
                    os.remove(g + ".new")
                except OSError:
                    pass
            return False
    for fn in ficheros:
        try:
            os.remove(fn)
        except OSError:
            pass
        os.rename(fn + ".new", fn)
        if fn.endswith(".mpy"):          # un .py con el mismo nombre se cargaria antes
            try:
                os.remove(fn[:-4] + ".py")
            except OSError:
                pass
    with open(OTA_VERSION_FILE, "w") as f:
        f.write(nueva)
    print("[OTA] instalada", nueva, "-> reinicio")
    import machine
    time.sleep(1)
    machine.reset()


def descargar_icono(icono):
    """Icono de LaMetric a /ICONS/<id>.gif. True si ya esta o se ha bajado."""
    try:
        os.mkdir("/ICONS")
    except OSError:
        pass
    ruta = "/ICONS/%s.gif" % icono
    try:
        if os.stat(ruta)[6] > 0:
            return True
    except OSError:
        pass
    if not str(icono).isdigit():
        return False
    for url in ("https://developer.lametric.com/content/apps/icon_thumbs/%s.gif" % icono,
                "https://developer.lametric.com/content/apps/icon_thumbs/%s_icon.gif" % icono):
        try:
            d = _get(url)
            if d[:3] == b"GIF":
                with open(ruta, "wb") as f:
                    f.write(d)
                print("[ICONO]", icono, len(d), "bytes")
                return True
        except Exception as e:
            print("[ICONO]", icono, e)
    return False
