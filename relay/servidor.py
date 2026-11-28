#!/usr/bin/env python3
"""Servidor del marcador: guarda y sirve JSON pequenos por http (sin https, para que el
TC001 y las placas sin memoria para TLS puedan leer).
  GET  /partidos.json?k=<clave>, /m/<notif>.json?k=<clave>  -> lo ultimo publicado
  PUT  /<ruta>.json  cabecera X-Token                       -> lo publica (solo el recolector)
Leer exige la clave de la pantalla (?k= o cabecera X-Key) si claves.json existe:
  {"obligatoria": true, "claves": {"<clave>": "nombre de la pantalla", ...},
   "equipos": {"<clave>": ["SERRACINES FEMENINO", ...]}}
"equipos" es opcional: la pantalla con esa clave solo recibe en /partidos.json los partidos en
los que juega alguno de esos equipos (local o visitante, sin distinguir mayusculas). Asi una
pantalla regalada a un equipo sigue solo sus partidos.
Sin clave valida responde 404 (como si no hubiera nada). Se relee al cambiar el fichero.
Maximo LIMITE_MIN lecturas por minuto y por IP (429 si se pasa).
token.txt y claves.json nunca van al repo.
Uso: python3 servidor.py [puerto]"""
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("RELAY_TOKEN") or open(os.path.join(DIR, "token.txt")).read().strip()
RUTA_OK = re.compile(r"^/[a-z0-9_/-]{1,80}\.json$")
MAX = 64 * 1024
DATOS = {}            # ruta -> bytes (en memoria; tambien a disco para sobrevivir reinicios)
GUARDA = os.path.join(DIR, "datos")
_lock = threading.Lock()
CLAVES_FICH = os.path.join(DIR, "claves.json")
_claves = {"mtime": None, "obligatoria": False, "claves": {}, "equipos": {}}
LIMITE_MIN = 120
_uso = {}             # ip -> [minuto, peticiones]


def claves():
    """claves.json (si cambia en disco se vuelve a leer)."""
    try:
        mt = os.path.getmtime(CLAVES_FICH)
    except OSError:
        _claves.update(mtime=None, obligatoria=False, claves={}, equipos={})
        return _claves
    if mt != _claves["mtime"]:
        try:
            d = json.load(open(CLAVES_FICH))
            _claves.update(mtime=mt, obligatoria=bool(d.get("obligatoria", True)),
                           claves=dict(d.get("claves", {})),
                           equipos={k: [e.upper() for e in ([v] if isinstance(v, str) else v)]
                                    for k, v in d.get("equipos", {}).items()})
        except Exception as e:
            sys.stderr.write("claves.json no valido: %s\n" % e)
    return _claves


def filtrar(d, equipos):
    """La lista de partidos dejando solo los de esos equipos."""
    try:
        datos = json.loads(d)
        datos["partidos"] = [p for p in datos.get("partidos", [])
                             if any(e in (p.get("local", "") + "|" + p.get("visit", "")).upper()
                                    for e in equipos)]
        return json.dumps(datos, ensure_ascii=False).encode()
    except Exception as e:
        sys.stderr.write("filtro: %s\n" % e)
        return d


def demasiadas(ip):
    m = int(time.time() // 60)
    with _lock:
        u = _uso.get(ip)
        if not u or u[0] != m:
            if len(_uso) > 5000:
                _uso.clear()
            _uso[ip] = u = [m, 0]
        u[1] += 1
        return u[1] > LIMITE_MIN


def _fich(ruta):
    return os.path.join(GUARDA, ruta.strip("/").replace("/", "__"))


def cargar():
    os.makedirs(GUARDA, exist_ok=True)
    for f in os.listdir(GUARDA):
        with open(os.path.join(GUARDA, f), "rb") as h:
            DATOS["/" + f.replace("__", "/")] = h.read()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"     # una peticion por conexion: lo mas sencillo para el ESP32

    def _resp(self, cod, cuerpo=b"", tipo="application/json"):
        self.send_response(cod)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def do_GET(self):
        partes = urlsplit(self.path)
        ruta = partes.path
        if demasiadas(self.client_address[0]):
            return self._resp(429, b'{"error":"despacio"}')
        c = claves()
        k = (parse_qs(partes.query).get("k") or [self.headers.get("X-Key") or ""])[0]
        if c["obligatoria"] and k not in c["claves"]:
            return self._resp(404, b'{"error":"no"}')
        with _lock:
            d = DATOS.get(ruta)
        if d is None:
            return self._resp(404, b'{"error":"no"}')
        if ruta == "/partidos.json" and k in c["equipos"]:
            d = filtrar(d, c["equipos"][k])
        self._resp(200, d)

    do_HEAD = do_GET

    def do_PUT(self):
        ruta = self.path.split("?")[0]
        if self.headers.get("X-Token") != TOKEN:
            return self._resp(403, b'{"error":"token"}')
        if not RUTA_OK.match(ruta):
            return self._resp(400, b'{"error":"ruta"}')
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX:
            return self._resp(400, b'{"error":"tam"}')
        d = self.rfile.read(n)
        try:
            json.loads(d)
        except Exception:
            return self._resp(400, b'{"error":"json"}')
        with _lock:
            DATOS[ruta] = d
            with open(_fich(ruta), "wb") as h:
                h.write(d)
        self._resp(200, b'{"ok":true}')

    def log_message(self, fmt, *a):
        if self.command != "GET" or os.environ.get("RELAY_LOG"):
            sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.client_address[0], fmt % a))


if __name__ == "__main__":
    cargar()
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print("servidor en el puerto", puerto, "-", len(DATOS), "ficheros")
    ThreadingHTTPServer(("", puerto), H).serve_forever()
