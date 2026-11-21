# Pantalla del marcador FBM para el Ulanzi TC001 (32x8, 256 LEDs en zigzag por filas,
# GPIO32). Mismo comportamiento que el marcador 32x8; pines y mapa en hw_tc001.py.
import machine
import time
import framebuf
import my_shared
from awtrix_font import FONT

from hw_tc001 import WIDTH, TOTAL_LEDS, PIN_DATA, led_index   # Ulanzi TC001


# En el ESP32 del TC001 el driver SPI (con codigo viper) cuelga la red: neopixel (RMT)
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
    return led_index(px, py)


def _bri():
    return min(1.0, my_shared.BRIGHTNESS * 1.5)


def show_framebuffer(color):
    bri = _bri()
    c = (int(color[0] * bri), int(color[1] * bri), int(color[2] * bri))
    off = (0, 0, 0)
    for i in range(TOTAL_LEDS):        # incluye los LED de las curvas: siempre apagados
        np[i] = off
    for y in range(8):
        for x in range(WIDTH):
            if fb.pixel(x, y):
                np[led_index(x, y)] = c
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
