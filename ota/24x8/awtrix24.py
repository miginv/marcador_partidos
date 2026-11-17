# Mensajes tipo Awtrix en el marcador 24x8: mismo codigo que my_display de la Awtrix
# (icono GIF de 8 px a la izquierda + texto, iconos de LaMetric en /ICONS), cambiando solo
# el tamano: 24 px de ancho, 3 modulos 8x8 sin zigzag, y el texto pasa en scroll si ocupa
# mas de 12 px. Los LED los manda my_display (SPI) del marcador.
import time
import os
import framebuf
from awtrix_font import FONT
import my_shared
import my_display

WIDTH = 24
MAX_FIJO = 12
TEXT_LINE = 1
GIF_BRIGHTNESS = 0.6
BLACK_THRESHOLD = 30
COLOR_ORDER = "RGB"
np = my_display.np
fb = framebuf.FrameBuffer(bytearray(32), 32, 8, framebuf.MONO_VLSB)


def _show():
    my_display._show()


def led_index(x, y):
    """3 modulos 8x8 en fila, cada uno 64 LED fila a fila (como my_display del marcador)."""
    if x < 0 or x >= WIDTH or y < 0 or y >= 8:
        return 0
    return (x // 8) * 64 + y * 8 + (x % 8)


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



def draw_char_base(char, x, line_offset=0, min_x=0):
    if char in FONT:
        char_data = FONT[char]
        for r_idx, r_val in enumerate(char_data):
            for c in range(8):
                if r_val & (1 << (7 - c)):
                    px, py = x + c, 7 - (len(char_data) - 1 - r_idx) + line_offset
                    if min_x <= px < WIDTH and 0 <= py < 8:
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
    if max(r, g, b) < BLACK_THRESHOLD:
        return None
    return scale_rgb(r, g, b, my_shared.BRIGHTNESS * GIF_BRIGHTNESS)


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
            if download_icon(icon_id):
                try:
                    player = GifPlayer("/ICONS/{}.gif".format(icon_id))
                except Exception as e:
                    print("Error cargando icono {} tras descarga: {}".format(icon_id, e))
                    player = None
            else:
                print("No se pudo descargar icono {}".format(icon_id))
                player = None

    t_w = get_text_width(text)
    is_static = t_w <= MAX_FIJO   # 24x8: texto de mas de 12 px en scroll
    line_offset = -TEXT_LINE  # Offset vertical en píxeles
    last_frame = (None, None)

    for _ in range(repeat):
        frames = range(WIDTH, 7 - t_w, -1) if not is_static else range(40)
        
        for x_pos in frames:
            fb.fill(0)  # Limpiar framebuffer al inicio de cada frame
            if is_static:
                curr_x = 8 + (WIDTH - 8 - t_w) // 2 if player else (WIDTH - t_w) // 2
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

            for x in range(WIDTH):
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

            _show()
            time.sleep_ms(speed if not is_static else 100)

    if player:
        player.f.close()


def download_icon(icon_id):
    """Descarga un icono de LaMetric si no existe en /ICONS/.
    Devuelve True si el icono está disponible (ya existía o se descargó), False si falla.
    Nota: urequests de MicroPython no soporta timeout ni ssl kwarg personalizado;
    el SSL por defecto (CERT_NONE) es suficiente para HTTPS en el ESP32-C3.
    """
    import os, gc
    import requests
    try:
        os.mkdir("/ICONS")
    except OSError:
        pass
    icon_path = "/ICONS/{}.gif".format(icon_id)
    try:
        if os.stat(icon_path)[6] > 0:
            return True  # Ya existe y no está vacío
    except:
        pass

    urls = [
        "https://developer.lametric.com/content/apps/icon_thumbs/{}.gif".format(icon_id),
        "https://developer.lametric.com/content/apps/icon_thumbs/{}_icon.gif".format(icon_id),
    ]

    for url in urls:
        response = None
        try:
            gc.collect()
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.content
                response.close()
                response = None
                if len(data) > 10 and data[:3] == b'GIF':
                    with open(icon_path, 'wb') as f:
                        f.write(data)
                    print("Icono {} descargado ({} bytes)".format(icon_id, len(data)))
                    return True
                else:
                    print("Icono {}: contenido invalido, {} bytes, header={}".format(
                        icon_id, len(data), data[:6]))
            else:
                print("Icono {}: HTTP {} en {}".format(icon_id, response.status_code, url))
                response.close()
                response = None
        except Exception as e:
            print("Error descargando icono {} de {}: {}".format(icon_id, url, e))
        finally:
            if response:
                try:
                    response.close()
                except:
                    pass

    # Registrar como icono no encontrado para no reintentar en cada muestra
    try:
        with open('/missing_icons.txt', 'a') as mf:
            mf.write("{}\n".format(icon_id))
    except Exception:
        pass
    return False


def display_clock_frame(hours, minutes, separator_on):
    """Reloj de la Awtrix (blanco, dos puntos parpadeando). En 24 px no cabe el
    calendario de 9 columnas: la hora va centrada."""
    bri = my_shared.BRIGHTNESS
    left_text = str(hours)
    right_text = str(minutes)
    total_width = get_text_width(left_text) + 1 + 1 + 1 + get_text_width(right_text)
    fb.fill(0)
    temp_x = max(0, (WIDTH - total_width) // 2)
    temp_x = draw_text_line(left_text, temp_x, line_offset=-1)
    temp_x += 1
    if separator_on:
        draw_char_base(':', temp_x, line_offset=-1)
    temp_x += 2
    draw_text_line(right_text, temp_x, line_offset=-1)
    w = (int(255 * bri), int(255 * bri), int(255 * bri))
    for x in range(WIDTH):
        for y in range(8):
            np[led_index(x, y)] = w if fb.pixel(x, y) else (0, 0, 0)
    _show()


def clear():
    my_display._np_clear()
    _show()
