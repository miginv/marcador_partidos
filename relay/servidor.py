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
"secretos" (opcional): {"<clave>": "<64 hex>"}, secreto de cada placa para cifrarle las WiFis.
  GET /ajustes.json?k=<clave> -> ajustes de esa pantalla, de ajustes.json (tampoco va al repo):
  {"todas": {"brillo": 40, "wifis": [{"ssid": "...", "password": "..."}]},
   "<nombre de la pantalla>": {"brillo_marcador": 60, "wifis": [...], "equipos": [...]}}
  Lo de la pantalla manda sobre "todas"; las WiFis se suman. Las WiFis solo salen cifradas
  (AES-256-CBC + firma, ver ota/32x8/ajustes_remotos.py) y solo si la clave tiene secreto.
  "equipos" en ajustes.json tambien filtra /partidos.json, como en claves.json.
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
_claves = {"mtime": None, "obligatoria": False, "claves": {}, "equipos": {}, "secretos": {}}
AJUSTES_FICH = os.path.join(DIR, "ajustes.json")
_ajustes = {"mtime": None, "d": {}}
CAMPOS = ("brillo", "brillo_marcador", "wifis", "equipos")
LIMITE_MIN = 120
_uso = {}             # ip -> [minuto, peticiones]


def claves():
    """claves.json (si cambia en disco se vuelve a leer)."""
    try:
        mt = os.path.getmtime(CLAVES_FICH)
    except OSError:
        _claves.update(mtime=None, obligatoria=False, claves={}, equipos={}, secretos={})
        return _claves
    if mt != _claves["mtime"]:
        try:
            d = json.load(open(CLAVES_FICH))
            _claves.update(mtime=mt, obligatoria=bool(d.get("obligatoria", True)),
                           claves=dict(d.get("claves", {})),
                           equipos={k: [e.upper() for e in ([v] if isinstance(v, str) else v)]
                                    for k, v in d.get("equipos", {}).items()},
                           secretos=dict(d.get("secretos", {})))
        except Exception as e:
            sys.stderr.write("claves.json no valido: %s\n" % e)
    return _claves


def ajustes_de(k):
    """Ajustes en claro de la pantalla con la clave k ("todas" + los suyos)."""
    try:
        mt = os.path.getmtime(AJUSTES_FICH)
        if mt != _ajustes["mtime"]:
            _ajustes.update(mtime=mt, d=json.load(open(AJUSTES_FICH)))
    except OSError:
        _ajustes.update(mtime=None, d={})
    except Exception as e:
        sys.stderr.write("ajustes.json no valido: %s\n" % e)
    a = _ajustes["d"]
    nombre = claves()["claves"].get(k)
    r = {}
    for parte in (a.get("todas", {}), a.get(nombre, {}) if nombre else {}):
        for c, v in parte.items():
            if c not in CAMPOS:
                continue
            r[c] = r.get(c, []) + list(v) if c == "wifis" else v
    return r


def equipos_de(k):
    e = ajustes_de(k).get("equipos") or claves()["equipos"].get(k)
    if isinstance(e, str):
        e = [e]
    return [x.upper() for x in e] if e else None


def cifrar(datos, secreto):
    """Lo que descifra ajustes_remotos._descifrar en la placa."""
    import base64
    import hashlib
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    clave = bytes.fromhex(secreto)
    iv = os.urandom(16)
    n = 16 - len(datos) % 16
    e = Cipher(algorithms.AES(clave), modes.CBC(iv)).encryptor()
    ct = e.update(datos + bytes([n]) * n) + e.finalize()
    kmac = hashlib.sha256(clave + b"mac").digest()
    tag = hashlib.sha256(kmac + hashlib.sha256(kmac + iv + ct).digest()).digest()[:16]
    return base64.b64encode(iv + ct + tag).decode()


def respuesta_ajustes(k):
    import hashlib
    a = ajustes_de(k)
    a.pop("equipos", None)                 # eso lo aplica el servidor, no la placa
    secreto = claves()["secretos"].get(k)
    if not secreto:
        a.pop("wifis", None)               # nunca en claro
    v = hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()[:12]
    if a.get("wifis"):
        a["wifis"] = cifrar(json.dumps(a["wifis"]).encode(), secreto)
    a["v"] = v
    return json.dumps(a).encode()


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
        if ruta == "/ajustes.json":
            try:
                return self._resp(200, respuesta_ajustes(k))
            except Exception as e:
                sys.stderr.write("ajustes: %s\n" % e)
                return self._resp(500, b'{"error":"ajustes"}')
        with _lock:
            d = DATOS.get(ruta)
        if d is None:
            return self._resp(404, b'{"error":"no"}')
        if ruta == "/partidos.json":
            e = equipos_de(k)
            if e:
                d = filtrar(d, e)
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
