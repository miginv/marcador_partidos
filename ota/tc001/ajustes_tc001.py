# Ajustes propios del TC001: brillo automatico por el sensor de luz y servidor del marcador.
# (Que mensajes llegan a esta pantalla lo decide nano: telegram_bot.awtrix_iconos_permitidos.)
# Se guardan en ajustes_tc001.json (no se toca config.json). Se cambian por la API:
#   GET  /api/ajustes                      -> ajustes actuales + luz medida
#   POST /api/ajustes  {"brillo": {...}}   -> cambia solo las claves que se manden
#   POST /api/settings {"ABRI": true/false} (como Awtrix 3) activa/desactiva el automatico
import json
import time
import my_shared
import hw_tc001

FICHERO = "ajustes_tc001.json"

AJUSTES = {
    "brillo": {
        "auto": True,
        "min": 1,            # nivel 0-255 a oscuras: 1 = lo minimo que se ve
        "max": 50,           # % con mucha luz
        "luz_oscuro": 60,    # lectura del sensor (0-1023) por debajo = oscuro -> min
        "luz_max": 700,      # lectura a partir de la cual va al max
    },
    # servidor propio del marcador (relay/servidor.py): http normal, sin TLS
    "relay": {
        "url": "",           # p. ej. http://1.2.3.4:8080 ; vacio = sin modo marcador
        "auto": False,       # pasar solo a marcador 15 min antes de un partido de la lista
        "clave": "",         # clave de esta pantalla en el servidor (?k=...)
    },
}


def cargar():
    try:
        with open(FICHERO) as f:
            datos = json.load(f)
        for k in AJUSTES:
            if isinstance(datos.get(k), dict):
                AJUSTES[k].update(datos[k])
    except Exception:
        pass


def guardar():
    try:
        with open(FICHERO, "w") as f:
            json.dump(AJUSTES, f)
    except Exception as e:
        print("[AJUSTES] no se pudo guardar:", e)


def cambiar(nuevos):
    for k, v in nuevos.items():
        if k in AJUSTES and isinstance(v, dict):
            AJUSTES[k].update(v)
    guardar()
    global _ultimo
    _ultimo = 0                    # aplicar el brillo ya
    return AJUSTES


# ---------- brillo automatico ----------
_media = None
_ultimo = 0


def brillo_auto():
    """Llamar a menudo: cada segundo lee la luz (media suavizada) y ajusta el brillo."""
    global _media, _ultimo
    b = AJUSTES["brillo"]
    if not b.get("auto"):
        return
    ahora = time.time()
    if ahora - _ultimo < 1:
        return
    _ultimo = ahora
    luz = hw_tc001.luz()
    _media = luz if _media is None else _media * 0.8 + luz * 0.2
    lo, hi = b.get("luz_oscuro", 60), b.get("luz_max", 700)
    minimo = max(1, b.get("min", 1)) / 255
    maximo = max(minimo, b.get("max", 50) / 100)
    if _media <= lo:
        nuevo = minimo
    elif _media >= hi:
        nuevo = maximo
    else:
        nuevo = minimo + (maximo - minimo) * (_media - lo) / (hi - lo)
    if abs(nuevo - my_shared.BRIGHTNESS) > 0.002:
        my_shared.BRIGHTNESS = nuevo


def estado():
    d = {"brillo_actual": int(my_shared.BRIGHTNESS * 1000) / 10,
         "luz": hw_tc001.luz(), "luz_media": int(_media or 0)}
    d.update(AJUSTES)
    rel = dict(AJUSTES.get("relay", {}))
    if rel.get("clave"):
        rel["clave"] = "****"          # la clave no se ensena por la API
    d["relay"] = rel
    return d


cargar()
