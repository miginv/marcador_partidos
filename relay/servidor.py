#!/usr/bin/env python3
"""Servidor del marcador: guarda y sirve JSON pequenos por http (sin https, para que el
TC001 y las placas sin memoria para TLS puedan leer).
  GET  /partidos.json, /m/<clave>.json      -> lo ultimo publicado (sin cache)
  PUT  /<ruta>.json  cabecera X-Token        -> lo publica (solo el recolector)
El token se lee de la variable RELAY_TOKEN o del fichero token.txt (nunca en el repo).
Uso: python3 servidor.py [puerto]"""
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("RELAY_TOKEN") or open(os.path.join(DIR, "token.txt")).read().strip()
RUTA_OK = re.compile(r"^/[a-z0-9_/-]{1,80}\.json$")
MAX = 64 * 1024
DATOS = {}            # ruta -> bytes (en memoria; tambien a disco para sobrevivir reinicios)
GUARDA = os.path.join(DIR, "datos")
_lock = threading.Lock()


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
        ruta = self.path.split("?")[0]
        with _lock:
            d = DATOS.get(ruta)
        if d is None:
            return self._resp(404, b'{"error":"no"}')
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
