# Pantalla del marcador FBM para la tira 32x8 en zigzag (264 LEDs: 33 por fila,
# el LED de cada curva no se ve). Mismo comportamiento que my_display del marcador
# 24x8, con el mapa LED_MAP_17 de la Awtrix. No usa my_display.py (el de la Awtrix
# crea su propio NeoPixel en el pin 4).
import micropython
import machine
import time
import framebuf
import my_shared
from awtrix_font import FONT

WIDTH = 32
TOTAL_LEDS = 264
PIN_DATA = 4
PIN_SCK = 7          # el SPI necesita un pin de reloj; no va conectado a nada

# Mapa copiado de my_display.py (MATRIX_TILES = 17): fila 0 arriba, x de izquierda a
# derecha. Filas pares van der->izq, impares izq->der; 32, 65, 98... son las curvas.
LED_MAP = [
    [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64],
    [97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83, 82, 81, 80, 79, 78, 77, 76, 75, 74, 73, 72, 71, 70, 69, 68, 67, 66],
    [99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130],
    [163, 162, 161, 160, 159, 158, 157, 156, 155, 154, 153, 152, 151, 150, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 139, 138, 137, 136, 135, 134, 133, 132],
    [165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196],
    [229, 228, 227, 226, 225, 224, 223, 222, 221, 220, 219, 218, 217, 216, 215, 214, 213, 212, 211, 210, 209, 208, 207, 206, 205, 204, 203, 202, 201, 200, 199, 198],
    [231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262],
]
import orientacion
orientacion.aplicar(LED_MAP)    # pantalla montada girada: la tira empieza abajo a la izquierda


class _SpiLeds:
    """WS2812 por SPI+DMA a 2,4 MHz: cada bit del LED son 3 bits SPI (0->100, 1->110).
    El DMA envia la trama entera sin pausas, asi el WiFi no puede cortarla a medias."""
    def __init__(self, n, mosi, sck):
        self.n = n
        self.buf = bytearray(n * 3)          # orden GRB
        self.out = bytearray(n * 9 + 40)     # 3 bytes SPI por byte de color + ceros de reset
        lut = bytearray(256 * 3)
        for v in range(256):
            bits = 0
            for i in range(7, -1, -1):
                bits = (bits << 3) | (0b110 if (v >> i) & 1 else 0b100)
            lut[v * 3] = (bits >> 16) & 0xFF
            lut[v * 3 + 1] = (bits >> 8) & 0xFF
            lut[v * 3 + 2] = bits & 0xFF
        self.lut = lut
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

    def __getitem__(self, i):
        j = i * 3
        return (self.buf[j + 1], self.buf[j], self.buf[j + 2])

    def fill(self, c):
        for i in range(self.n):
            self[i] = c

    @micropython.viper
    def _encode(self):
        src = ptr8(self.buf)
        dst = ptr8(self.out)
        lut = ptr8(self.lut)
        n = int(len(self.buf))
        k = 0
        for i in range(n):
            v = src[i] * 3
            dst[k] = lut[v]
            dst[k + 1] = lut[v + 1]
            dst[k + 2] = lut[v + 2]
            k += 3

    def write(self):
        self._encode()
        self.spi.write(self.out)


try:
    np = _SpiLeds(TOTAL_LEDS, PIN_DATA, PIN_SCK)
except Exception as _e:
    print("[DISPLAY] SPI no disponible, uso neopixel:", _e)
    import neopixel
    np = neopixel.NeoPixel(machine.Pin(PIN_DATA), TOTAL_LEDS)


def _show():
    np.write()
    time.sleep_ms(2)
    np.write()


def hold(seconds, step=0.5):
    """Espera reenviando la trama cada step s: un fallo puntual dura como mucho medio segundo."""
    t_end = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while True:
        left = time.ticks_diff(t_end, time.ticks_ms())
        if left <= 0:
            break
        time.sleep_ms(min(int(step * 1000), left))
        np.write()


fb = framebuf.FrameBuffer(bytearray(WIDTH), WIDTH, 8, framebuf.MONO_VLSB)


def _led_idx(px, py):
    if px < 0 or px >= WIDTH or py < 0 or py >= 8:
        return -1
    return LED_MAP[py][px]


def _bri():
    return min(1.0, my_shared.BRIGHTNESS * 1.5)


def show_framebuffer(color):
    bri = _bri()
    c = (int(color[0] * bri), int(color[1] * bri), int(color[2] * bri))
    off = (0, 0, 0)
    for i in range(TOTAL_LEDS):        # incluye los LED de las curvas: siempre apagados
        np[i] = off
    for y in range(8):
        fila = LED_MAP[y]
        for x in range(WIDTH):
            if fb.pixel(x, y):
                np[fila[x]] = c
    _show()


def get_char_width(char):
    if char in FONT:
        width = 0
        for col in range(8):
            if any((row & (1 << (7 - col))) for row in FONT[char]):
                width = col + 1
        return width
    return 0


def draw_char_at_position(char, x, y):
    if char in FONT:
        char_data = FONT[char]
        for row in range(len(char_data)):
            for col in range(8):
                if char_data[row] & (1 << (7 - col)):
                    px = x + col
                    py = y + 4 - len(char_data) + row
                    if 0 <= px < WIDTH and 0 <= py < 8:
                        fb.pixel(px, py, 1)


def draw_centered_text(text, y, color=(0, 0, 255)):
    text_width = sum(get_char_width(c) + 1 for c in text) - 1
    start_x = max(int((WIDTH - text_width) // 2), 0)
    fb.fill(0)
    pos_x = start_x
    for c in text:
        draw_char_at_position(c, pos_x, y)
        pos_x += get_char_width(c) + 1
    show_framebuffer(color)


def clear():
    fb.fill(0)
    _np_clear()
    _show()


def _np_clear():
    for i in range(TOTAL_LEDS):
        np[i] = (0, 0, 0)


def _draw_region(text, color, x_min, x_max):
    """Dibuja text centrado (por tinta real) en [x_min, x_max), alineado abajo."""
    bri = _bri()
    scaled = (int(color[0] * bri), int(color[1] * bri), int(color[2] * bri))
    lo_t, hi_t = None, None
    off = 0
    for c in text:
        if c in FONT:
            cols = [col for col in range(8) if any(r & (1 << (7 - col)) for r in FONT[c])]
            if cols:
                a, b = off + cols[0], off + cols[-1]
                lo_t = a if lo_t is None else min(lo_t, a)
                hi_t = b if hi_t is None else max(hi_t, b)
            off += get_char_width(c) + 1
    if lo_t is None:
        return
    ink_w = hi_t - lo_t + 1
    start = x_min + max(0, (x_max - x_min - ink_w) // 2) - lo_t
    off = 0
    for c in text:
        if c in FONT:
            char_data = FONT[c]
            for row_idx, row_val in enumerate(char_data):
                for col in range(8):
                    if row_val & (1 << (7 - col)):
                        px = start + off + col
                        py = 7 - len(char_data) + row_idx
                        idx = _led_idx(px, py)
                        if idx >= 0 and x_min <= px < x_max:
                            np[idx] = scaled
            off += get_char_width(c) + 1


MITAD = WIDTH // 2


def show_names(local_name, visitor_name, local_color, visitor_color, duration=5):
    _np_clear()
    _draw_region(local_name.upper(), local_color, 0, MITAD)
    _draw_region(visitor_name.upper(), visitor_color, MITAD, WIDTH)
    _show()
    hold(duration)


def _ancho_scroll(c):
    return 2 if c == " " else get_char_width(c)


def scroll_texto(text, color, segundos=5, y=3):
    """Texto que entra por la derecha y sale por la izquierda en 'segundos' (ultima jugada)."""
    w = sum(_ancho_scroll(c) + 1 for c in text) - 1
    pasos = w + WIDTH
    t0 = time.ticks_ms()
    for k in range(pasos + 1):
        fb.fill(0)
        x = WIDTH - k
        for c in text:
            draw_char_at_position(c, x, y)
            x += _ancho_scroll(c) + 1
        show_framebuffer(color)
        espera = time.ticks_diff(time.ticks_add(t0, (k + 1) * segundos * 1000 // (pasos + 1)),
                                 time.ticks_ms())
        if espera > 0:
            time.sleep_ms(espera)
