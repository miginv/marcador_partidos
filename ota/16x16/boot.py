# Pantalla 16x16 (reloj de posesion + marcador + mensajes).
# Modo normal: WiFi (wifi_portal: redes de config.json y, si no conecta, la red abierta
#   "scoreboard" con portal) -> hora y OTA (HTTPS) -> main16.
# Modo pabellon (fichero pabellon.on): no depende de la WiFi. Bluetooth lo primero y
#   pabellon16, que muestra el 24 al momento y conecta la WiFi en segundo plano, sin portal.
#   Sin OTA: MicroPython empieza con 64 KB y, si se le llenan, dobla su tamano quitandole al
#   sistema la memoria que la WiFi necesita con el Bluetooth activo, y el HTTPS es lo que mas
#   pide. Para actualizar: /api/settings {"PABELLON": 0} (vuelve al modo normal y reinicia).
import gc
import network
import ubinascii
import sistema16

_mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()
if sistema16.es_pabellon():
    try:
        import ble16
        ble16.iniciar("pos16-" + _mac[-4:])
    except Exception as _e:
        print("[BLE]", _e)
    del _mac
    gc.collect()
    import pabellon16        # no vuelve
else:
    import wifi_portal

    def _aviso_ota(v):
        import pantalla16
        pantalla16.draw_centered_text("OTA", 0, (0, 120, 255))

    wifi_portal.asegurar("marcador-" + _mac[-4:], "pantalla16")
    del _mac
    if network.WLAN(network.STA_IF).isconnected():
        sistema16.sync_hora()
        try:
            sistema16.actualizar(_aviso_ota)
        except Exception as _e:
            print("[OTA]", _e)
    gc.collect()
    import main16            # no vuelve
