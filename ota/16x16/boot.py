# Pantalla 16x16 (reloj de posesion + marcador + mensajes). La WiFi la pone wifi_portal:
# redes guardadas en config.json y, si no hay ninguna, la red abierta "scoreboard".
# Modo normal: WiFi -> hora y OTA (HTTPS) -> main16.
# Modo pabellon: WiFi -> hora -> Bluetooth -> pabellon16, SIN OTA: MicroPython empieza con 64 KB
# y, si se le llenan, dobla su tamano quitandole al sistema lo que la WiFi necesita con el
# Bluetooth activo; el HTTPS es justo lo que mas memoria pide. Para actualizar, pasar un
# momento al modo normal (/api/settings {"PABELLON": 0}).
import gc
import network
import ubinascii
import wifi_portal
import sistema16


def _aviso_ota(v):
    import pantalla16
    pantalla16.draw_centered_text("OTA", 0, (0, 120, 255))


_mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()
wifi_portal.asegurar("marcador-" + _mac[-4:], "pantalla16")
_pab = sistema16.es_pabellon()
if network.WLAN(network.STA_IF).isconnected():
    sistema16.sync_hora()
    if not _pab:
        try:
            sistema16.actualizar(_aviso_ota)
        except Exception as _e:
            print("[OTA]", _e)
gc.collect()
if _pab:
    try:
        import ble16
        ble16.iniciar("pos16-" + _mac[-4:])
    except Exception as _e:
        print("[BLE]", _e)
    del _mac
    import pabellon16        # no vuelve
else:
    del _mac
    import main16            # no vuelve
