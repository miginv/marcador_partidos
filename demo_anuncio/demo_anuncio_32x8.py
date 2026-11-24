# Demo para fotos/anuncio en la 32x8 (firmware Awtrix): bucle de mensajes con iconos de LaMetric.
# Se activa creando demo.txt en la placa (boot.py lo mira antes que nada); borrarlo para volver.
# Los iconos van en /ICONS/<id>.gif (subidos por USB: en este modo no hay WiFi).
import my_display
import orientacion
from awtrix_font import FONT

orientacion.aplicar(my_display.LED_MAP_17)
FONT["€"] = [0x30, 0x40, 0xF0, 0x40, 0x30]      # simbolo del euro (4 px)

VERDE, AMAR, ROJO, BLANCO = (0, 255, 40), (255, 190, 0), (255, 0, 0), (255, 255, 255)
CIAN, ROSA, NARANJA, AZUL = (0, 220, 255), (255, 40, 180), (255, 110, 0), (40, 120, 255)

# (icono, texto, color, repeticiones). Texto de mas de 24 px (con icono) hace scroll.
MENSAJES = [
    (2149, "GOOOL!", VERDE, 2),
    (472, "CANASTA!", NARANJA, 1),
    (1213, "3€", AMAR, 1),
    (1311, "1,20€", AMAR, 1),
    (613, "2€", AMAR, 1),
    (1324, "PIZZA 4€", AMAR, 1),
    (None, "DESCANSO", CIAN, 1),
    (1246, "18ºC", BLANCO, 1),
    (72, "LLUVIA 12ºC", AZUL, 1),
    (82, "18:30", AZUL, 1),
    (2060, "CAMPEONES", AMAR, 1),
    (2167, "MVP", AMAR, 1),
    (635, "TU MARCA AQUI", ROSA, 1),
    (61, "GRACIAS AFICION", ROJO, 1),
]


def bucle():
    while True:
        for icono, texto, color, rep in MENSAJES:
            my_display.process_awtrix({"text": texto, "color": list(color), "icon": icono,
                                       "repeat": rep, "scrollspeed": 60})


bucle()
