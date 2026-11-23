# Matriz 16x16 en una tira, como el layout 17 del 32x8 pero con filas de 16 y empezando
# ABAJO A LA IZQUIERDA: fila de abajo izq->der, 1 LED sin usar en la curva, la siguiente der->izq...
# Coordenadas: x 0..15 de izquierda a derecha, y 0..15 de arriba a abajo.
import machine
import neopixel
import my_shared

W = H = 16
PASO = W + 1                       # 16 LED por fila + 1 en la curva
N_LEDS = H * PASO - 1              # 271
np = neopixel.NeoPixel(machine.Pin(my_shared.PIN_DATA), N_LEDS)


def led_index(x, y):
    fila = H - 1 - y               # fila 0 = la de abajo
    if fila & 1:
        return fila * PASO + W - 1 - x
    return fila * PASO + x


_MAPA = [led_index(i % W, i // W) for i in range(W * H)]   # (y*16 + x) -> LED


def _escala(c):
    b = my_shared.BRIGHTNESS
    r, g, bl = (max(1, int(v * b)) if v else 0 for v in c)
    return (g, r, bl) if my_shared.COLOR_ORDER == "GRB" else (r, g, bl)


def pintar_capas(capas):
    """capas: lista de (cols, color, dy). cols = enteros de 16 bits por columna (bit 0 = fila
    de arriba de la capa), dy = fila donde empieza. Cada capa se centra en horizontal.
    Borra el resto de la pantalla."""
    np.fill((0, 0, 0))
    for cols, color, dy in capas:
        c = _escala(color)
        x0 = (W - len(cols)) // 2
        for i, col in enumerate(cols):
            x = x0 + i
            if 0 <= x < W and col:
                for y in range(H - dy):
                    if col >> y & 1:
                        np[_MAPA[(y + dy) * W + x]] = c
    np.write()


def pintar_columnas(cols, color):
    pintar_capas([(cols, color, 0)])


def apagar():
    np.fill((0, 0, 0))
    np.write()
