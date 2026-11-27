# Reloj de la 16x16 sin mensajes: arriba el icono del calendario con el dia, abajo HH MM.
# Aparte de mensajes16 para que el modo pabellon no cargue el decodificador de GIF.
import time
import pantalla16
import sistema16

GIF_BRILLO = 0.6
BLANCO = (255, 255, 255)


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
