# Demo de mensajes con iconos de LaMetric en la 16x16 (para fotos/anuncio).
# Iconos en /ICONS/<id>.gif (8x8). Tres formatos:
#   ("grande", icono, segundos)            icono a 16x16 (x2)
#   ("icono", icono, texto, color)          icono arriba, texto abajo (scroll si no cabe)
#   ("texto", texto, color)                 texto a toda pantalla, centrado en vertical
import time
import pantalla16
import my_shared
from gif8 import GifPlayer
from awtrix_font import FONT

FONT["€"] = [0x30, 0x40, 0xF0, 0x40, 0x30]       # euro (4 px)
W = 16
np = pantalla16.np
MAPA = pantalla16._MAPA
GIF_BRILLO = getattr(my_shared, "GIF_BRIGHTNESS", 0.6)
NEGRO = getattr(my_shared, "BLACK_THRESHOLD", 30)
PASO_GIF = 150          # ms por fotograma del icono
PASO_SCROLL = 70        # ms por columna de scroll

VERDE, AMAR, ROJO, BLANCO = (0, 255, 40), (255, 190, 0), (255, 0, 0), (255, 255, 255)
CIAN, ROSA, NARANJA, AZUL = (0, 220, 255), (255, 40, 180), (255, 110, 0), (40, 120, 255)

MENSAJES = [
    ("grande", 2149, 4),
    ("icono", 2149, "GOOOL!", VERDE),
    ("icono", 472, "CANASTA", NARANJA),
    ("icono", 1213, "3€", AMAR),
    ("icono", 1311, "1,20€", AMAR),
    ("icono", 613, "2€", AMAR),
    ("icono", 1324, "4€", AMAR),
    ("texto", "DESCANSO", CIAN),
    ("grande", 1246, 3),
    ("icono", 1246, "18ºC", BLANCO),
    ("icono", 72, "12ºC", AZUL),
    ("icono", 82, "18:30", AZUL),
    ("grande", 2060, 3),
    ("icono", 2167, "MVP", AMAR),
    ("icono", 635, "TU MARCA AQUI", ROSA),
    ("grande", 61, 3),
]


def _ancho_car(c):
    cw = 0
    for r in FONT.get(c, ()):
        for col in range(8):
            if r & (1 << (7 - col)):
                cw = max(cw, col + 1)
    return cw or 3


def _ancho(t):
    return sum(_ancho_car(c) + 1 for c in t) - 1


def _texto(t, x, y0, color):
    """Texto de 5 filas con la fuente de la Awtrix; y0 = fila de arriba."""
    c = pantalla16._escala(color)
    for ch in t:
        filas = FONT.get(ch)
        if filas:
            for r, v in enumerate(filas):
                for col in range(8):
                    if v & (1 << (7 - col)):
                        px, py = x + col, y0 + r
                        if 0 <= px < W and 0 <= py < W:
                            np[MAPA[py * W + px]] = c
        x += _ancho_car(ch) + 1


def _color_gif(ind, pal, i, transp):
    k = ind[i]
    if k == transp or k * 3 + 2 >= len(pal):
        return None
    r, g, b = pal[k * 3], pal[k * 3 + 1], pal[k * 3 + 2]
    if max(r, g, b) < NEGRO:
        return None
    e = my_shared.BRIGHTNESS * GIF_BRILLO
    c = tuple(max(1, int(v * e)) if v else 0 for v in (r, g, b))
    return (c[1], c[0], c[2]) if my_shared.COLOR_ORDER == "GRB" else c


def _icono(fr, x0, y0, escala):
    ind, pal, transp = fr
    if not ind or len(ind) < 64:
        return
    for y in range(8):
        for x in range(8):
            c = _color_gif(ind, pal, y * 8 + x, transp)
            if c:
                for dy in range(escala):
                    for dx in range(escala):
                        np[MAPA[(y0 + y * escala + dy) * W + x0 + x * escala + dx]] = c


class _Anim:
    def __init__(self, icono):
        self.p = None
        self.fr = None
        self.t = 0
        try:
            self.p = GifPlayer("/ICONS/%d.gif" % icono)
        except Exception as e:
            print("icono", icono, e)

    def frame(self):
        if self.p and (self.fr is None or time.ticks_diff(time.ticks_ms(), self.t) >= PASO_GIF):
            ind, pal = self.p.get_next_frame()
            if ind and len(ind) >= 64 and pal:
                self.fr = (ind, pal, self.p.transparent_idx)
            self.t = time.ticks_ms()
        return self.fr

    def cerrar(self):
        if self.p:
            self.p.f.close()


def grande(icono, segundos):
    a = _Anim(icono)
    fin = time.ticks_add(time.ticks_ms(), segundos * 1000)
    while time.ticks_diff(fin, time.ticks_ms()) > 0:
        np.fill((0, 0, 0))
        fr = a.frame()
        if fr:
            _icono(fr, 0, 0, 2)
        np.write()
        time.sleep_ms(30)
    a.cerrar()


def _pasar(texto, color, y0, fondo=None, quieto_ms=3500):
    """Texto en la fila y0: centrado y quieto si cabe, si no scroll de derecha a izquierda.
    fondo() pinta lo demas en cada cuadro (el icono animado)."""
    w = _ancho(texto)
    if w <= W:
        xs, paso = [(W - w) // 2] * (quieto_ms // 50), 50
    else:
        xs, paso = list(range(W, -w - 1, -1)), PASO_SCROLL
    for x in xs:
        np.fill((0, 0, 0))
        if fondo:
            fondo()
        _texto(texto, x, y0, color)
        np.write()
        time.sleep_ms(paso)


def icono_texto(icono, texto, color):
    a = _Anim(icono)

    def fondo():
        fr = a.frame()
        if fr:
            _icono(fr, 4, 1, 1)
    _pasar(texto, color, 10, fondo)
    a.cerrar()


def bucle(mensajes=MENSAJES, veces=None):
    n = 0
    while veces is None or n < veces:
        for m in mensajes:
            if m[0] == "grande":
                grande(m[1], m[2])
            elif m[0] == "icono":
                icono_texto(m[1], m[2], m[3])
            else:
                _pasar(m[1], m[2], 5)
        n += 1
