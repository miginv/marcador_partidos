#!/bin/zsh
# Compila los modulos a .mpy (bytecode de MicroPython 1.23, lo que lleva la placa) y pone en
# version.json la lista para la OTA: boot.py va en fuente y el resto precompilado. Los .mpy
# ahorran la compilacion en la placa, que hace crecer la memoria de MicroPython y, en modo
# pabellon (con Bluetooth), deja a la WiFi sin memoria.
# Uso: ./publicar.sh 1.1.1   (luego commit y push)
set -e
cd "${0:A:h}"
[ -n "$1" ] || { echo "uso: $0 VERSION"; exit 1; }
python3 -m mpy_cross --version | grep -q "v1.23" || { echo "hace falta: pip3 install mpy-cross==1.23.0"; exit 1; }
MODS=(main16 pantalla16 fuente16 awtrix_font gif16 sistema16 reloj16 mensajes16 posesion16 ble16 pabellon16 marcador16 fbm_http font_narrow wifi_portal)

for m in $MODS; do python3 -m mpy_cross -o $m.mpy $m.py; done
python3 - "$1" "${MODS[@]}" <<'PY'
import json, sys
v, mods = sys.argv[1], sys.argv[2:]
json.dump({"version": v, "files": ["boot.py"] + ["%s.mpy" % m for m in mods]},
          open("version.json", "w"), indent=2)
open("version.json", "a").write("\n")
PY
cat version.json
