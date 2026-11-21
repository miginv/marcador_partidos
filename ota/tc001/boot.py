# Ulanzi TC001: modo solo mensajes (reloj + API Awtrix para auto_power).
# El marcador FBM no cabe en la memoria de este ESP32 (sin PSRAM) junto con TLS;
# los ficheros del marcador siguen en ota/tc001 pero no se instalan.
import hw_tc001                 # zumbador a nivel bajo antes de nada
import mensajes_tc001           # no vuelve: servidor de mensajes
