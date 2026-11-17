import sys
import time
import gc
import json

# Marcador FBM en tiempo real para la pantalla Awtrix 32x8 (tira en zigzag).
# Misma logica que el boot.py del marcador 24x8; boot.py lo lanza si existe este fichero.
import my_shared
# solo en memoria: no se toca my_shared.py (lo usa la Awtrix)
my_shared.BRIGHTNESS = 0.333     # igual que el marcador 24x8 (se dibuja al 50 %)
my_shared.DEBUG = False
import marcador_disp as my_display
import font_narrow as _f8
import gesdeportiva as fbm
import modo_fbm


def _dbg(*a):
    if my_shared.DEBUG:
        print(*a)

COLOR_LOCAL = [0, 0, 255]
COLOR_VISIT = [255, 0, 0]
POLL_LIVE = 20        # segundos entre sondeos con partido en juego
POLL_ESPERA = 60      # segundos entre sondeos mientras el partido no ha empezado
ESTADO_FILE = "estado.json"
CONFIG_FILE = "config.json"

# alias por subcadena: cualquier equipo que contenga la clave (Coslada C.B. Serracines, Serracines 2019...)
ALIASES = {"SERRACINES": "SER", "LARRY": "LAR"}


# ---------- configuracion y estado ----------

PARTIDOS_FILE = "partidos.json"     # copia local de la ultima lista descargada
PARTIDOS_URL = "https://raw.githubusercontent.com/miginv/marcador_partidos/main/partidos.json"
REFRESCO_SEG = 15 * 60              # cada cuanto se vuelve a descargar la lista
EPOCH_2000 = 946684800              # time.time() de MicroPython cuenta desde 2000


def _ordenar(lista):
    return sorted(lista, key=lambda p: p.get("ts") or 0)


def descargar_partidos(url):
    """Baja la lista de GitHub y la guarda en local. Devuelve la lista o None si falla."""
    try:
        import requests
        r = requests.get(url, headers={"Cache-Control": "no-cache"})
        try:
            if r.status_code != 200:
                print("[LISTA] HTTP", r.status_code)
                return None
            txt = r.text
        finally:
            r.close()
        lista = json.loads(txt).get("partidos", [])
        with open(PARTIDOS_FILE, "w") as f:
            f.write(txt)
        print("[LISTA] descargada:", len(lista), "partidos")
        return _ordenar(lista)
    except Exception as e:
        print("[LISTA] fallo descarga:", e)
        return None
    finally:
        gc.collect()


def cargar_partidos():
    """Copia local de la lista descargada; si no hay, los partidos de config.json."""
    for fich in (PARTIDOS_FILE, CONFIG_FILE):
        try:
            with open(fich, "r") as f:
                lista = json.load(f).get("partidos", [])
            if lista:
                return _ordenar(lista)
        except Exception:
            pass
    return []


def clave(p):
    return p.get("notif") or (p.get("fecha", "") + p.get("hora", ""))


def leer_hechos():
    """Partidos ya terminados o descartados (por notif): la lista puede cambiar desde
    GitHub, asi que no vale un indice."""
    try:
        with open(ESTADO_FILE, "r") as f:
            return json.load(f).get("hechos", [])
    except Exception:
        return []


def marcar_hecho(p):
    k = clave(p)
    if k not in HECHOS:
        HECHOS.append(k)
        del HECHOS[:-40]
    try:
        with open(ESTADO_FILE, "w") as f:
            json.dump({"hechos": HECHOS}, f)
    except Exception as e:
        print("[ESTADO] no se pudo guardar:", e)


# ---------- nombres ----------

def abreviar(nombre):
    """Alias guardado; 1 palabra -> 3 letras; 2 -> 2 + 1; 3+ -> inicial de 3 primeras."""
    nombre = (nombre or "").strip().upper()
    # solo A-Z, 0-9, & y espacio: cualquier otro caracter (\, acentos sin mapear...) se sustituye
    nombre = "".join(c if (c in " &" or "A" <= c <= "Z" or "0" <= c <= "9") else " " for c in nombre)
    nombre = " ".join(nombre.split())
    if not nombre:
        return "???"
    for k, v in ALIASES.items():
        if k in nombre:
            return v
    p = nombre.split()
    if len(p) == 1:
        return p[0][:3]
    if len(p) == 2:
        return p[0][:2] + p[1][:1]
    return "".join(w[0] for w in p[:3])


# ---------- pantalla ----------

def _dibuja_grande(text, color, x_min, x_max):
    """Digitos 5x8 px, trazo 2 px (font_narrow). Paso de 6 px por caracter."""
    bri = min(1.0, my_shared.BRIGHTNESS * 1.5)
    r0, g0, b0 = color
    scaled = (int(r0 * bri), int(g0 * bri), int(b0 * bri))
    # centrado por tinta real: el "1" solo usa las columnas 3-4 del glifo
    lo_t, hi_t = None, None
    for i, ch in enumerate(text):
        glyph = _f8.FONT_NARROW.get(ch)
        if not glyph:
            continue
        cols = [c for c in range(5) if any(r & (0x80 >> c) for r in glyph)]
        if cols:
            a, b = 6 * i + cols[0], 6 * i + cols[-1]
            lo_t = a if lo_t is None else min(lo_t, a)
            hi_t = b if hi_t is None else max(hi_t, b)
    if lo_t is None:
        return
    ink_w = hi_t - lo_t + 1
    start = x_min + max(0, (x_max - x_min - ink_w) // 2) - lo_t
    for i, ch in enumerate(text):
        glyph = _f8.FONT_NARROW.get(ch)
        if glyph:
            pos_x = start + 6 * i
            for row_idx, row_val in enumerate(glyph):
                for col in range(5):
                    px = pos_x + col
                    if row_val & (0x80 >> col) and x_min <= px < x_max:
                        idx = my_display._led_idx(px, row_idx)
                        if idx >= 0:
                            my_display.np[idx] = scaled


W = my_display.WIDTH          # 32
M = W // 2                    # 16


def mostrar_marcador(rl, rv):
    my_display._np_clear()
    _dibuja_grande(str(rl), COLOR_LOCAL, 0, M)
    _dibuja_grande(str(rv), COLOR_VISIT, M, W)
    my_display._show()
    my_display.hold(1)


def _segundos(t):
    try:
        mm, ss = t.split(":")
        return int(mm) * 60 + int(ss)
    except Exception:
        return None


# reloj en 32 px: cuarto | mm | : | ss
RQ, RMM, RDP, RSS = (0, 8), (10, 18), (19, 21), (22, 30)


def _dibujar_reloj(num_q, r, el):
    """Cuarto en rojo puro y reloj mm:ss en verde puro; un segundo por frame."""
    my_display._np_clear()
    my_display._draw_region(num_q, (255, 0, 0), *RQ)
    my_display._draw_region("{:02d}".format(r // 60), (0, 255, 0), *RMM)
    if el % 2 == 0:
        my_display._draw_region(":", (0, 255, 0), *RDP)
    my_display._draw_region("{:02d}".format(r % 60), (0, 255, 0), *RSS)
    my_display._show()
    my_display.hold(1)


NOMBRES_SEG = 3       # segundos que se muestran los nombres
_nombres_pend = [True]   # nombres solo al empezar a seguir un partido y al acabar cada cuarto
_desc_prev = [False]

_ancla = {"q": None, "api": None, "rem": 0, "t": 0.0}


def _seg_desde(hora):
    """Segundos desde 'hh:mm:ss' (hora local de la accion) hasta ahora; None sin hora NTP."""
    if not _hora_ok or not hora:
        return None
    try:
        h, m, s = [int(x) for x in hora.split(":")[:3]]
    except Exception:
        return None
    ahora = int(_ahora_local()) % 86400
    return (ahora - (h * 3600 + m * 60 + s)) % 86400


def _rem_estimado(cuarto, tiempo, parado=False, hora_acc=None):
    """Segundos restantes. La API da el tiempo de la ULTIMA ACCION, no un reloj en vivo:
    - si esa accion para el reloj (falta, tiempo muerto, cambio...) se queda congelado;
    - si no, baja desde la hora real de la accion (hora_dia) o, sin ella, desde que se vio."""
    s = _segundos(tiempo)
    if s is None:
        return None
    if parado:
        _ancla["api"] = None          # al reanudarse se vuelve a anclar
        return s
    now = time.time()
    a = _ancla
    if a["q"] != cuarto or a["api"] != tiempo:
        a["q"] = cuarto
        a["api"] = tiempo
        a["rem"] = s
        a["t"] = now
        dt = _seg_desde(hora_acc)
        if dt is not None and dt < 300:   # descarta relojes de mesa descuadrados
            a["rem"] = s - dt
    return max(0, a["rem"] - int(now - a["t"]))


NUESTROS = ("SERRACINES", "COSLADA")   # sus jugadas en azul; las del rival en rojo
_jug_vista = [None]     # (id de accion, partido) de la ultima jugada mostrada


def _es_nuestro(nombre):
    nombre = (nombre or "").upper()
    return any(k in nombre for k in NUESTROS)


def fijar_colores(p):
    """Serracines siempre en azul: local a la izquierda, visitante a la derecha."""
    if _es_nuestro(p.get("visit")) and not _es_nuestro(p.get("local")):
        COLOR_LOCAL[:] = [255, 0, 0]
        COLOR_VISIT[:] = [0, 0, 255]
    else:
        COLOR_LOCAL[:] = [0, 0, 255]
        COLOR_VISIT[:] = [255, 0, 0]


def color_jugada(p, jugada):
    eq = p.get("local", "") if jugada["local"] else p.get("visit", "")
    eq = eq.upper()
    return (0, 0, 255) if any(k in eq for k in NUESTROS) else (255, 0, 0)


def mostrar_en_vivo(rl, rv, cuarto, tiempo, duracion, nom_l, nom_v, jugada=None,
                    descanso=False, parado=False, hora_acc=None):
    """Por sondeo: reloj 10 s, marcador 5 s y la jugada nueva en scroll 5 s (si no hay,
    marcador hasta el final). Los nombres solo al empezar el partido y al acabar un cuarto."""
    if descanso:
        _ancla["api"] = None
        rem = _segundos(tiempo)
    else:
        rem = _rem_estimado(cuarto, tiempo, parado, hora_acc)
    congelado = descanso or parado
    t_rem = time.time()
    num_q = cuarto.lstrip("Q") if cuarto else ""
    if _nombres_pend[0]:
        _nombres_pend[0] = False
        my_display.show_names(nom_l, nom_v, COLOR_LOCAL, COLOR_VISIT, NOMBRES_SEG)
    t0 = time.time()
    while True:
        el = int(time.time() - t0)
        if el >= duracion:
            break
        if rem is not None and el < 10:
            r = rem if congelado else max(0, rem - int(time.time() - t_rem))
            _dibujar_reloj(num_q, r, el)
        elif jugada and el >= 15:
            my_display.scroll_texto(jugada[0], jugada[1], 5)
            jugada = None                     # cada jugada se muestra una sola vez
            mostrar_marcador(rl, rv)          # queda el marcador mientras se consulta
        else:
            mostrar_marcador(rl, rv)


def mostrar_espera(hora, nombre_l, nombre_v, duracion):
    """Modo espera: hora de comienzo 5 s y nombres 5 s."""
    t0 = time.time()
    while time.time() - t0 < duracion:
        my_display.draw_centered_text(hora, 3, (0, 255, 0))
        my_display.hold(5)
        my_display.show_names(nombre_l, nombre_v, COLOR_LOCAL, COLOR_VISIT, 5)


# ---------- busqueda ----------

def buscar_partido(p):
    """Config de buscar_partidos.py (notif + skip): una llamada a la pagina exacta.
    El IdPartido depende de la sesion, por eso no puede venir fijado en el config."""
    if p.get("notif"):
        sk = p.get("skip", 0)
        for s in (sk, sk - 50, sk + 50):   # por si la lista se ha desplazado una pagina
            if s < 0:
                continue
            try:
                termino = p["buscar"] if isinstance(p["buscar"], str) else p["buscar"][0]
                hid, _l, _v = fbm.buscar_id_partido(termino, p["fecha"], s, p["notif"])
            except Exception as e:
                print("[BUSCAR] error", e)
                hid = None
            if hid:
                _dbg("[BUSCAR] notif", p["notif"], "skip", s)
                return hid, abreviar(p.get("local", "")), abreviar(p.get("visit", "")), p["hora"][:5]
            gc.collect()
        return None, None, None, None
    for t in p["buscar"]:
        try:
            hid, lf, vf = fbm.buscar_id_partido(t, p["fecha"])
        except Exception as e:
            _dbg("[BUSCAR] error", t, e)
            hid = None
        if hid:
            _dbg("[BUSCAR] encontrado con", t, "->", p.get("nota", ""))
            return hid, abreviar(lf), abreviar(vf), fbm._last_hora[:5]
    return None, None, None, None


# ---------- arranque ----------

import network as _net
_wlan = _net.WLAN(_net.STA_IF)


def _conectar_wifi():
    """Prueba las redes de config.json (wifi_credentials), 10 s cada una."""
    try:
        with open(CONFIG_FILE) as f:
            creds = json.load(f).get("wifi_credentials", [])
    except Exception as e:
        print("[WIFI] config:", e)
        return
    _wlan.active(True)
    for c in creds:
        if _wlan.isconnected():
            return
        print("[WIFI] conectando a", c.get("ssid"))
        try:
            _wlan.connect(c["ssid"], c["password"])
        except Exception as e:
            print("[WIFI]", e)
            continue
        t0 = time.time()
        while not _wlan.isconnected() and time.time() - t0 < 10:
            time.sleep(0.5)
    print("[WIFI] conectado:", _wlan.isconnected())
try:
    # nombre en el router: marcador + ultimos 4 digitos de la MAC (p. ej. marcador-88fd)
    import ubinascii
    _wlan.active(True)
    _net.hostname("marcador-" + ubinascii.hexlify(_wlan.config("mac")).decode()[-4:])
except Exception as _e:
    print("[BOOT] hostname:", _e)
_conectar_wifi()
my_display.clear()
if _wlan.isconnected():
    _dbg("[BOOT] WiFi OK:", _wlan.ifconfig()[0])
    # nombre de la red (6 primeras letras para que quepa), en verde, 3 s
    my_display.draw_centered_text(_wlan.config("essid")[:6], 3, (0, 255, 0))
else:
    _dbg("[BOOT] WiFi NOK")
    my_display.draw_centered_text("NOK", 3, (255, 0, 0))
my_display.hold(3)
my_display.clear()


# ---------- hora real (NTP) para saltar partidos atascados ----------
MAX_MIN = 150        # si a los 150 min del inicio no esta FINALIZADO, pasa al siguiente
NOG_MIN = 30         # si 30 min despues del inicio sigue sin encontrarse, pasa al siguiente
_hora_ok = False


def _sync_hora():
    global _hora_ok
    try:
        import ntptime
        ntptime.settime()            # RTC en UTC
        _hora_ok = time.localtime()[0] >= 2024
    except Exception as e:
        print("[NTP] fallo:", e)


def _offset_es(t):
    """UTC+1 en invierno, UTC+2 entre el ultimo domingo de marzo y el de octubre."""
    y = time.localtime(t)[0]
    def ultimo_domingo(mes):
        d = 31
        while time.localtime(time.mktime((y, mes, d, 1, 0, 0, 0, 0)))[6] != 6:
            d -= 1
        return time.mktime((y, mes, d, 1, 0, 0, 0, 0))
    return 7200 if ultimo_domingo(3) <= t < ultimo_domingo(10) else 3600


def _ahora_local():
    t = time.time()
    return t + _offset_es(t)


def _min_desde_inicio(p):
    """Minutos desde la hora prevista del partido (negativo si aun no ha llegado); None sin hora."""
    if not _hora_ok:
        return None
    if p.get("ts"):
        return (time.time() - (p["ts"] - EPOCH_2000)) // 60
    try:
        d, mo, y = [int(x) for x in p["fecha"].split("/")]
        h, mi = [int(x) for x in p["hora"][:5].split(":")]
        return (_ahora_local() - time.mktime((y, mo, d, h, mi, 0, 0, 0))) // 60
    except Exception:
        return None


if _wlan.isconnected():
    _sync_hora()
print("[BOOT] hora NTP:", _hora_ok, time.localtime(_ahora_local())[:5] if _hora_ok else "")

_url = PARTIDOS_URL
try:
    with open(CONFIG_FILE, 'r') as _f:
        _cfg = json.load(_f)
    my_shared.DEBUG = bool(_cfg.get('debug', False))
    for _k, _v in _cfg.get('aliases', {}).items():
        ALIASES[_k.upper()] = _v
    _url = _cfg.get('partidos_url', PARTIDOS_URL)
    del _cfg
except Exception:
    my_shared.DEBUG = False
gc.collect()

PARTIDOS = cargar_partidos()
if _wlan.isconnected():
    _l = descargar_partidos(_url)
    if _l is not None:
        PARTIDOS = _l
_ult_descarga = time.time()
HECHOS = leer_hechos()
print("[BOOT] partidos:", len(PARTIDOS), "hechos:", len(HECHOS))


def siguiente():
    """Primer partido (por hora) no terminado ni pasado de MAX_MIN."""
    for q in PARTIDOS:
        if clave(q) in HECHOS:
            continue
        m = _min_desde_inicio(q)
        if m is not None and m > MAX_MIN:
            continue
        return q
    return None


ACTUAL = None
HEX_ID = None
AL = AV = HORA = ""
poll_count = 0

while True:
    try:
        # la lista vive en GitHub: se vuelve a bajar cada REFRESCO_SEG
        if time.time() - _ult_descarga > REFRESCO_SEG and _wlan.isconnected():
            _ult_descarga = time.time()
            _l = descargar_partidos(_url)
            if _l is not None:
                PARTIDOS = _l
            del _l

        p = siguiente()
        # sin partido cerca: modo mensajes (solo si la placa lo tiene y hay hora)
        if _hora_ok and modo_fbm.hay_mensajes():
            _m = _min_desde_inicio(p) if p else None
            if p is None or (_m is not None and _m < -modo_fbm.SALIR_MIN):
                print("[LOOP] sin partido en", modo_fbm.SALIR_MIN, "min -> mensajes")
                my_display.clear()
                modo_fbm.cambiar("mensajes")
        if p is None:
            if ACTUAL is not None:
                print("[LOOP] sin partidos pendientes")
                ACTUAL = None
            my_display.draw_centered_text("FIN", 3, (0, 200, 0))
            my_display.hold(60)
            continue
        if clave(p) != ACTUAL:
            ACTUAL = clave(p)
            _nombres_pend[0] = True
            HEX_ID = None
            print("[LOOP] partido:", p.get("fecha"), p.get("hora"), p.get("local"), "vs", p.get("visit"))

        if not _wlan.isconnected():
            _dbg("[WIFI] desconectado, reconectando")
            _conectar_wifi()
            time.sleep(2)
            if not _hora_ok and _wlan.isconnected():
                _sync_hora()
            fbm._sid = None
            fbm._key = None
            continue

        if HEX_ID is None:
            _dbg("[LOOP] buscando", p.get("local", ""), p["fecha"], p["hora"])
            HEX_ID, AL, AV, HORA = buscar_partido(p)
            fijar_colores(p)
            gc.collect()
            if HEX_ID is None:
                my_display.draw_centered_text("NOG", 3, (255, 100, 0))
                print("[DISPLAY] NOG -", p.get("local", ""), "no encontrado")
                _m = _min_desde_inicio(p)
                if _m is not None and _m > NOG_MIN:
                    print("[LOOP] NOG tras", _m, "min -> siguiente")
                    marcar_hecho(p)
                    continue
                my_display.hold(POLL_ESPERA)
                continue

        if fbm._sid is None or fbm._key is None:
            _dbg("[LOOP] sesion perdida, buscando id otra vez")
            HEX_ID = None
            continue

        poll_count += 1
        _dbg("[LOOP] Poll #{}".format(poll_count))
        m = fbm.get_marcador(HEX_ID)
        if not m:
            _dbg("[LOOP] sin datos, reintento")
            time.sleep(POLL_LIVE)
            continue

        rl, rv = m["rl"], m["rv"]
        estado = m.get("estado", "")
        cuarto = m.get("cuarto", "")
        tiempo = m.get("tiempo", "")
        descanso = m.get("descanso", False)
        if descanso and not _desc_prev[0]:
            _nombres_pend[0] = True           # acaba de terminar un cuarto
        _desc_prev[0] = descanso
        parado = m.get("parado", False)
        hora_acc = m.get("hora_acc")
        jg = m.get("jugada")
        jugada = None
        if jg and (jg.get("id"), ACTUAL) != _jug_vista[0]:
            jugada = (jg["txt"], color_jugada(p, jg))
            _jug_vista[0] = (jg.get("id"), ACTUAL)
        _dbg("[LOOP] {} {}-{} {} | {} {} | {}".format(AL, rl, rv, AV, cuarto, tiempo, estado))
        del m
        gc.collect()

        if estado == "FINALIZADO":
            _dbg("[LOOP] FINALIZADO", AL, rl, rv, AV, "-> siguiente partido")
            mostrar_marcador(rl, rv)
            my_display.hold(20)
            marcar_hecho(p)
            HEX_ID = None
            continue

        if rl == 0 and rv == 0 and not tiempo:
            _dbg("[ESPERA] hora", HORA, AL, AV)
            mostrar_espera(HORA, AL, AV, POLL_ESPERA)
            continue

        mostrar_en_vivo(rl, rv, cuarto, tiempo, POLL_LIVE, AL, AV, jugada, descanso, parado, hora_acc)

    except Exception as e:
        print("[MAIN] error, reintento en 15s:", e)
        sys.print_exception(e)
        fbm._sid = None
        fbm._key = None
        time.sleep(15)
