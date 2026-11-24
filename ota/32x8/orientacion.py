# Orientacion de la tira de la 32x8 (mapa LED_MAP_17 de la Awtrix: la tira empieza arriba a
# la derecha). Por defecto la pantalla va girada 180 grados (la tira empieza ABAJO A LA
# IZQUIERDA y el cable queda abajo). Cada placa puede llevar su propio orientacion.txt
# (no va en la OTA) con una de estas palabras:
#   girada    -> 180 grados (por defecto)
#   vertical  -> solo se invierten las filas (otra forma de cablear la entrada abajo a la izq.)
#   normal    -> como la Awtrix original
GIRADA = True       # compatibilidad: sin orientacion.txt, girada


def modo():
    try:
        with open("orientacion.txt") as f:
            m = f.read().strip().lower()
        if m in ("girada", "vertical", "normal"):
            return m
    except Exception:
        pass
    return "girada" if GIRADA else "normal"


def aplicar(mapa):
    """Cambia en el sitio un mapa [fila][x] -> indice LED (asi vale para quien ya lo tenga
    importado)."""
    m = modo()
    if m == "girada":
        mapa[:] = [list(reversed(f)) for f in reversed(mapa)]
    elif m == "vertical":
        mapa[:] = [list(f) for f in reversed(mapa)]
    return mapa
