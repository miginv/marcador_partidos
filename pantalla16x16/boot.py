# Pantalla 16x16, demos en bucle:
#  1) posesion 24 -> 0 en grande (rojo; de 9.9 a 0.0 con decimas)
#  2) dos lineas de 7 px: arriba el tiempo del cuarto desde 12:00, abajo la posesion desde 24
import time
import pantalla16
import fuente16

COLOR = (255, 0, 0)            # rojo puro (posesion)
COLOR_CUARTO = (255, 200, 0)   # amarillo (tiempo del cuarto)
CUARTO = 12 * 60               # segundos por cuarto
T_CUARTO = time.ticks_ms()     # el cuarto corre desde el arranque, tambien durante la otra demo


def demo_posesion(desde=24):
    t0 = time.ticks_ms()
    total = desde * 10                       # en decimas
    ultimo = None
    while True:
        quedan = total - time.ticks_diff(time.ticks_ms(), t0) // 100
        if quedan < 0:
            quedan = 0
        if quedan >= 100:
            txt = str((quedan + 9) // 10)    # 24..10 (sube al entero: 23.4 -> 24)
        else:
            txt = "%d.%d" % (quedan // 10, quedan % 10)
        if txt != ultimo:
            pantalla16.pintar_columnas(fuente16.texto(txt), COLOR)
            ultimo = txt
        if quedan == 0:
            break
        time.sleep_ms(20)


def _texto_posesion(decimas):
    if decimas >= 100:
        return str((decimas + 9) // 10)      # redondeo hacia arriba, como los relojes de 24
    return "%d.%d" % (decimas // 10, decimas % 10)


def demo_partido(segundos=50, posesion=24):
    """Arriba el tiempo del cuarto (sigue la cuenta desde el arranque; al llegar a 0 vuelve
    a 12:00), abajo la posesion (24 bajando; al llegar a 0 vuelve a 24)."""
    t0 = time.ticks_ms()
    ultimo = None
    while True:
        pasadas = time.ticks_diff(time.ticks_ms(), t0) // 100          # decimas
        if pasadas > segundos * 10:
            break
        quedan_cuarto = CUARTO * 10 - time.ticks_diff(time.ticks_ms(), T_CUARTO) // 100 % (CUARTO * 10)
        arriba = (quedan_cuarto + 9) // 10 if quedan_cuarto >= 600 else quedan_cuarto / 10
        abajo = _texto_posesion(posesion * 10 - pasadas % (posesion * 10))
        clave = (arriba, abajo)
        if clave != ultimo:
            pantalla16.pintar_capas([(fuente16.reloj7(arriba), COLOR_CUARTO, 0),
                                     (fuente16.posesion7(abajo), COLOR, 9)])
            ultimo = clave
        time.sleep_ms(20)


while True:                              # demo grande, demo de partido y vuelta a empezar
    try:
        demo_posesion()
        time.sleep(3)
        demo_partido()
    except Exception as e:
        print("demo:", e)
        pantalla16.apagar()
        break
