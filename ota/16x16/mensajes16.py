# Modo mensajes de la 16x16 (como la Awtrix, misma API): icono o GIF en la primera fila
# (8 px de alto; hasta 16x8 apaisado, 8x8 centrado, 16x16 reducido a 8x8) y el texto en la
# segunda fila. Si el texto cabe en 16 px va centrado y quieto; si no, como en la 24x8: se
# muestra quieto desde la izquierda hasta donde llegue y luego pasa en scroll.
# Sin mensajes: reloj (horas arriba, minutos abajo).
import time
import pantalla16
import sistema16
import my_shared
from gif16 import Gif

GIF_BRILLO = 0.6
NEGRO = 30            # colores mas oscuros que esto no se encienden (fondo del icono)
PAUSA_MS = 2000       # texto largo: quieto al principio
DURACION_MS = 4000    # texto corto: lo que dura en pantalla (por repeticion)
BLANCO = (255, 255, 255)


def abrir_icono(icono):
    if icono is None or icono == "":
        return None
    icono = str(icono)
    if icono.lower().endswith(".gif"):
        icono = icono[:-4]
    for intento in range(2):
        try:
            return Gif("/ICONS/%s.gif" % icono)
        except Exception as e:
            if intento or not sistema16.descargar_icono(icono):
                print("[MSG] icono", icono, e)
                return None
    return None


def pintar_icono(g, y0=0, alto=8):
    """GIF en la franja de alto px que empieza en y0, centrado; reducido si no cabe."""
    if g is None or not g.listo:
        return
    f = 1
    while g.h // f > alto or g.w // f > 16:
        f += 1
    w, h = g.w // f, g.h // f
    x0 = (16 - w) // 2
    y1 = y0 + (alto - h) // 2
    e = my_shared.BRIGHTNESS * GIF_BRILLO
    orden = pantalla16.COLOR_ORDER
    for y in range(h):
        for x in range(w):
            r, gg, b = g.color(x * f, y * f)
            if max(r, gg, b) < NEGRO:
                continue
            c = (max(1, int(r * e)) if r else 0, max(1, int(gg * e)) if gg else 0,
                 max(1, int(b * e)) if b else 0)
            pantalla16.pixel(x0 + x, y1 + y, (c[1], c[0], c[2]) if orden == "GRB" else c)


def mostrar(p, interrumpir=None):
    """Mensaje tipo Awtrix (/api/notify, /api/custom). interrumpir() -> True corta el
    mensaje (llega la posesion). Devuelve False si se ha cortado."""
    txt = str(p.get("text", ""))
    if p.get("textCase") == 1:
        txt = txt.lower()
    elif p.get("textCase") == 2:
        txt = txt.upper()
    color = p.get("color") or BLANCO
    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        color = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    repeat = max(1, min(int(p.get("repeat", 1)), 8))
    paso = max(20, int(p.get("scrollspeed", 60)))
    dur = int(float(p.get("duration", DURACION_MS / 1000)) * 1000)
    g = abrir_icono(p.get("icon"))
    base = pantalla16.FILA2 if g else 10        # sin icono, el texto centrado en vertical
    w = pantalla16.ancho(txt)
    try:
        for _ in range(repeat):
            if w <= 16:
                xs = None
                fin = time.ticks_add(time.ticks_ms(), dur)
            else:
                xs = [0] * (PAUSA_MS // paso) + list(range(-1, -w - 1, -1))
            i = 0
            while True:
                if xs is None:
                    if time.ticks_diff(fin, time.ticks_ms()) <= 0:
                        break
                    x = (16 - w) // 2
                else:
                    if i >= len(xs):
                        break
                    x = xs[i]
                    i += 1
                if interrumpir and interrumpir():
                    return False
                if g:
                    g.tick()
                pantalla16.limpiar()
                pintar_icono(g)
                pantalla16.texto(txt, x, base, color)
                pantalla16.mostrar()
                time.sleep_ms(paso if xs is not None else 40)
    finally:
        if g:
            g.cerrar()
    return True


def grande(icono, segundos, interrumpir=None):
    """Icono a toda la pantalla (8x8 al doble)."""
    g = abrir_icono(icono)
    if not g:
        return True
    fin = time.ticks_add(time.ticks_ms(), int(segundos * 1000))
    try:
        while time.ticks_diff(fin, time.ticks_ms()) > 0:
            if interrumpir and interrumpir():
                return False
            g.tick()
            pantalla16.limpiar()
            f = 2 if g.w <= 8 and g.h <= 8 else 1
            e = my_shared.BRIGHTNESS * GIF_BRILLO
            for y in range(min(16, g.h * f)):
                for x in range(min(16, g.w * f)):
                    r, gg, b = g.color(x // f, y // f)
                    if max(r, gg, b) >= NEGRO:
                        pantalla16.pixel(x, y, pantalla16.escala((r, gg, b), GIF_BRILLO))
            pantalla16.mostrar()
            time.sleep_ms(40)
    finally:
        g.cerrar()
    return True


_reloj = [None]
ROJO_CAL = (255, 0, 0)


def _cifras(txt, x, base, color):
    """Digitos en celdas fijas de 3 px con 1 px de separacion (el "1" centrado)."""
    for ch in txt:
        w = pantalla16.ancho_car(ch)
        pantalla16.texto(ch, x + (3 - w + 1) // 2 if w < 3 else x, base, color)
        x += 4


def _calendario(dia):
    """Icono 8x8 centrado arriba: hoja de calendario (cabecera roja con anillas, hoja blanca)
    con el dia en hueco (LED apagados), con el mismo brillo que los iconos GIF."""
    x0 = 4
    rojo = pantalla16.escala(ROJO_CAL, GIF_BRILLO)
    blanco = pantalla16.escala(BLANCO, GIF_BRILLO)
    for x in range(8):
        if x not in (1, 6):
            pantalla16.pixel(x0 + x, 0, rojo)
        pantalla16.pixel(x0 + x, 1, rojo)
        for y in range(2, 8):
            pantalla16.pixel(x0 + x, y, blanco)
    negro = (0, 0, 0)
    w = pantalla16.ancho(dia)
    pantalla16.texto(dia, x0 + (8 - w + 1) // 2, 6, None, xmin=x0, xmax=x0 + 8, c=negro)


def reloj(forzar=False):
    """Arriba el icono del calendario con el dia; abajo la hora HH MM."""
    if sistema16.hora_ok[0]:
        lt = time.localtime(sistema16.ahora_local())
        clave = (str(lt[2]), "%02d" % lt[3], "%02d" % lt[4])
    else:
        clave = ("", "--", "--")
    if clave == _reloj[0] and not forzar:
        return
    _reloj[0] = clave
    dia, hh, mm = clave
    pantalla16.limpiar()
    _calendario(dia)
    _cifras(hh, 0, pantalla16.FILA2, BLANCO)
    _cifras(mm, 9, pantalla16.FILA2, BLANCO)
    pantalla16.mostrar()


def olvidar():
    _reloj[0] = None
