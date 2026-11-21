# Cambio entre modo marcador (partido FBM) y modo mensajes (reloj + API de siempre).
# Cada modo arranca limpio tras un reset: asi el marcador tiene toda la RAM para la API
# y durante el partido no se atiende ningun mensaje. modo.txt dice que modo arrancar.
import json
import os
import time

EPOCH_2000 = 946684800       # time.time() de MicroPython cuenta desde 2000
ANTES_MIN = 15               # mensajes -> marcador 15 min antes del inicio
SALIR_MIN = 20               # marcador -> mensajes si el siguiente empieza en mas de 20 min
MAX_MIN = 150                # igual que el marcador: pasado esto el partido se da por acabado
MODO_FILE = "modo.txt"
PARTIDOS_FILE = "partidos.json"
ESTADO_FILE = "estado.json"
PARTIDOS_URL = "https://raw.githubusercontent.com/miginv/marcador_partidos/main/partidos.json"


def hay_mensajes():
    """Solo se cambia de modo si la placa tiene modo mensajes."""
    return "mensajes_fbm.py" in os.listdir() or "mensajes_fbm.mpy" in os.listdir()


def leer_modo():
    try:
        with open(MODO_FILE) as f:
            m = f.read().strip()
    except Exception:
        m = ""
    if m == "mensajes" and hay_mensajes():
        return "mensajes"
    return "marcador"


def cambiar(modo):
    print("[MODO] ->", modo)
    try:
        with open(MODO_FILE, "w") as f:
            f.write(modo)
    except Exception as e:
        print("[MODO] no se pudo guardar:", e)
        return
    import machine
    time.sleep(1)
    machine.reset()


def _clave(p):
    return p.get("notif") or (p.get("fecha", "") + p.get("hora", ""))


def partido_cercano():
    """Partido pendiente que empieza en ANTES_MIN min o menos, o ya en juego. None si no
    hay o si la placa aun no tiene hora."""
    if time.localtime()[0] < 2024:
        return None
    try:
        with open(PARTIDOS_FILE) as f:
            lista = json.load(f).get("partidos", [])
    except Exception:
        return None
    try:
        with open(ESTADO_FILE) as f:
            hechos = json.load(f).get("hechos", [])
    except Exception:
        hechos = []
    ahora = time.time() + EPOCH_2000
    for p in lista:
        ts = p.get("ts")
        if not ts or _clave(p) in hechos:
            continue
        if ts - ANTES_MIN * 60 <= ahora <= ts + MAX_MIN * 60:
            return p
    return None


def descargar():
    """Baja la lista de GitHub a partidos.json. True si ha ido bien."""
    import gc
    url = PARTIDOS_URL
    try:
        with open("config.json") as f:
            url = json.load(f).get("partidos_url", PARTIDOS_URL)
    except Exception:
        pass
    gc.collect()
    try:
        import requests
        r = requests.get(url, headers={"Cache-Control": "no-cache"})
        try:
            if r.status_code != 200:
                print("[MODO] lista HTTP", r.status_code)
                return False
            txt = r.text
        finally:
            r.close()
        json.loads(txt)                      # solo se guarda si es JSON valido
        with open(PARTIDOS_FILE, "w") as f:
            f.write(txt)
        return True
    except Exception as e:
        print("[MODO] fallo descarga:", e)
        return False
    finally:
        gc.collect()


# ---------- OTA del marcador (no la de la Awtrix: esa pisaria boot.py) ----------
# En el repo publico: ota/<canal>/version.json = {"version": "1.0.1", "files": [...]}.
# Se baja todo a .new y solo si han llegado todos se sustituyen y se reinicia.
OTA_BASE = "https://raw.githubusercontent.com/miginv/marcador_partidos/main/ota/"
OTA_VERSION_FILE = "ota_version.txt"


def _canal():
    return "tc001"                     # Ulanzi TC001: canal propio, nunca 32x8 ni 24x8


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


def actualizar():
    """Si hay version nueva en GitHub la instala y reinicia. Si no, devuelve False."""
    import gc
    import requests
    base = OTA_BASE + _canal() + "/"
    gc.collect()
    try:
        r = requests.get(base + "version.json", headers={"Cache-Control": "no-cache"})
        try:
            if r.status_code != 200:
                print("[OTA] version.json HTTP", r.status_code)
                return False
            remoto = json.loads(r.text)
        finally:
            r.close()
    except Exception as e:
        print("[OTA] sin version.json:", e)
        return False
    local = version_local()
    nueva = remoto.get("version", "0.0.0")
    if _ver(nueva) <= _ver(local):
        print("[OTA] al dia:", local)
        return False
    ficheros = remoto.get("files", [])
    print("[OTA]", local, "->", nueva, ficheros)
    for fn in ficheros:
        gc.collect()
        try:
            r = requests.get(base + fn, headers={"Cache-Control": "no-cache"})
            try:
                if r.status_code != 200:
                    raise OSError("HTTP %d" % r.status_code)
                datos = r.content
            finally:
                r.close()
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
            return False
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
