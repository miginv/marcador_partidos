# Ulanzi TC001: modo mensajes (reloj + API Awtrix para auto_power) y, si hay servidor
# propio configurado (ajustes_tc001.json "relay"), modo marcador leyendo de ese servidor
# por http (aqui no cabe el TLS de la FBM). modo.txt = "marcador" arranca el marcador;
# cualquier otra cosa (o un fallo al arrancarlo) arranca los mensajes.
import hw_tc001                 # zumbador a nivel bajo antes de nada
try:
    with open("modo.txt") as _f:
        _modo = _f.read().strip()
except Exception:
    _modo = ""
if _modo == "marcador":
    try:
        import marcador_fbm     # no vuelve: vuelve a mensajes reiniciando (modo_fbm.cambiar)
    except Exception as _e:
        import sys
        sys.print_exception(_e)
        with open("modo.txt", "w") as _f:
            _f.write("mensajes")
        import machine
        machine.reset()
import mensajes_tc001           # no vuelve: servidor de mensajes
