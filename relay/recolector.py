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
POLL_VIVO = int(os.environ.get("POLL_VIVO", 5))     # s entre consultas a la FBM en juego
POLL_ESPERA = 60      # s antes de empezar / sin encontrar
ANTES_MIN = 20        # empieza a seguir un partido 20 min antes
MAX_MIN = 150         # pasado esto sin FINALIZADO se deja
LISTA_SEG = 15 * 60
# Retraso del reloj: la FBM da el tiempo de la ULTIMA accion apuntada y el anotador la apunta
# tarde (medido en pista: 15-20 s), asi que las pantallas iban por detras del reloj real. Con el
# reloj en marcha se publica el tiempo RETRASO_SEG segundos menos (11:55 -> 11:40); parado
# (falta, tiempo muerto...) o antes de empezar el cuarto se publica tal cual. "retraso" en la
# entrada del partido en partidos.json lo cambia para ese partido. Las placas no se tocan.
RETRASO_SEG = float(os.environ.get("RETRASO_SEG", 15))

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


def corregir_retraso(p, mk):
    """Resta el retraso al tiempo publicado solo con el reloj en marcha."""
    c = p.get("retraso", RETRASO_SEG)
    try:
        c = int(float(c))
    except (TypeError, ValueError):
        c = 0
    t = mk.get("tiempo") or ""
    if not c or mk.get("parado") or mk.get("descanso") or ":" not in t:
        return
    try:
        mm, ss = t.split(":")
        r = max(0, int(mm) * 60 + int(ss) - c)
    except ValueError:
        return
    mk["tiempo_fbm"] = t
    mk["tiempo"] = "%02d:%02d" % (r // 60, r % 60)


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


_PUNTOS = {"CANASTA-1P": 1, "CANASTA-2P": 2, "CANASTA-3P": 3}


def bajar_partido(hid):
    """JSON completo del partido (una sola peticion; solo se usa al acabar)."""
    body = fbm._urlencode({"id_dispositivo": fbm._sid, "key": fbm._key,
                           "accion": "obtenerPartido", "id_partido": hid})
    s = _ssl_connect("v2/envivo/partido.ashx", body)
    b = b""
    try:
        while True:
            c = s.recv(65536)
            if not c:
                break
            b += c
    finally:
        s.close()
    return json.loads(b[b.find(b"\r\n\r\n") + 4:])


def estadisticas(hid):
    """Estadisticas por jugador a partir del acta en directo. La FBM solo apunta canastas
    (1, 2 y 3), tiros libres fallados, faltas, cambios y tiempos muertos: no hay rebotes,
    asistencias, robos ni tapones."""
    d = bajar_partido(hid)
    pd = d.get("partido") or {}
    ott = d.get("EnVivoJugadoresOTT") or {}
    hist = (d.get("envivo") or {}).get("historialacciones") or []
    equipos = {}
    for lado, ide, nom, lst in (("local", pd.get("idlocal"), pd.get("local"), ott.get("JugadoresEnVivoLocal")),
                                ("visit", pd.get("idvisitante"), pd.get("visitante"), ott.get("JugadoresEnVivoVisitante"))):
        equipos[int(ide or 0)] = {"lado": lado, "nombre": nom or "", "pts": 0, "jug": {
            str(j.get("IdJugador")): {"nombre": j.get("Nombre", ""), "dorsal": "", "pts": 0, "t1": 0, "t1i": 0,
                                      "t2": 0, "t3": 0, "f": 0, "juega": False}
            for j in (lst or [])}}
    for a in hist:
        if str(a.get("eliminado")) == "True":
            continue
        eq = equipos.get(int(a.get("equipo_id") or 0))
        cid = str(a.get("componente_id") or "")
        if not eq or cid in ("", "-1"):
            continue
        j = eq["jug"].setdefault(cid, {"nombre": "", "dorsal": "", "pts": 0, "t1": 0, "t1i": 0,
                                       "t2": 0, "t3": 0, "f": 0, "juega": False})
        if str(a.get("dorsal") or "-1") != "-1":
            j["dorsal"] = str(a["dorsal"])
        t = a.get("accion_tipo")
        if t in _PUNTOS:
            j["pts"] += _PUNTOS[t]
            eq["pts"] += _PUNTOS[t]
            j["juega"] = True
            if t == "CANASTA-1P":
                j["t1"] += 1
                j["t1i"] += 1
            else:
                j["t%d" % _PUNTOS[t]] += 1
        elif t == "TIRO1-FALLADO":
            j["t1i"] += 1
            j["juega"] = True
        elif t == "FALTA-COMETIDA":
            j["f"] += 1
            j["juega"] = True
        elif t == "CAMBIO-JUGADOR-ENTRA":
            j["juega"] = True
    for lst in ((d.get("envivo") or {}).get("jugadoresenpistalocal") or [],
                (d.get("envivo") or {}).get("jugadoresenpistavisitante") or []):
        for x in lst:
            eq = equipos.get(int(x.get("idequipo") or 0))
            if eq:
                for j in eq["jug"].values():
                    if j["dorsal"] == str(x.get("dorsal")):
                        j["juega"] = True
    out = {"local": {}, "visit": {}, "rl": pd.get("tanteo_local"), "rv": pd.get("tanteo_visitante"),
           "parciales": [[p.get("tanteo_periodo_local"), p.get("tanteo_periodo_visitante")]
                         for p in pd.get("periodos") or []],
           "numperiodos": pd.get("numperiodos")}
    for eq in equipos.values():
        jug = sorted(eq["jug"].values(), key=lambda j: (-j["pts"], int(j["dorsal"]) if j["dorsal"].isdigit() else 999))
        out[eq["lado"]] = {"nombre": eq["nombre"], "jugadores": jug}
    return out


MINIBASKET = ("benj", "alev", "mini", "premini")   # categorias de 6 periodos


def periodo(p, mk):
    """En minibasket (benjamin/alevin) se juegan 6 periodos: la FBM numera el 5 y el 6 como si
    fueran prorrogas (OT1/OT2). Se publican como Q5/Q6 y la prorroga real (7) como OT1."""
    if any(c in (p.get("categoria") or "").lower() for c in MINIBASKET):
        q = mk.get("cuarto") or ""
        mk["cuarto"] = {"OT1": "Q5", "OT2": "Q6", "OT3": "OT1", "OT4": "OT2"}.get(q, q)


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
            periodo(p, mk)
            corregir_retraso(p, mk)
            if k in fin_forzado():
                mk["estado"], mk["vivo"] = "FINALIZADO", False
                log("[FIN] forzado a mano:", k)
            st["n"] += 1
            publicar("/m/%s.json" % k, {"clave": k, "al": st["al"], "av": st["av"], "hora": st["hora"],
                                        "m": mk, "t": int(ahora), "n": st["n"]})
            log("[PUB]", k, mk["rl"], "-", mk["rv"], mk["cuarto"], mk["tiempo"], mk["estado"])
            if mk["estado"] == "FINALIZADO":
                st["fin"] = True
                try:
                    publicar("/m/%s_stats.json" % k, estadisticas(st["hid"]))
                    log("[STATS]", k, "publicadas")
                except Exception as e:
                    log("[STATS] error", k, e)
            vivo = mk["tiempo"] or mk["rl"] or mk["rv"]
            st["prox"] = ahora + (POLL_VIVO if vivo else POLL_ESPERA)
        time.sleep(1)


if __name__ == "__main__":
    main()
