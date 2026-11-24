# Sustituto de gesdeportiva.py que NO va a la FBM: lee lo que publica el servidor propio
# (relay/recolector.py) por http normal, sin TLS. Misma interfaz que gesdeportiva para que
# marcador_fbm.py funcione igual: buscar_id_partido, get_marcador, _sid/_key, _last_hora.
#   GET <relay>/m/<notif>.json -> {"al","av","hora","m": {rl, rv, cuarto, tiempo, ...}}
import gc
import json
import socket

URL = ""            # http://host[:puerto] (lo fija marcador_fbm desde ajustes_tc001)
CLAVE = ""          # clave de esta pantalla en el servidor (sin ella responde 404)
_sid = "relay"      # marcador_fbm vuelve a buscar el partido si son None
_key = "relay"
_last_hora = ""


def con_clave(ruta):
    """Ruta con la clave de la pantalla (?k=...) si la hay."""
    if not CLAVE:
        return ruta
    return ruta + ("&" if "?" in ruta else "?") + "k=" + CLAVE


def _get(ruta):
    """GET http minimo (HTTP/1.0, una conexion por peticion). Devuelve dict o None."""
    u = URL.split("://", 1)[-1]
    host, _, puerto = u.partition(":")
    puerto = int(puerto or 80)
    gc.collect()
    s = socket.socket()
    try:
        s.settimeout(8)
        s.connect(socket.getaddrinfo(host, puerto)[0][-1])
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (con_clave(ruta), host)).encode())
        r = b""
        while True:
            c = s.recv(512)
            if not c:
                break
            r += c
            if len(r) > 8192:
                break
    finally:
        s.close()
    i = r.find(b"\r\n\r\n")
    if i < 0 or b" 200 " not in r[:16]:
        return None
    return json.loads(r[i + 4:])


def buscar_id_partido(nombre, fecha, skip=0, notif=None):
    """Con notif: el partido existe si el recolector ya lo publica. Sin notif no se puede
    localizar en el servidor (la lista de partidos.json siempre lleva notif)."""
    global _last_hora
    if not notif:
        return None, None, None
    try:
        d = _get("/m/%s.json" % notif)
    except Exception as e:
        print("[RELAY] buscar:", e)
        return None, None, None
    if not d:
        return None, None, None
    _last_hora = d.get("hora", "")
    return str(notif), d.get("al", ""), d.get("av", "")


def get_marcador(id_partido):
    try:
        d = _get("/m/%s.json" % id_partido)
    except Exception as e:
        print("[RELAY] marcador:", e)
        return None
    return d.get("m") if d else None
