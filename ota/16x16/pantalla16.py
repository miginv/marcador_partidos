# Pantalla 16x16 (ESP32-C3): una tira de 271 LED, filas en zigzag con 1 LED sin usar en
# cada curva, empezando ABAJO A LA IZQUIERDA (layout 16161).
# Coordenadas: x 0..15 de izquierda a derecha, y 0..15 de arriba a abajo.
# Envio por SPI+DMA (como el 24x8: el WiFi no puede cortar la trama a medias); con
# "led_spi": false en config.json se usa neopixel (RMT).
import json
import time
import machine
import my_shared
from awtrix_font import FONT

FONT["\u20ac"] = [0x30, 0x40, 0xF0, 0x40, 0x30]            # euro
_SIN_ACENTO = {"\u00e1": "a", "\u00e9": "e", "\u00ed": "i", "\u00f3": "o", "\u00fa": "u", "\u00fc": "u",
               "\u00c1": "A", "\u00c9": "E", "\u00cd": "I", "\u00d3": "O", "\u00da": "U", "\u00dc": "U",
               "\u00f1": "n", "\u00d1": "N"}

W = H = WIDTH = 16
PASO = W + 1
N_LEDS = H * PASO - 1              # 271

try:
    with open("config.json") as _f:
        _cfg = json.load(_f)
except Exception:
    _cfg = {}
LED_PIN = int(_cfg.get("led_pin", getattr(my_shared, "PIN_DATA", 4)))
COLOR_ORDER = getattr(my_shared, "COLOR_ORDER", "RGB")


def led_index(x, y):
    fila = H - 1 - y               # fila 0 = la de abajo
    if fila & 1:
        return fila * PASO + W - 1 - x
    return fila * PASO + x


_MAPA = [led_index(i % W, i // W) for i in range(W * H)]   # (y*16 + x) -> LED


class _SpiLeds:
    """WS2812 por SPI a 2,4 MHz: cada bit son 3 bits SPI (0->100, 1->110)."""
    def __init__(self, n, mosi, sck):
        self.n = n
        self.buf = bytearray(n * 3)          # GRB
        lut = bytearray(256 * 3)
        for v in range(256):
            bits = 0
            for i in range(7, -1, -1):
                bits = (bits << 3) | (0b110 if (v >> i) & 1 else 0b100)
            lut[v * 3] = (bits >> 16) & 0xFF
            lut[v * 3 + 1] = (bits >> 8) & 0xFF
            lut[v * 3 + 2] = bits & 0xFF
        self.t3 = [bytes(lut[v * 3:v * 3 + 3]) for v in range(256)]
        self.cero = bytes(40)
        self.spi = machine.SPI(1, baudrate=2400000, polarity=0, phase=0, bits=8,
                               firstbit=machine.SPI.MSB, sck=machine.Pin(sck),
                               mosi=machine.Pin(mosi), miso=None)

    def __len__(self):
        return self.n

    def __setitem__(self, i, c):
        j = i * 3
        self.buf[j] = c[1]
        self.buf[j + 1] = c[0]
        self.buf[j + 2] = c[2]

    def fill(self, c):
        for i in range(self.n):
            self[i] = c

    def write(self):
        # sin viper (no esta en todas las versiones de MicroPython): tabla de 3 bytes por valor
        t = self.t3
        self.spi.write(b"".join([t[v] for v in self.buf]) + self.cero)


np = None
if _cfg.get("led_spi", True):
    try:
        np = _SpiLeds(N_LEDS, LED_PIN, int(_cfg.get("led_sck", 7)))
    except Exception as _e:
        print("[PANTALLA] SPI no disponible, uso neopixel:", _e)
if np is None:
    import neopixel
    np = neopixel.NeoPixel(machine.Pin(LED_PIN), N_LEDS)
del _cfg


def escala(c, extra=1.0):
    """Color con el brillo aplicado y en el orden de la tira."""
    b = my_shared.BRIGHTNESS * extra
    r, g, bl = (max(1, int(v * b)) if v else 0 for v in c)
    return (g, r, bl) if COLOR_ORDER == "GRB" else (r, g, bl)


def limpiar():
    np.fill((0, 0, 0))


def mostrar():
    np.write()


def pixel(x, y, c):
    """c ya escalado (escala())."""
    if 0 <= x < W and 0 <= y < H:
        np[_MAPA[y * W + x]] = c


def columnas(cols, color, x0, y0, xmin=0, xmax=W):
    """cols: enteros por columna (bit 0 = fila y0)."""
    c = escala(color)
    for i, col in enumerate(cols):
        x = x0 + i
        if xmin <= x < xmax and col:
            y = 0
            while col and y0 + y < H:
                if col & 1:
                    pixel(x, y0 + y, c)
                col >>= 1
                y += 1


# ---------- texto con la fuente de la Awtrix (5 px, alineada abajo) ----------
FILA1 = 6           # linea base (fila de abajo del texto) de la primera fila
FILA2 = 14          # de la segunda fila


def ancho_car(ch):
    ch = _SIN_ACENTO.get(ch, ch)
    cw = 0
    for r in FONT.get(ch, ()):
        for col in range(8):
            if r & (1 << (7 - col)):
                cw = max(cw, col + 1)
    return cw or 3


def ancho(t):
    return sum(ancho_car(c) + 1 for c in t) - 1 if t else 0


def texto(t, x, base, color, xmin=0, xmax=W):
    """Pinta t con la letra mas a la izquierda en x y la fila de abajo en base."""
    c = escala(color)
    for ch in t:
        ch = _SIN_ACENTO.get(ch, ch)
        filas = FONT.get(ch)
        if filas:
            n = len(filas)
            for r, v in enumerate(filas):
                py = base - (n - 1 - r)
                for col in range(8):
                    if v & (1 << (7 - col)):
                        px = x + col
                        if xmin <= px < xmax:
                            pixel(px, py, c)
        x += ancho_car(ch) + 1
    return x


# ---------- compatibilidad con wifi_portal (dibuja en la segunda fila) ----------

class _FB:
    def __init__(self):
        self.p = set()

    def fill(self, v):
        self.p = set()


fb = _FB()


def _ancho_scroll(c):
    return ancho_car(c)


def draw_char_at_position(ch, x, y=0, color=None):
    filas = FONT.get(ch)
    if filas:
        n = len(filas)
        for r, v in enumerate(filas):
            for col in range(8):
                if v & (1 << (7 - col)) and 0 <= x + col < W:
                    fb.p.add((x + col, FILA2 - (n - 1 - r)))


def show_framebuffer(color):
    limpiar()
    c = escala(color)
    for x, y in fb.p:
        pixel(x, y, c)
    mostrar()


def draw_centered_text(t, y=0, color=(255, 255, 255)):
    limpiar()
    texto(t, max(0, (W - ancho(t)) // 2), FILA2 if ancho(t) <= W else FILA2, color)
    mostrar()


def clear():
    limpiar()
    mostrar()
