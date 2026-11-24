# Modo marcador FBM: si existe marcador_fbm.py la pantalla hace de marcador en tiempo
# real (partidos de github.com/miginv/marcador_partidos). modo.txt elige el modo:
#  - marcador (o sin fichero): sigue el partido; sin partido cerca pasa a mensajes
#  - mensajes: reloj + API Awtrix de siempre; 15 min antes de un partido pasa a marcador
# Para volver al reloj Awtrix de siempre: borrar o renombrar marcador_fbm.py.
# Con demo.txt (y demo_anuncio.py) hace solo la demo de mensajes con iconos, sin WiFi.
# Sin ninguna WiFi guardada al alcance: red abierta "scoreboard" para dar de alta otra.
import os as _os
if "demo.txt" in _os.listdir() and "demo_anuncio.py" in _os.listdir():
    import demo_anuncio          # modo demo (fotos/anuncio): no vuelve; borrar demo.txt para salir
if "marcador_fbm.py" in _os.listdir():
    import modo_fbm
    import wifi_portal
    if modo_fbm.leer_modo() == "mensajes":
        import my_network
        wifi_portal.asegurar(my_network.get_matrix_id())
        import mensajes_fbm      # no vuelve: servidor de mensajes
    else:
        import network, ubinascii
        _mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()
        wifi_portal.asegurar("marcador-" + _mac[-4:], "marcador_disp")
        import marcador_fbm      # no vuelve: bucle del marcador
del _os

import my_display
import my_network
import my_server
import time

# TEST de diagnóstico: muestra filas de colores 20 segundos al arrancar
#my_display.test_rows()

# 1. Conectar WiFi y configurar Hostname
my_network.connect_wifi()

# 2. Comprobar actualizaciones
my_network.check_for_updates()

# 3. Sincronizar hora (opcional pero recomendado)
my_network.get_ntp_time_local()

# 4. Mostrar mensaje de conexión
ssid = my_network.get_ssid()
ip = my_network.get_ip()
hostname = my_network.get_hostname()
msg = {
    "text": "{} {} {}".format(ssid, ip, hostname),
    "color": [0, 80, 255],
    "icon": 32930,
    "repeat": 1,
    "textCase": 3,
    "scrollspeed": 50
}
my_display.process_awtrix(msg)

# 5. Lanzar el servidor de escucha con reloj
# Nota: Esto bloqueará el hilo principal para escuchar mensajes y mostrar reloj
my_server.start_api_server_with_clock()
