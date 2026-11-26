# Pantalla 16x16 (reloj de posesion + marcador + mensajes). La WiFi la pone wifi_portal:
# redes guardadas en config.json y, si no hay ninguna, la red abierta "scoreboard".
import network
import ubinascii
import wifi_portal

_mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()
wifi_portal.asegurar("marcador-" + _mac[-4:], "pantalla16")
del _mac
import main16            # no vuelve
