#!/usr/bin/env python3
"""Prueba sin partido real: publica en el servidor una lista con un partido ficticio que
empieza ahora (notif "demo1") y un marcador que va cambiando cada 5 s.
No ejecutar a la vez que recolector.py (los dos publican /partidos.json).
Uso: RELAY_URL=http://127.0.0.1:8080 python3 simular.py"""
import random
import time
import recolector as r

ts = int(time.time()) - 60
fecha = time.strftime("%d/%m/%Y", time.localtime(ts))
hora = time.strftime("%H:%M", time.localtime(ts))
r.publicar("/partidos.json", {"actualizado": "simulacion", "partidos": [{
    "ts": ts, "fecha": fecha, "hora": hora, "local": "SERRACINES", "visit": "PRUEBA",
    "notif": "demo1", "buscar": "serracines", "skip": 0}]})
rl = rv = 0
seg = 10 * 60
cuarto = 1
n = 0
while True:
    n += 1
    if random.random() < 0.5:
        if random.random() < 0.5:
            rl += random.choice((1, 2, 2, 3))
        else:
            rv += random.choice((1, 2, 2, 3))
    seg -= 5
    if seg <= 0:
        cuarto, seg = cuarto + 1, 10 * 60
    m = {"rl": rl, "rv": rv, "cuarto": "Q%d" % cuarto, "tiempo": "%02d:%02d" % (seg // 60, seg % 60),
         "estado": "EN JUEGO", "vivo": True, "jugada": None, "descanso": False, "parado": False,
         "hora_acc": None}
    r.publicar("/m/demo1.json", {"clave": "demo1", "al": "SERRACINES", "av": "PRUEBA", "hora": hora,
                                 "m": m, "t": int(time.time()), "n": n})
    print(time.strftime("%H:%M:%S"), rl, "-", rv, m["cuarto"], m["tiempo"], flush=True)
    time.sleep(5)
