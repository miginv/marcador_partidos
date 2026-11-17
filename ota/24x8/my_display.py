import micropython
import neopixel
import framebuf
import machine
from awtrix_font import FONT
import time
import my_shared
import urandom

# Configuración del pin de datos y número total de LEDs
# Pin de los LED: "led_pin" en config.json (por defecto 4, el de las placas C3)
try:
    import json as _jp
    with open("config.json") as _f:
        _cfg_led = _jp.load(_f)
except Exception:
    _cfg_led = {}
LED_PIN = int(_cfg_led.get("led_pin", 4))
pin = machine.Pin(LED_PIN)
num_matrices = 3
leds_por_matriz = 64
total_leds = num_matrices * leds_por_matriz
WIDTH = 24
# Envio por bit-banging en vez de RMT: el RMT del C3 tiene poca memoria y necesita
# recargas por interrupcion; si el WiFi las retrasa se desplazan bits y se "mueven" columnas.
# Por defecto RMT. Con "led_bitbang": true en config.json se usa bit-banging, pero en esta
# placa el primer bit sale largo y el LED 0 (esquina sup. izq.) se queda verde.
try:
    import esp32, json as _json
    with open("config.json") as _f:
        _bb = _json.load(_f).get("led_bitbang", False)
    esp32.RMT.bitstream_channel(None if _bb else 0)
except Exception as _e:
    print("[DISPLAY] bitstream_channel:", _e)


class _SpiLeds:
    """WS2812 por SPI+DMA a 2,4 MHz: cada bit del LED son 3 bits SPI (0->100, 1->110).
    El DMA envia la trama entera sin pausas, asi el WiFi no puede cortarla a medias
    (con RMT una pausa larga hace que los LED reinicien y el dibujo salga desplazado)."""
    def __init__(self, n, mosi, sck):
        self.n = n
        self.buf = bytearray(n * 3)          # orden GRB, como neopixel
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


np = None
try:
    import json as _json2
    with open("config.json") as _f:
        _spi_on = _json2.load(_f).get("led_spi", True)
    if _spi_on:
        np = _SpiLeds(total_leds, LED_PIN, int(_cfg_led.get("led_sck", 7)))
except Exception as _e:
    print("[DISPLAY] SPI no disponible, uso neopixel:", _e)
    np = None
if np is None:
    np = neopixel.NeoPixel(pin, total_leds)

def _show():
    # Doble envio: si la actividad WiFi corrompe la primera trama (RMT), la segunda la corrige.
    # (No usar disable_irq: el RMT necesita interrupciones y salta el watchdog.)
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
buf = bytearray(32)
fb = framebuf.FrameBuffer(buf, 32, 8, framebuf.MONO_VLSB)

SCOREBOARD_INTERVAL = 3  # segundos por panel

def show_framebuffer(color):
    bri = min(1.0, my_shared.BRIGHTNESS * 1.5)
    brightness_color = (
        int(color[0] * bri),
        int(color[1] * bri),
        int(color[2] * bri)
    )
    for i in range(num_matrices):
        for y in range(8):
            for x in range(8):
                led_index = i * leds_por_matriz + (y * 8 + x)
                if led_index < total_leds:
                    if fb.pixel(x + (i * 8), y):
                        if color == (0, 0, 0):
                            np[led_index] = (
                            int(urandom.getrandbits(8) * my_shared.BRIGHTNESS),
                            int(urandom.getrandbits(8) * my_shared.BRIGHTNESS),
                            int(urandom.getrandbits(8) * my_shared.BRIGHTNESS)
                            )
                        else:
                            np[led_index] = brightness_color
                    else:
                        np[led_index] = (0, 0, 0)
    _show()

def get_char_width(char):
    if char in FONT:
        char_data = FONT[char]
        width = 0
        for col in range(8):
            if any((row & (1 << (7 - col))) for row in char_data):
                width = col + 1
        return width
    return 0

def draw_char_at_position(char, x, y, color=(0, 0, 255)):
    if char in FONT:
        char_data = FONT[char]
        for row in range(len(char_data)):
            for col in range(8):
                if char_data[row] & (1 << (7 - col)):
                    pixel_x = x + col
                    pixel_y = y + 4 - len(char_data) + row
                    if 0 <= pixel_x < 32 and 0 <= pixel_y < 8:
                        fb.pixel(pixel_x, pixel_y, 1)

def draw_centered_text(text, y, color=(0, 0, 255)):
    text_width = sum(get_char_width(char) + 1 for char in text) - 1
    start_x = max(int((WIDTH - text_width) // 2), 0)

    clear()
    pos_x = start_x
    for char in text:
        draw_char_at_position(char, pos_x, y, color)
        char_width = get_char_width(char)
        pos_x += char_width + 1
    show_framebuffer(color)

def scroll_text_left(text, y, color=(0, 0, 255), delay=0.1):
    text_width = sum(get_char_width(char) + 1 for char in text) - 1
    total_width = WIDTH

    clear()

    pos_x = 0
    for char in text:
        draw_char_at_position(char, pos_x, y, color)
        pos_x += get_char_width(char) + 1
    show_framebuffer(color)
    time.sleep(1)

    for offset in range(text_width + total_width):
        fb.fill(0)
        pos_x = -offset
        for char in text:
            draw_char_at_position(char, pos_x, y, color)
            pos_x += get_char_width(char) + 1
        show_framebuffer(color)
        time.sleep(delay)

def clear():
    fb.fill(0)
    _show()


# ── Marcador ──────────────────────────────────────────────────────────────────

def _led_idx(px, py):
    """Mapa LED para 3 módulos 8x8 en fila, sin zigzag."""
    if px < 0 or px >= WIDTH or py < 0 or py >= 8:
        return -1
    panel = px // 8
    x_in = px % 8
    return panel * 64 + py * 8 + x_in


def _draw_region(text, color, x_min, x_max):
    """Dibuja text centrado en [x_min, x_max) directamente sobre np."""
    bri = min(1.0, my_shared.BRIGHTNESS * 1.5)
    r0, g0, b0 = color
    scaled = (int(r0 * bri), int(g0 * bri), int(b0 * bri))
    # centrado por tinta real (no por ancho de celda): ignora columnas vacias del glifo
    lo_t, hi_t = None, None
    off = 0
    for c in text:
        if c in FONT:
            glyph_cols = [col for col in range(8)
                          if any(r & (1 << (7 - col)) for r in FONT[c])]
            if glyph_cols:
                a, b = off + glyph_cols[0], off + glyph_cols[-1]
                lo_t = a if lo_t is None else min(lo_t, a)
                hi_t = b if hi_t is None else max(hi_t, b)
            off += get_char_width(c) + 1
    if lo_t is None:
        return
    region_w = x_max - x_min
    ink_w = hi_t - lo_t + 1
    start = x_min + max(0, (region_w - ink_w) // 2) - lo_t
    off = 0
    for char in text:
        if char in FONT:
            char_data = FONT[char]
            char_w = get_char_width(char)
            for row_idx, row_val in enumerate(char_data):
                for col in range(8):
                    if row_val & (1 << (7 - col)):
                        px = start + off + col
                        py = 7 - len(char_data) + row_idx  # alineado abajo (+3px)
                        idx = _led_idx(px, py)
                        # recorte a la region: nunca pintar sobre el otro equipo o el reloj
                        if idx >= 0 and x_min <= px < x_max:
                            np[idx] = scaled
            off += char_w + 1


def _np_clear():
    for i in range(total_leds):
        np[i] = (0, 0, 0)


def display_scoreboard(local_name, visitor_name, local_color, visitor_color,
                       local_pts, visitor_pts, minutes, seconds, quarter):
    """Muestra el marcador en 3 paneles de SCOREBOARD_INTERVAL segundos:
    1. Nombres  — izq=local  der=visitante
    2. Puntos   — izq=local  der=visitante
    3. Cuarto + MM:SS con cuenta atrás y parpadeo del separador (5s)
    Layout 24px: [0-11]=izq  [12-23]=der
    Panel 3:     [0-5]=Q  [6-14]=MM  [15-17]=:  [17-24]=SS
    """
    # Panel 1: nombres
    _np_clear()
    _draw_region(local_name.upper(), local_color, 0, 12)
    _draw_region(visitor_name.upper(), visitor_color, 12, 24)
    _show()
    time.sleep(SCOREBOARD_INTERVAL)

    # Panel 2: puntos
    _np_clear()
    _draw_region(str(local_pts), local_color, 0, 12)
    _draw_region(str(visitor_pts), visitor_color, 12, 24)
    _show()
    time.sleep(SCOREBOARD_INTERVAL)

    # Panel 3: cuarto + tiempo (5 ticks de 1s con cuenta atrás)
    show_time(minutes, seconds, quarter, 5)


def show_names(local_name, visitor_name, local_color, visitor_color, duration=5):
    _np_clear()
    _draw_region(local_name.upper(), local_color, 0, 12)
    _draw_region(visitor_name.upper(), visitor_color, 12, 24)
    _show()
    hold(duration)


def show_scores(local_pts, visitor_pts, local_color, visitor_color, duration=5):
    _np_clear()
    _draw_region(str(local_pts), local_color, 0, 12)
    _draw_region(str(visitor_pts), visitor_color, 12, 24)
    _show()
    hold(duration)


def show_time(minutes, seconds, quarter, duration=5):
    """Muestra panel de tiempo durante duration segundos con cuenta atrás interna."""
    rem_min, rem_sec = minutes, seconds
    for tick in range(duration):
        _np_clear()
        _draw_region(str(quarter), (255, 140, 0), 0, 5)
        _draw_region("{:02d}".format(rem_min), (0, 0, 255), 6, 15)
        if tick % 2 == 0:
            _draw_region(":", (0, 0, 255), 14, 17)
        _draw_region("{:02d}".format(rem_sec), (0, 0, 255), 17, 24)
        _show()
        time.sleep(1)
        if rem_sec > 0:
            rem_sec -= 1
        elif rem_min > 0:
            rem_min -= 1
            rem_sec = 59


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
