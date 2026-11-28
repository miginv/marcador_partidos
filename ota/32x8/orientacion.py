# Orientacion de la tira de la 32x8 (mapa LED_MAP_17 de la Awtrix: la tira empieza arriba a
# la derecha). Por defecto la pantalla va girada 180 grados (la tira empieza ABAJO A LA
# IZQUIERDA y el cable queda abajo). Cada placa puede llevar su propio orientacion.txt
# (no va en la OTA) con una de estas palabras:
#   girada    -> 180 grados (por defecto)
#   vertical  -> solo se invierten las filas (otra forma de cablear la entrada abajo a la izq.)
#   normal    -> como la Awtrix original
# Pantallas de 4 matrices 8x8 (my_shared.MATRIX_TILES = 4): el mapa es el de modulos 8x8
# encadenados de izquierda a derecha, filas sin zigzag (LED = x//8*64 + y*8 + x%8), y por
# defecto van "normal"; orientacion.txt "girada" o "vertical" tambien vale para ellas.
GIRADA = True       # compatibilidad: sin orientacion.txt, girada


def _tiles4():
    try:
        import my_shared
        return getattr(my_shared, "MATRIX_TILES", 17) == 4
    except Exception:
        return False


def modo():
    try:
        with open("orientacion.txt") as f:
            m = f.read().strip().lower()
        if m in ("girada", "vertical", "normal"):
            return m
    except Exception:
        pass
    return "girada" if GIRADA and not _tiles4() else "normal"


def aplicar(mapa):
    """Cambia en el sitio un mapa [fila][x] -> indice LED (asi vale para quien ya lo tenga
    importado)."""
    if _tiles4():
        mapa[:] = [[(x // 8) * 64 + y * 8 + x % 8 for x in range(32)] for y in range(8)]
    m = modo()
    if m == "girada":
        mapa[:] = [list(reversed(f)) for f in reversed(mapa)]
    elif m == "vertical":
        mapa[:] = [list(f) for f in reversed(mapa)]
    return mapa
