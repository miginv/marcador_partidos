# Marcador ligero para ESP8266 (ver marcador8266.py).
import gc
gc.collect()
try:
    import marcador8266        # no vuelve
except Exception as e:
    import sys
    sys.print_exception(e)
