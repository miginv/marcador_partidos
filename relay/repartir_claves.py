#!/usr/bin/env python3
"""Reparte a cada pantalla su clave del servidor del marcador. Pensado para un temporizador en
nano cada 2 min: cada ejecucion intenta las pantallas pendientes y, cuando estan todas, se
desactiva. Las pantallas solo atienden en modo mensajes (en modo marcador no hay API), por eso
se reintenta hasta que respondan.
  /root/.oci/marcador_claves.json    {"obligatoria": true, "claves": {"<clave>": "<nombre>"}}
  /root/.oci/marcador_pantallas.json {"<nombre>": {"host": "...", "tipo": "tc001" | "32x8"}}
  /root/.oci/marcador_reparto.json   estado: nombre -> clave ya entregada
Cuando el Ulanzi tiene su clave de Google se paran el servidor y el recolector de nano."""
import json
import os
import subprocess
import sys
import time
import urllib.request

URL = "http://34.30.243.27"
D = "/root/.oci/"
TEMPORIZADOR = "marcador-repartir-claves.timer"


def log(*a):
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)


def post(url, datos):
    req = urllib.request.Request(url, data=json.dumps(datos).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()


def entregar(nombre, p, clave):
    if p["tipo"] == "tc001":
        r = post("http://%s/api/ajustes" % p["host"],
                 {"relay": {"url": URL, "auto": True, "clave": clave}})
        return URL in r
    if p["tipo"] == "32x8":
        r = post("http://%s/api/settings" % p["host"], {"RELAY_CLAVE": clave, "RELAY_URL": URL})
        return '"relay"' in r          # sin la 1.0.7 contesta solo con el brillo: se reintenta
    raise ValueError("tipo " + p["tipo"])


def main():
    claves = {v: k for k, v in json.load(open(D + "marcador_claves.json"))["claves"].items()}
    pantallas = json.load(open(D + "marcador_pantallas.json"))
    est_f = D + "marcador_reparto.json"
    est = json.load(open(est_f)) if os.path.exists(est_f) else {}
    for nombre, p in pantallas.items():
        clave = claves.get(nombre)
        if not clave or est.get(nombre) == clave:
            continue
        try:
            if entregar(nombre, p, clave):
                est[nombre] = clave
                json.dump(est, open(est_f, "w"), indent=1)
                log("[OK]", nombre, "tiene su clave")
                if nombre == "ulanzi-tc001":
                    subprocess.run(["systemctl", "disable", "--now", "marcador-recolector", "marcador-servidor"])
                    log("[OK] servidor y recolector de nano parados (todo sale de Google)")
            else:
                log("[--]", nombre, "responde pero sin la version nueva, se reintenta")
        except Exception as e:
            log("[--]", nombre, "no responde (modo marcador o apagada):", e)
    if all(est.get(n) == claves.get(n) for n in pantallas if claves.get(n)):
        subprocess.run(["systemctl", "disable", "--now", TEMPORIZADOR])
        log("[FIN] todas las pantallas tienen su clave")
    return 0


if __name__ == "__main__":
    sys.exit(main())
