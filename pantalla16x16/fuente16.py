# Fuente de numeros de 16 px de alto (estilo 7 segmentos, trazo de 2 px) para la 16x16.
# Cada caracter es una lista de columnas: entero de 16 bits, bit 0 = fila de arriba.
#   ancho 7 + hueco 2: "24" ocupa 7+2+7 = 16
#   ancho 6 + hueco 1 + punto 2x2: "9.8" ocupa 6+1+2+1+6 = 16
ALTO = 16
TRAZO = 2
SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
       "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg"}


def _digito(ch, w, h=ALTO, t=TRAZO, tv=None):
    """t = grosor de los trazos horizontales, tv = de los verticales (por defecto t)."""
    tv = t if tv is None else tv
    mid = (h - t) // 2
    segs = {"a": (0, 0, w, t), "g": (0, mid, w, mid + t), "d": (0, h - t, w, h),
            "f": (0, 0, tv, mid + t), "b": (w - tv, 0, w, mid + t),
            "e": (0, mid, tv, h), "c": (w - tv, mid, w, h)}
    cols = [0] * w
    for s in SEG[ch]:
        x0, y0, x1, y1 = segs[s]
        m = ((1 << (y1 - y0)) - 1) << y0
        for x in range(x0, x1):
            cols[x] |= m
    return cols


_ANCHO = {7: {c: _digito(c, 7) for c in SEG}, 6: {c: _digito(c, 6) for c in SEG}}
PUNTO = [0b11 << (ALTO - 2)] * 2          # 2x2 abajo


def texto(t):
    """Columnas para t: enteros con digitos de 7 px; con decimales, de 6 px y punto 2x2."""
    if "." in t:
        w, hueco = 6, 1
    else:
        w, hueco = 7, 2
    cols = []
    for i, ch in enumerate(t):
        if i:
            cols += [0] * hueco
        cols += PUNTO if ch == "." else _ANCHO[w][ch]
    return cols


# ---------- fuente pequena de 7 px de alto (dos lineas en la 16x16) ----------
# reloj del cuarto: digitos de 3 px (el "1" de 2 px) -> "12:00" ocupa 2+1+3+1+1+1+3+1+3 = 16
# posesion: digitos de 5 px -> "24" = 5+2+5, "9.8" = 5+1+1+1+5
ALTO7 = 7
_P3 = {c: _digito(c, 3, ALTO7, 1) for c in SEG}
_P3["1"] = [0, (1 << ALTO7) - 1]                    # "1" estrecho: 2 px (hueco + trazo)
_P5 = {c: _digito(c, 5, ALTO7, 1) for c in SEG}
_P5["1"] = [0, 0, 0, 0, (1 << ALTO7) - 1]           # alineado a la derecha como en 7 segmentos
DOS_PUNTOS = [(1 << 1) | (1 << 5)]
PUNTO7 = [1 << (ALTO7 - 1)]


def _une(trozos, hueco):
    cols = []
    for i, t in enumerate(trozos):
        if i:
            cols += [0] * hueco
        cols += t
    return cols


def reloj7(segundos):
    """Tiempo del cuarto: M:SS / MM:SS; en el ultimo minuto SS.d (segundos en float)."""
    if segundos >= 60:
        s = int(segundos)
        txt = "%d:%02d" % (s // 60, s % 60)
    else:
        txt = "%d.%d" % (int(segundos), int(segundos * 10) % 10)
    trozos = []
    for ch in txt:
        trozos.append(DOS_PUNTOS if ch == ":" else PUNTO7 if ch == "." else _P3[ch])
    return _une(trozos, 1)


def posesion7(txt):
    """Posesion: "24".."10" con hueco de 2; "9.8" con punto de 1 px y hueco de 1."""
    if "." in txt:
        return _une([PUNTO7 if ch == "." else _P5[ch] for ch in txt], 1)
    return _une([_P5[ch] for ch in txt], 2)
