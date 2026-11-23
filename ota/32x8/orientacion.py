# Orientacion de la tira de la 32x8 (mapa LED_MAP_17 de la Awtrix: la tira empieza arriba a
# la derecha). Con GIRADA = True la pantalla va montada girada 180 grados: la tira empieza
# ABAJO A LA IZQUIERDA y el cable queda abajo. Montada como antes: GIRADA = False.
GIRADA = True


def aplicar(mapa):
    """Gira 180 grados, en el sitio, un mapa [fila][x] -> indice LED (filas en orden y
    cada fila al reves). Al cambiarlo en el sitio vale para quien ya lo tenga importado."""
    if GIRADA:
        filas = [list(reversed(f)) for f in reversed(mapa)]
        mapa[:] = filas
    return mapa
