# Modo mensajes de la Awtrix: reloj + API HTTP/UDP de siempre (my_server) mientras no
# haya partido. Cada minuto mira la lista; 15 min antes de un partido reinicia en modo
# marcador. No usa check_for_updates (la OTA de la Awtrix pisaria boot.py) sino la del
# marcador (modo_fbm.actualizar, carpeta ota/32x8 de miginv/marcador_partidos).
# Con el servidor en marcha no queda RAM para TLS: lista y OTA se bajan al arrancar y,
# si la lista no se ha podido refrescar en 1 h (o cada 6 h para la OTA), se reinicia.
import time
import modo_fbm
import my_display
import my_network
import my_server

REVISAR_SEG = 60
DESCARGA_SEG = 15 * 60
REFRESCO_SEG = 3600         # sin lista nueva en 1 h: reinicio para bajarla con RAM libre
OTA_SEG = 6 * 3600          # la OTA solo se hace al arrancar: reinicio cada 6 h
_t = {"rev": 0, "desc": 0, "ok": time.time(), "ota": time.time()}
_frame_orig = my_display.display_clock_frame


def _revisar():
    ahora = time.time()
    if ahora - _t["desc"] >= DESCARGA_SEG:
        _t["desc"] = ahora
        if modo_fbm.descargar():
            _t["ok"] = ahora
    p = modo_fbm.partido_cercano()
    if p:
        print("[MODO] partido cerca:", p.get("hora"), p.get("local"), "vs", p.get("visit"))
        modo_fbm.cambiar("marcador")
    if ahora - _t["ok"] >= REFRESCO_SEG or ahora - _t["ota"] >= OTA_SEG:
        print("[MODO] reinicio para bajar lista/OTA con RAM libre")
        modo_fbm.cambiar("mensajes")


def _frame(*a, **k):
    # my_server dibuja el reloj varias veces por segundo: se aprovecha para revisar
    if time.time() - _t["rev"] >= REVISAR_SEG:
        _t["rev"] = time.time()
        try:
            _revisar()
        except Exception as e:
            print("[MODO] error revisando:", e)
    return _frame_orig(*a, **k)


my_display.display_clock_frame = _frame

if not my_network.sta.isconnected():   # boot.py ya ha conectado; nunca el hotspot "Pantalla"
    import wifi_portal                 # de la Awtrix (borra las redes): siempre "scoreboard"
    wifi_portal.asegurar(my_network.get_matrix_id())
my_network.get_ntp_time_local()
try:
    modo_fbm.actualizar()
except Exception as _e:
    print("[OTA] error:", _e)
if modo_fbm.descargar():
    print("[MODO] lista descargada")
_t["ota"] = _t["ok"] = _t["desc"] = time.time()   # tras el NTP: el reloj ha saltado
my_display.process_awtrix({
    "text": "{} {} {}".format(my_network.get_ssid(), my_network.get_ip(), my_network.get_hostname()),
    "color": [0, 80, 255], "icon": 32930, "repeat": 1, "textCase": 3, "scrollspeed": 50})
my_server.start_api_server_with_clock()
