#!/usr/bin/env python3
"""Recolector: el UNICO que consulta a la FBM. Lee la lista de partidos, sigue los que estan
en juego (o a punto) y publica cada uno en el servidor como /m/<notif>.json; tambien
republica la lista como /partidos.json. Asi la FBM ve un solo cliente aunque haya muchas
pantallas, y las pantallas leen por http sin TLS.
Reutiliza el gesdeportiva.py de las placas (el mismo codigo, con unos adaptadores).
Uso: RELAY_URL=http://host:8080 python3 recolector.py   (token en RELAY_TOKEN o token.txt)"""
import binascii
import json
import os
import ssl
import socket
import sys
import time
import types
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
OTA = os.path.join(DIR, "..", "ota", "32x8")
RELAY = os.environ.get("RELAY_URL", "http://127.0.0.1:8080").rstrip("/")
TOKEN = os.environ.get("RELAY_TOKEN") or open(os.path.join(DIR, "token.txt")).read().strip()
PARTIDOS_URL = os.environ.get("PARTIDOS_URL",
                              "https://raw.githubusercontent.com/miginv/marcador_partidos/main/partidos.json")
POLL_VIVO = int(os.environ.get("POLL_VIVO", 15))     # s entre consultas a la FBM en juego
POLL_ESPERA = 60      # s antes de empezar / sin encontrar
ANTES_MIN = 20        # empieza a seguir un partido 20 min antes
MAX_MIN = 150         # pasado esto sin FINALIZADO se deja
LISTA_SEG = 15 * 60

# --- adaptadores para usar gesdeportiva.py (MicroPython) en CPython ---
sys.modules["ujson"] = json
sys.modules["ubinascii"] = binascii
sys.modules["my_shared"] = types.SimpleNamespace(DEBUG=bool(os.environ.get("DEBUG")))
sys.path.insert(0, OTA)
import gesdeportiva as fbm  # noqa: E402


def _ssl_connect(path, body_str):
    body_b = body_str.encode()
    req = ("POST /{} HTTP/1.0\r\nHost: {}\r\nUser-Agent: {}\r\n"
           "Content-Type: application/x-www-form-urlencoded\r\n"
           "Content-Length: {}\r\nConnection: close\r\n\r\n"
           ).format(path, fbm._HOST, fbm._UA, len(body_b)).encode() + body_b
    s = socket.create_connection((fbm._HOST, fbm._PORT), timeout=15)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(s, server_hostname=fbm._HOST)
    s.sendall(req)
    return s


fbm._ssl_connect = _ssl_connect
_uid_orig = os.urandom


def log(*a):
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)


def publicar(ruta, obj):
    d = json.dumps(obj, separators=(",", ":")).encode()
    r = urllib.request.Request(RELAY + ruta, data=d, method="PUT",
                               headers={"X-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=10) as resp:
        resp.read()


def clave(p):
    return p.get("notif") or (p.get("fecha", "").replace("/", "") + p.get("hora", "").replace(":", ""))


def minutos(p):
    if p.get("ts"):
        return (time.time() - p["ts"]) / 60
    return None


def buscar(p):
    """Como marcador_fbm.buscar_partido, pero devuelve los nombres completos."""
    if p.get("notif"):
        sk = p.get("skip", 0)
        termino = p["buscar"] if isinstance(p["buscar"], str) else p["buscar"][0]
        for s in (sk, sk - 50, sk + 50):
            if s < 0:
                continue
            try:
                hid, lf, vf = fbm.buscar_id_partido(termino, p["fecha"], s, p["notif"])
            except Exception as e:
                log("[BUSCAR] error", e)
                fbm._sid = None
                hid = None
            if hid:
                return hid, p.get("local", ""), p.get("visit", ""), p["hora"][:5]
        return None
    for t in p["buscar"]:
        try:
            hid, lf, vf = fbm.buscar_id_partido(t, p["fecha"])
        except Exception as e:
            log("[BUSCAR] error", e)
            hid = None
        if hid:
            return hid, lf, vf, fbm._last_hora[:5]
    return None


FIN_FORZADO = os.path.join(DIR, "fin_forzado.txt")   # notif (uno por linea) a dar por terminados


def fin_forzado():
    """Partidos que la FBM no cierra (acta sin cerrar, prorroga fantasma...): se publican como
    FINALIZADO para que las pantallas pasen al siguiente."""
    try:
        return {l.split("#")[0].strip() for l in open(FIN_FORZADO)} - {""}
    except OSError:
        return set()


def main():
    lista, t_lista = [], 0
    seg = {}        # clave -> {"hid","al","av","hora","prox","n","fin"}
    while True:
        ahora = time.time()
        if ahora - t_lista > LISTA_SEG or not lista:
            try:
                url = PARTIDOS_URL if PARTIDOS_URL.startswith("file:") else PARTIDOS_URL + "?t=%d" % ahora
                with urllib.request.urlopen(url, timeout=20) as r:
                    datos = json.loads(r.read())
                lista = datos.get("partidos", [])
                publicar("/partidos.json", datos)
                t_lista = ahora
                log("[LISTA]", len(lista), "partidos")
            except Exception as e:
                log("[LISTA] fallo:", e)
        for p in lista:
            m = minutos(p)
            if m is None or m < -ANTES_MIN or m > MAX_MIN:
                continue
            k = clave(p)
            st = seg.setdefault(k, {"n": 0, "prox": 0, "fin": False, "hid": None})
            if st["fin"] or ahora < st["prox"]:
                continue
            if not st["hid"]:
                r = buscar(p)
                if not r:
                    log("[NOG]", k, p.get("local"), "-", p.get("visit"))
                    st["prox"] = ahora + POLL_ESPERA
                    continue
                st["hid"], st["al"], st["av"], st["hora"] = r
                log("[SIGO]", k, st["al"], "-", st["av"], st["hora"])
            try:
                mk = fbm.get_marcador(st["hid"])
            except Exception as e:
                log("[FBM] error", k, e)
                fbm._sid = None
                st["hid"] = None
                st["prox"] = ahora + 10
                continue
            if not mk:
                st["hid"] = None          # sesion caducada: se vuelve a buscar
                st["prox"] = ahora + 10
                continue
            if k in fin_forzado():
                mk["estado"], mk["vivo"] = "FINALIZADO", False
                log("[FIN] forzado a mano:", k)
            st["n"] += 1
            publicar("/m/%s.json" % k, {"clave": k, "al": st["al"], "av": st["av"], "hora": st["hora"],
                                        "m": mk, "t": int(ahora), "n": st["n"]})
            log("[PUB]", k, mk["rl"], "-", mk["rv"], mk["cuarto"], mk["tiempo"], mk["estado"])
            if mk["estado"] == "FINALIZADO":
                st["fin"] = True
            vivo = mk["tiempo"] or mk["rl"] or mk["rv"]
            st["prox"] = ahora + (POLL_VIVO if vivo else POLL_ESPERA)
        time.sleep(1)


if __name__ == "__main__":
    main()
