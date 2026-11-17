# Marcador 24x8: elige modo al arrancar. modo.txt (modo_fbm) dice si toca el marcador
# (partido cerca) o los mensajes (reloj + API tipo Awtrix). La WiFi la pone wifi_portal:
# redes guardadas y, si no hay ninguna, la red abierta "scoreboard" para darlas de alta.
import network
import ubinascii
import modo_fbm
import wifi_portal

_mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()
wifi_portal.asegurar("marcador-" + _mac[-4:], "my_display")
del _mac
if modo_fbm.leer_modo() == "mensajes":
    import mensajes_fbm      # no vuelve: reloj + mensajes
else:
    import marcador24        # no vuelve: bucle del marcador
