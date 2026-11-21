import machine, neopixel, time, os, struct
import framebuf
from awtrix_font import FONT
import my_shared

# --- CONFIGURACIÓN ---
import hw_tc001                      # Ulanzi TC001: GPIO32, 256 LEDs en zigzag
PIN_DATA = hw_tc001.PIN_DATA
_led_count = hw_tc001.TOTAL_LEDS
np = neopixel.NeoPixel(machine.Pin(PIN_DATA), _led_count)
fb = framebuf.FrameBuffer(bytearray(32), 32, 8, framebuf.MONO_VLSB)

# 2. Orden: Si el Rojo y el Verde salen cambiados, pon "GRB"
COLOR_ORDER = "RGB"

# Ulanzi TC001: el mapa de LEDs esta en hw_tc001.led_index


def scale_rgb(r, g, b, scale):
    if scale <= 0:
        return 0, 0, 0
    return min(255, int(r * scale)), min(255, int(g * scale)), min(255, int(b * scale))


class GifPlayer:
    def __init__(self, filename):
        self.f = open(filename, 'rb')
        self.f.seek(10)
        packed = ord(self.f.read(1))
        self.gct_size = 3 * (2 << (packed & 0x07)) if packed & 0x80 else 0
        self.f.seek(13)
        self.gct = self.f.read(self.gct_size)
        self.start_pos = 13 + self.gct_size
        self.transparent_idx = -1  # se actualiza con cada GCE

    def decompress_lzw(self, min_code_size, data):
        clear_code = 1 << min_code_size
        end_code = clear_code + 1
        code_size = min_code_size + 1
        result = []
        table = [[i] for i in range(clear_code + 2)]
        bit_buf = bit_count = pos = 0

        def get_code():
            nonlocal bit_buf, bit_count, pos
            while bit_count < code_size:
                if pos >= len(data):
                    return end_code
                bit_buf |= data[pos] << bit_count
                pos += 1
                bit_count += 8
            code = bit_buf & ((1 << code_size) - 1)
            bit_buf >>= code_size
            bit_count -= code_size
            return code

        prev_code = None
        while True:
            code = get_code()
            if code == end_code:
                break
            if code == clear_code:
                table = [[i] for i in range(clear_code + 2)]
                code_size = min_code_size + 1
                prev_code = None
                continue
            if code < len(table):
                val = table[code]
                if prev_code is not None:
                    table.append(table[prev_code] + [val[0]])
            else:
                val = table[prev_code] + [table[prev_code][0]]
                table.append(val)
            result.extend(val)
            prev_code = code
            if len(table) == (1 << code_size) and code_size < 12:
                code_size += 1
        return result

    def get_next_frame(self):
        """Busca el siguiente frame de imagen y devuelve indices y su paleta específica"""
        max_iters = 5000
        iters = 0
        while iters < max_iters:
            iters += 1
            block = self.f.read(1)
            if not block or block == b'\x3b':
                self.f.seek(self.start_pos)
                continue
            if block == b'\x21':
                ext = self.f.read(1)
                if ext == b'\xf9':  # Graphic Control Extension
                    sz = self.f.read(1)
                    if sz and ord(sz) >= 4:
                        gce = self.f.read(ord(sz))
                        if gce and (gce[0] & 0x01):  # transparent flag
                            self.transparent_idx = gce[3]
                        else:
                            self.transparent_idx = -1
                        self.f.read(1)  # block terminator
                    continue
                sub_iters = 0
                while sub_iters < 256:
                    sub_iters += 1
                    size_b = self.f.read(1)
                    if not size_b or ord(size_b) == 0:
                        break
                    self.f.read(ord(size_b))
                continue
            if block == b'\x2c':
                self.f.read(8)
                packed = ord(self.f.read(1))
                palette = self.f.read(3 * (2 << (packed & 0x07))) if packed & 0x80 else self.gct
                lzw_min = ord(self.f.read(1))
                data = b''
                sub_iters = 0
                while sub_iters < 4096:
                    sub_iters += 1
                    s = self.f.read(1)
                    if not s or ord(s) == 0:
                        break
                    data += self.f.read(ord(s))
                return self.decompress_lzw(lzw_min, data), palette
        # Si se supera el límite, reiniciar y devolver vacío
        self.f.seek(self.start_pos)
        return [], b''


def led_index(x, y):
    if x < 0 or x >= 32 or y < 0 or y >= 8:
        return 0
    return hw_tc001.led_index(x, y)

def draw_char_base(char, x, line_offset=0, min_x=0):
    if char in FONT:
        char_data = FONT[char]
        for r_idx, r_val in enumerate(char_data):
            for c in range(8):
                if r_val & (1 << (7 - c)):
                    px, py = x + c, 7 - (len(char_data) - 1 - r_idx) + line_offset
                    if min_x <= px < 32 and 0 <= py < 8:
                        fb.pixel(px, py, 1)
                        fb.pixel(px, py, 1)


def get_text_width(text):
    w = 0
    for c in text:
        if c in FONT:
            char_data = FONT[c]
            cw = 0
            for r in char_data:
                for col in range(8):
                    if r & (1 << (7 - col)):
                        cw = max(cw, col + 1)
            w += (cw if cw > 0 else 3) + 1
    return w - 1


def get_char_width(char):
    if char in FONT:
        char_data = FONT[char]
        cw = 0
        for r in char_data:
            for col in range(8):
                if r & (1 << (7 - col)):
                    cw = max(cw, col + 1)
        return cw if cw > 0 else 3
    return 3


def _get_gif_color(indices, palette, x, y, transparent_idx=-1):
    if not indices or len(indices) < 64:
        return None
    color_idx = indices[y * 8 + x]
    if color_idx == transparent_idx:
        return None
    c_ptr = color_idx * 3
    if c_ptr + 2 >= len(palette):
        return None
    r, g, b = palette[c_ptr], palette[c_ptr + 1], palette[c_ptr + 2]
    if max(r, g, b) < my_shared.BLACK_THRESHOLD:
        return None
    return scale_rgb(r, g, b, my_shared.BRIGHTNESS * my_shared.GIF_BRIGHTNESS)


def draw_text_line(text, start_x, line_offset=0, min_x=0):
    current_x = start_x
    for i, char in enumerate(text):
        if char in FONT:
            draw_char_base(char, current_x, line_offset, min_x=min_x)
            current_x += get_char_width(char)
        else:
            current_x += 3
        if i < len(text) - 1:
            current_x += 1
    return current_x


def process_awtrix(payload):
    try:
        _process_awtrix(payload)
    except Exception as e:
        print("Error fatal en process_awtrix, ignorando mensaje:", e)


def _process_awtrix(payload):
    text = str(payload.get("text", ""))
    color_req = payload.get("color", [255, 255, 255])
    icon_id = payload.get("icon", None)
    repeat = min(int(payload.get("repeat", 1)), 8)  # máximo 8 repeticiones
    speed = payload.get("scrollspeed", 50)

    if payload.get("textCase") == 1:
        text = text.lower()
    elif payload.get("textCase") == 2:
        text = text.upper()

    player = None
    if icon_id:
        try:
            player = GifPlayer("/ICONS/{}.gif".format(icon_id))
        except Exception as e:
            print("Error cargando icono {}: {}".format(icon_id, e))
            # Intentar descargar el icono
            import my_network
            if my_network.download_icon(icon_id):
                try:
                    player = GifPlayer("/ICONS/{}.gif".format(icon_id))
                except Exception as e:
                    print("Error cargando icono {} tras descarga: {}".format(icon_id, e))
                    player = None
            else:
                print("No se pudo descargar icono {}".format(icon_id))
                player = None

    t_w = get_text_width(text)
    is_static = t_w <= 24
    line_offset = -my_shared.TEXT_LINE  # Offset vertical en píxeles
    last_frame = (None, None)

    for _ in range(repeat):
        frames = range(32, 7 - t_w, -1) if not is_static else range(40)
        
        for x_pos in frames:
            fb.fill(0)  # Limpiar framebuffer al inicio de cada frame
            if is_static:
                curr_x = 8 + (24 - t_w) // 2 if player else (32 - t_w) // 2
            else:
                curr_x = x_pos
            
            temp_x = curr_x
            draw_text_line(text, temp_x, line_offset, min_x=8 if player else 0)

            if player:
                try:
                    indices, palette = player.get_next_frame()
                    if not indices or len(indices) < 64 or not palette:
                        indices, palette = last_frame
                    else:
                        last_frame = (indices, palette)
                except Exception as e:
                    print("Error obteniendo frame: {}".format(e))
                    indices, palette = last_frame
            else:
                indices, palette = None, None

            for x in range(32):
                for y in range(8):
                    idx = led_index(x, y)
                    color = (0, 0, 0)
                    if x < 8 and player:
                        gif_color = _get_gif_color(indices, palette, x, y, player.transparent_idx)
                        if gif_color:
                            color = gif_color if COLOR_ORDER == "RGB" else (gif_color[1], gif_color[0], gif_color[2])
                    if fb.pixel(x, y):
                        tr, tg, tb = color_req[0], color_req[1], color_req[2]
                        color = (int(tr * my_shared.BRIGHTNESS), int(tg * my_shared.BRIGHTNESS), int(tb * my_shared.BRIGHTNESS)) if COLOR_ORDER == "RGB" else (int(tg * my_shared.BRIGHTNESS), int(tr * my_shared.BRIGHTNESS), int(tb * my_shared.BRIGHTNESS))
                    np[idx] = color

            np.write()
            time.sleep_ms(speed if not is_static else 100)

    if player:
        player.f.close()


import urandom


def display_match_results(text_izq, color_izq, text_der, color_der, duracion=3, font=None):
    """Dibuja dos textos centrados en cada mitad (izq/der). font=None → FONT global."""
    if font is None:
        font = FONT

    for i in range(len(np)):
        np[i] = (0, 0, 0)

    str_izq, str_der = str(text_izq), str(text_der)

    def _w(text):
        w = 0
        for ch in text:
            if ch in font:
                cw = 0
                for row in font[ch]:
                    for col in range(8):
                        if row & (1 << (7 - col)):
                            cw = max(cw, col + 1)
                w += (cw if cw > 0 else 3) + 1
            else:
                w += 4
        return max(0, w - 1)

    start_x_izq = (16 - _w(str_izq)) // 2
    start_x_der = 16 + (16 - _w(str_der)) // 2

    def draw_direct(text, start_x, color):
        current_x = start_x
        for char in text:
            if char in font:
                char_data = font[char]
                char_width = 0
                top_offset = max(0, 8 - len(char_data) - 1)
                for r_idx, r_val in enumerate(char_data):
                    for c in range(8):
                        if r_val & (1 << (7 - c)):
                            px = current_x + c
                            py = r_idx + top_offset
                            if 0 <= px < 32 and 0 <= py < 8:
                                idx = led_index(px, py)
                                r, g, b = color[0], color[1], color[2]
                                if COLOR_ORDER == "GRB":
                                    np[idx] = (int(g * my_shared.BRIGHTNESS), int(r * my_shared.BRIGHTNESS), int(b * my_shared.BRIGHTNESS))
                                else:
                                    np[idx] = (int(r * my_shared.BRIGHTNESS), int(g * my_shared.BRIGHTNESS), int(b * my_shared.BRIGHTNESS))
                            char_width = max(char_width, c + 1)
                current_x += (char_width if char_width > 0 else 3) + 1
            else:
                current_x += 4

    draw_direct(str_izq, start_x_izq, color_izq)
    draw_direct(str_der, start_x_der, color_der)
    np.write()
    time.sleep(duracion)


SCOREBOARD_INTERVAL = 3  # seconds per panel


def _np_draw_text_region(text, color, x_min, x_max, font=None):
    """Dibuja text centrado en [x_min, x_max). color=(R,G,B) 0-255; aplica BRIGHTNESS.
    font=None usa FONT global. Compatible con fuentes de cualquier altura (≤8 rows)."""
    if font is None:
        font = FONT
    # Calcular ancho con la fuente dada
    w = 0
    for ch in text:
        if ch in font:
            cw = 0
            for row in font[ch]:
                for col in range(8):
                    if row & (1 << (7 - col)):
                        cw = max(cw, col + 1)
            w += (cw if cw > 0 else 3) + 1
        else:
            w += 4
    w = max(0, w - 1)
    region_w = x_max - x_min
    start_x = x_min + max(0, (region_w - w) // 2)
    br = my_shared.BRIGHTNESS
    r, g, b = color
    if COLOR_ORDER == "GRB":
        scaled = (int(g * br), int(r * br), int(b * br))
    else:
        scaled = (int(r * br), int(g * br), int(b * br))
    current_x = start_x
    for char in text:
        if char in font:
            char_data = font[char]
            char_w = 0
            top_offset = max(0, 8 - len(char_data) - 1)
            for r_idx, r_val in enumerate(char_data):
                for c in range(8):
                    if r_val & (1 << (7 - c)):
                        px = current_x + c
                        py = r_idx + top_offset
                        if x_min <= px < x_max and 0 <= py < 8:
                            np[led_index(px, py)] = scaled
                        char_w = max(char_w, c + 1)
            current_x += (char_w if char_w > 0 else 3) + 1
        else:
            current_x += 4


def display_scoreboard(local_name, visitor_name, local_color, visitor_color,
                       local_pts, visitor_pts, minutes, seconds, quarter):
    """Marcador en 3 pantallas de SCOREBOARD_INTERVAL segundos:
    1. Nombres (mitades izq=local, der=visitante)
    2. Puntos  (mitades izq=local, der=visitante)
    3. Cuarto Q{n} (cols 0-9) + tiempo MM:SS (cols 10-31)
    Colores en formato [R, G, B] 0-255.
    """
    from awtrix_font_8px import FONT_8PX

    # Panel 1: nombres de equipos
    display_match_results(
        local_name.upper()[:3], local_color,
        visitor_name.upper()[:3], visitor_color,
        duracion=SCOREBOARD_INTERVAL,
        font=FONT_8PX,
    )

    # Panel 2: marcador
    display_match_results(
        str(local_pts), local_color,
        str(visitor_pts), visitor_color,
        duracion=SCOREBOARD_INTERVAL,
        font=FONT_8PX,
    )

    # Panel 3: cuarto + MM:SS con cuenta atrás y parpadeo del separador (5 s)
    # Layout: [0-5]=cuarto  [7-15]=MM  [15-19]=":"  [19-28]=SS
    rem_min, rem_sec = minutes, seconds
    for tick in range(5):
        for i in range(len(np)):
            np[i] = (0, 0, 0)
        _np_draw_text_region(str(quarter),              (200, 200, 200),  0,  6, font=FONT_8PX)
        _np_draw_text_region("{:02d}".format(rem_min),  (200, 200, 200),  7, 16, font=FONT_8PX)
        if tick % 2 == 0:
            _np_draw_text_region(":",                   (200, 200, 200), 16, 19, font=FONT_8PX)
        _np_draw_text_region("{:02d}".format(rem_sec),  (200, 200, 200), 19, 28, font=FONT_8PX)
        np.write()
        time.sleep(1)
        if rem_sec > 0:
            rem_sec -= 1
        elif rem_min > 0:
            rem_min -= 1
            rem_sec = 59


def demo_cronometro():
    """
    Simula un cronómetro de cuenta atrás (MM:SS) durante 5 segundos
    con valores aleatorios iniciales.
    """
    minutos = urandom.getrandbits(3) % 10
    segundos = urandom.getrandbits(6) % 60

    color_crono = [255, 120, 0]

    for _ in range(5):
        tiempo_str = "{:02d}:{:02d}".format(minutos, segundos)

        for i in range(len(np)):
            np[i] = (0, 0, 0)
        w_total = get_text_width(tiempo_str)
        start_x = (32 - w_total) // 2

        curr_x = start_x
        for char in tiempo_str:
            if char in FONT:
                char_data = FONT[char]
                cw = 0
                for r_idx, r_val in enumerate(char_data):
                    for c in range(8):
                        if r_val & (1 << (7 - c)):
                            px, py = curr_x + c, 7 - (len(char_data) - 1 - r_idx) - 1
                            if 0 <= px < 32 and 0 <= py < 8:
                                idx = led_index(px, py)
                                if COLOR_ORDER == "GRB":
                                    np[idx] = (int(color_crono[1] * my_shared.BRIGHTNESS), int(color_crono[0] * my_shared.BRIGHTNESS), int(color_crono[2] * my_shared.BRIGHTNESS))
                                else:
                                    np[idx] = (int(color_crono[0] * my_shared.BRIGHTNESS), int(color_crono[1] * my_shared.BRIGHTNESS), int(color_crono[2] * my_shared.BRIGHTNESS))
                            cw = max(cw, c + 1)
                curr_x += (cw if cw > 0 else 3) + 1

        np.write()
        time.sleep(1)
        if segundos > 0:
            segundos -= 1
        elif minutos > 0:
            minutos -= 1
            segundos = 59


def display_clock_frame(hours, minutes, day, separator_on):
    """Dibuja un único frame del reloj (no bloqueante).
    Llamar desde el bucle del servidor pasando los datos de tiempo ya calculados."""
    bri = my_shared.BRIGHTNESS
    # Fondo de calendario en las primeras 9 columnas
    for x in range(9):
        for y in range(8):
            idx = led_index(x, y)
            if y in (0, 1):
                np[idx] = (int(255 * bri), 0, 0)
            else:
                np[idx] = (int(255 * bri), int(255 * bri), int(255 * bri))

    # Día en negro sobre el calendario
    day_text = str(day)
    w_day = get_text_width(day_text)
    start_x_day = (9 - w_day) // 2
    fb.fill(0)
    draw_text_line(day_text, start_x_day, line_offset=-1)
    for x in range(9):
        for y in range(8):
            if fb.pixel(x, y) and y > 0:
                np[led_index(x, y)] = (0, 0, 0)

    # Hora:minutos con colon parpadeante
    left_text = str(hours)
    right_text = str(minutes)
    separator_width = 1
    total_width = get_text_width(left_text) + 1 + separator_width + 1 + get_text_width(right_text)
    start_x_time = 9 + max(0, (23 - total_width) // 2)
    fb.fill(0)
    temp_x = start_x_time
    temp_x = draw_text_line(left_text, temp_x, line_offset=-1)
    temp_x += 1
    if separator_on:
        draw_char_base(':', temp_x, line_offset=-1)
    temp_x += separator_width + 1
    draw_text_line(right_text, temp_x, line_offset=-1)

    for x in range(9, 32):
        for y in range(8):
            idx = led_index(x, y)
            if fb.pixel(x, y):
                np[idx] = (int(255 * bri), int(255 * bri), int(255 * bri))
            else:
                np[idx] = (0, 0, 0)

    np.write()


def display_clock():
    """Compatibilidad: muestra el reloj bloqueante 10s (no usar desde el servidor)."""
    import my_network
    year, weekday, hours, minutes, seconds, day, month = my_network.get_ntp_time_local()
    try:
        h = (int(hours) + my_shared.HOUR_OFFSET) % 24
        hours = '{:02d}'.format(h)
    except:
        pass
    start = time.time()
    while time.time() - start < 10:
        separator_on = int(time.time()) % 2 == 0
        display_clock_frame(hours, minutes, day, separator_on)
        time.sleep_ms(100)
        time.sleep_ms(100)  # Actualiza cada 100ms para suavidad