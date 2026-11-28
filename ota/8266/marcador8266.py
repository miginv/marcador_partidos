# Marcador ligero para ESP8266: el Awtrix marcador estandar (ESP32) no cabe en sus ~36 KB.
# Hace de marcador: lee la lista y el partido del servidor propio (relay, http sin TLS,
# con su clave) y pinta en la matriz 32x8 el reloj (cuarto + mm:ss) y el marcador. Sin
# OTA ni web: para cambiar algo, por USB (config.json). Recibe los mensajes de la domotica
# como una Awtrix: POST /api/notify {"text", "color", "repeat"} (sin iconos, en mayusculas).
# config.json: {"wifi": [{"ssid","password"}...], "relay": "http://host", "clave": "...",
#   "brillo": 0.1, "pin": 4, "ancho": 32, "mapa": "8x8", "girada": false}
#   mapa "8x8" (por defecto): modulos 8x8 encadenados de izquierda a derecha, cada uno con
#     sus filas de izquierda a derecha sin zigzag (como la 24x8, con 4 modulos);
#   mapa "zigzag": tira en zigzag de la Awtrix, con "leds_fila" (33: el de la curva no se ve)
#     y "derecha" (la primera fila empieza por la derecha);
#   girada: matriz montada al reves.
import gc
import json
import socket
import time
import machine
import network
import neopixel
gc.collect()

with open("config.json") as _f:
    CFG = json.load(_f)
W = CFG.get("ancho", 32)
H = 8
MAPA = CFG.get("mapa", "8x8")
FILA = CFG.get("leds_fila", W) if MAPA == "zigzag" else W
N = FILA * H
np = neopixel.NeoPixel(machine.Pin(CFG.get("pin", 4)), N)
BRILLO = CFG.get("brillo", 0.1)
DERECHA = CFG.get("derecha", True)
GIRADA = CFG.get("girada", False)
RELAY = CFG.get("relay", "http://34.30.243.27").split("://", 1)[-1].rstrip("/")
CLAVE = CFG.get("clave", "")
VERSION = "1.1"
EPOCH = 946684800 if time.gmtime(0)[0] == 2000 else 0    # el ESP8266 cuenta desde 2000

AZUL, ROJO, VERDE, BLANCO, NARANJA = (0, 0, 255), (255, 0, 0), (0, 255, 0), (255, 255, 255), (255, 100, 0)
NUESTROS = ("SERRACINES", "COSLADA")


def idx(x, y):
    if GIRADA:
        x, y = W - 1 - x, H - 1 - y
    if MAPA == "8x8":
        return (x // 8) * 64 + y * 8 + x % 8
    fila = y * FILA
    if (y % 2 == 0) == DERECHA:
        return fila + W - 1 - x
    return fila + x          # el LED de la curva (si FILA > W) queda al final de la fila, apagado


def borrar():
    np.fill((0, 0, 0))


def pon(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        np[idx(x, y)] = c


def color(c):
    return (int(c[0] * BRILLO), int(c[1] * BRILLO), int(c[2] * BRILLO))


# digitos grandes 5x8 (trazo de 2 px), bit 7 = columna izquierda
GRANDE = (b"\xf8\xf8\xd8\xd8\xd8\xd8\xf8\xf8", b"\x18\x18\x18\x18\x18\x18\x18\x18",
          b"\xf8\xf8\x18\xf8\xf8\xc0\xf8\xf8", b"\xf8\xf8\x18\xf8\xf8\x18\xf8\xf8",
          b"\xd8\xd8\xd8\xf8\xf8\x18\x18\x18", b"\xf8\xf8\xc0\xf8\xf8\x18\xf8\xf8",
          b"\xf8\xf8\xc0\xf8\xf8\xd8\xf8\xf8", b"\xf8\xf8\x18\x18\x18\x18\x18\x18",
          b"\xf8\xf8\xd8\xf8\xf8\xd8\xf8\xf8", b"\xf8\xf8\xd8\xf8\xf8\x18\xf8\xf8")
# letras y digitos 3x5 (5 filas de 3 bits; los de 1 columna usan el bit del medio)
PEQ = {"0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7), "3": (7, 1, 3, 1, 7),
       "4": (5, 5, 7, 1, 1), "5": (7, 4, 7, 1, 7), "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 2, 2),
       "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7),
       "A": (7, 5, 7, 5, 5), "B": (6, 5, 6, 5, 6), "C": (7, 4, 4, 4, 7), "D": (6, 5, 5, 5, 6),
       "E": (7, 4, 6, 4, 7), "F": (7, 4, 6, 4, 4), "G": (7, 4, 5, 5, 7), "H": (5, 5, 7, 5, 5),
       "I": (7, 2, 2, 2, 7), "J": (1, 1, 1, 5, 7), "K": (5, 5, 6, 5, 5), "L": (4, 4, 4, 4, 7),
       "M": (5, 7, 7, 5, 5), "N": (6, 5, 5, 5, 5), "O": (2, 5, 5, 5, 2), "P": (7, 5, 7, 4, 4),
       "Q": (2, 5, 5, 6, 3), "R": (6, 5, 6, 5, 5), "S": (3, 4, 2, 1, 6), "T": (7, 2, 2, 2, 2),
       "U": (5, 5, 5, 5, 7), "V": (5, 5, 5, 5, 2), "W": (5, 5, 7, 7, 5), "X": (5, 5, 2, 5, 5),
       "Y": (5, 5, 2, 2, 2), "Z": (7, 1, 2, 4, 7),
       ":": (0, 2, 0, 2, 0), ".": (0, 0, 0, 0, 2), ",": (0, 0, 0, 2, 2), "!": (2, 2, 2, 0, 2),
       "'": (2, 2, 0, 0, 0), "-": (0, 0, 7, 0, 0), "+": (0, 2, 7, 2, 0), "=": (0, 7, 0, 7, 0),
       "?": (7, 1, 2, 0, 2), "/": (1, 1, 2, 4, 4), "%": (5, 1, 2, 4, 5), "(": (1, 2, 2, 2, 1),
       ")": (4, 2, 2, 2, 4), "*": (7, 5, 7, 0, 0), " ": (0, 0, 0, 0, 0)}
ANCHO = {":": 1, ".": 1, ",": 1, "!": 1, "'": 1, " ": 2}
TILDES = {"\u00c1": "A", "\u00c9": "E", "\u00cd": "I", "\u00d3": "O", "\u00da": "U", "\u00dc": "U",
          "\u00d1": "N", "\u00ba": "*", "\u00b0": "*", "\u00aa": "A", "\u00c7": "C"}


def limpiar(t):
    """Mayusculas sin tildes; lo que no tiene letra pasa a espacio."""
    t = t.upper()
    return "".join(c if c in PEQ else TILDES.get(c, " ") for c in t)


def ancho_peq(t):
    return sum(ANCHO.get(c, 3) for c in t) + len(t) - 1


def texto(t, x, c, y=2):
    """Texto 3x5 en color c (sin escalar); devuelve la x final."""
    c = color(c)
    for ch in t:
        w = ANCHO.get(ch, 3)
        if -3 < x < W:
            g = PEQ.get(ch, PEQ[" "])
            for f in range(5):
                for k in range(w):
                    if g[f] & ((4 >> k) if w == 3 else 2):
                        pon(x + k, y + f, c)
        x += w + 1
    return x


def centrado(t, c, x0=0, x1=None):
    x1 = W if x1 is None else x1
    texto(t, x0 + max(0, (x1 - x0 - ancho_peq(t)) // 2), c)


def numero_grande(n, c, x0, x1):
    s = str(n)
    if len(s) > 3:
        s = s[-3:]
    w = len(s) * 6 - 1
    x = x0 + max(0, (x1 - x0 - w) // 2)
    c = color(c)
    for ch in s:
        g = GRANDE[ord(ch) - 48]
        for y in range(8):
            for k in range(5):
                if g[y] & (0x80 >> k):
                    pon(x + k, y, c)
        x += 6


def mostrar():
    np.write()


# ---------- WiFi y hora ----------
sta = network.WLAN(network.STA_IF)
sta.active(True)
network.WLAN(network.AP_IF).active(False)
try:
    network.hostname("marcador-" + "".join("%02x" % b for b in sta.config("mac")[-2:]))
except Exception:
    pass


def wifi():
    if sta.isconnected():
        return True
    for red in CFG.get("wifi", []):
        borrar()
        centrado("WIFI", NARANJA)
        mostrar()
        sta.connect(red["ssid"], red.get("password", ""))
        for _ in range(30):
            if sta.isconnected():
                print("[WIFI]", red["ssid"], sta.ifconfig()[0])
                return True
            dormir(0.5)
    return False


hora_ok = False


def poner_hora():
    global hora_ok
    try:
        import ntptime
        ntptime.settime()
        hora_ok = True
    except Exception as e:
        print("[NTP]", e)


def ahora_utc():
    return time.time() + EPOCH


def ahora_local():
    """Hora de Madrid: UTC+1, +2 de ultimo domingo de marzo a ultimo de octubre (1:00 UTC)."""
    t = ahora_utc()
    a = time.gmtime(t - EPOCH)[0]
    def ult_domingo(mes):
        d = time.mktime((a, mes, 31, 1, 0, 0, 0, 0)) + EPOCH
        return d - ((time.gmtime(d - EPOCH)[6] + 1) % 7) * 86400
    return t + (7200 if ult_domingo(3) <= t < ult_domingo(10) else 3600)


# ---------- servidor ----------
def get(ruta):
    host, puerto = (RELAY.split(":") + ["80"])[:2]
    ruta += ("&" if "?" in ruta else "?") + "k=" + CLAVE
    gc.collect()
    s = socket.socket()
    try:
        s.settimeout(8)
        s.connect(socket.getaddrinfo(host, int(puerto))[0][-1])
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (ruta, host)).encode())
        r = b""
        while len(r) < 16384:
            c = s.recv(512)
            if not c:
                break
            r += c
    finally:
        s.close()
    i = r.find(b"\r\n\r\n")
    if i < 0 or b" 200 " not in r[:16]:
        return None
    r = r[i + 4:]
    gc.collect()
    return json.loads(r)


ANTES_SEG = 15 * 60     # empieza a seguir el partido 15 min antes
MAX_SEG = 150 * 60      # sin FINALIZADO a los 150 min, siguiente
LISTA_SEG = 10 * 60
partidos = []
hechos = []


def bajar_lista():
    global partidos
    try:
        d = get("/partidos.json")
    except Exception as e:
        print("[LISTA]", e)
        return
    if d:
        partidos = [(p["ts"], p["notif"], p.get("hora", ""), p.get("local", ""), p.get("visit", ""))
                    for p in d.get("partidos", []) if p.get("notif")]
        partidos.sort()
        print("[LISTA]", len(partidos), "partidos")
    del d
    gc.collect()


def siguiente():
    t = ahora_utc()
    for p in partidos:
        if p[1] in hechos or (hora_ok and t - p[0] > MAX_SEG):
            continue
        return p
    return None


def seg(t):
    try:
        mm, ss = t.split(":")
        return int(mm) * 60 + int(ss)
    except Exception:
        return None


def seg_desde(h):
    """Segundos desde la hora del dia 'hh:mm:ss' de la ultima accion; None sin hora."""
    if not hora_ok or not h:
        return None
    try:
        a, b, c = [int(x) for x in h.split(":")[:3]]
    except Exception:
        return None
    return (int(ahora_local()) % 86400 - (a * 3600 + b * 60 + c)) % 86400


def nuestro(n):
    n = (n or "").upper()
    return any(k in n for k in NUESTROS)


# ---------- pantallas ----------
def pinta_reloj(cuarto, r, puntos):
    borrar()
    # el cuarto solo con el numero (Q4 -> 4; prorroga OT1), como las demas pantallas
    centrado((cuarto or "").lstrip("Q"), ROJO, 0, 14)
    x = 15
    x = texto("%02d" % (r // 60), x, VERDE)
    if puntos:
        texto(":", x, VERDE)
    texto("%02d" % (r % 60), x + 2, VERDE)
    mostrar()


def pinta_marcador(rl, rv, cl, cv):
    borrar()
    numero_grande(rl, cl, 0, W // 2)
    numero_grande(rv, cv, W // 2, W)
    mostrar()


def pinta_espera(p):
    borrar()
    centrado(p[2][:5] if p else "--:--", VERDE)
    mostrar()


def pinta_hora():
    borrar()
    if hora_ok:
        t = time.gmtime(int(ahora_local()) - EPOCH)
        centrado("%02d:%02d" % (t[3], t[4]), BLANCO)
    mostrar()


# ---------- mensajes de la domotica (POST /api/notify, como una Awtrix) ----------
srv = None
cola = []
MAX_COLA = 4


def abrir_servidor():
    global srv
    try:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(socket.getaddrinfo("0.0.0.0", 80)[0][-1])
        srv.listen(2)
        srv.setblocking(False)
    except Exception as e:
        print("[HTTP]", e)
        srv = None


def responder(cl, codigo, cuerpo):
    cl.send(("HTTP/1.1 %d %s\r\nContent-Type: application/json\r\nConnection: close\r\n"
             "Content-Length: %d\r\n\r\n" % (codigo, "OK" if codigo == 200 else "Error", len(cuerpo))).encode())
    cl.send(cuerpo.encode())


def atender():
    if not srv:
        return
    try:
        cl, _ = srv.accept()
    except OSError:
        return
    try:
        cl.settimeout(3)
        raw = b""
        while b"\r\n\r\n" not in raw and len(raw) < 2048:
            c = cl.recv(256)
            if not c:
                break
            raw += c
        i = raw.find(b"\r\n\r\n")
        cab, cuerpo = (raw[:i], raw[i + 4:]) if i >= 0 else (raw, b"")
        largo = 0
        for l in cab.split(b"\r\n"):
            if l.lower().startswith(b"content-length:"):
                largo = int(l.split(b":")[1].strip() or 0)
        while len(cuerpo) < min(largo, 1500):
            c = cl.recv(256)
            if not c:
                break
            cuerpo += c
        linea = cab.split(b"\r\n")[0]
        if linea.startswith(b"POST /api/notify") or linea.startswith(b"POST /api/custom"):
            d = json.loads(cuerpo or b"{}")
            t = d.get("text", "")
            if isinstance(t, list):        # Awtrix: [{"t": "...", "c": "..."}...]
                t = "".join(x.get("t", "") for x in t if isinstance(x, dict))
            if t and len(cola) < MAX_COLA:
                cola.append((str(t)[:120], d.get("color"), d.get("repeat", 1)))
            responder(cl, 200, '{"success": true}')
        elif linea.startswith(b"GET /api/version"):
            responder(cl, 200, json.dumps({"tipo": "8266", "version": VERSION, "ip": sta.ifconfig()[0],
                                           "libre": gc.mem_free(), "partido": actual}))
        else:
            responder(cl, 404, '{"success": false}')
    except Exception as e:
        print("[HTTP]", e)
    finally:
        cl.close()
        gc.collect()


def leer_color(c):
    try:
        if isinstance(c, str) and c.startswith("#") and len(c) == 7:
            return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
        if isinstance(c, (list, tuple)) and len(c) == 3:
            return (int(c[0]), int(c[1]), int(c[2]))
        if isinstance(c, int):
            return ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    except Exception:
        pass
    return BLANCO


def mensaje(t, c, rep):
    """El texto entra por la derecha y sale por la izquierda, 'repeat' veces (max 5)."""
    t = limpiar(t)
    w = ancho_peq(t)
    c = leer_color(c)
    try:
        rep = max(1, min(int(rep or 1), 5))
    except (TypeError, ValueError):
        rep = 1
    print("[MENSAJE]", t)
    for _ in range(rep):
        for x in range(W, -w - 1, -1):
            borrar()
            texto(t, x, c)
            mostrar()
            atender()
            time.sleep_ms(45)
    borrar()
    mostrar()


wdt = None


def dormir(seg):
    """sleep que alimenta el perro guardian (en el ESP8266 salta a los pocos segundos)."""
    fin = time.ticks_add(time.ticks_ms(), int(seg * 1000))
    while time.ticks_diff(fin, time.ticks_ms()) > 0:
        if wdt:
            wdt.feed()
        atender()
        if cola:
            return            # hay mensaje: se muestra ya
        time.sleep_ms(100)


# ---------- bucle ----------
borrar()
centrado("8266", AZUL)
mostrar()
wifi()
abrir_servidor()
poner_hora()
bajar_lista()
t_lista = time.time()
t_ntp = time.time()
# sin machine.WDT: en el ESP8266 salta a los pocos segundos y una peticion puede tardar 8 s
POLL = 5
m = None            # ultimo marcador del partido seguido
ancla = [None, 0, 0]    # (cuarto, tiempo) de la api, segundos restantes, ticks del ancla
actual = None
t_poll = 0
fase = 0

while True:
    try:
        if wdt:
            wdt.feed()
        if not sta.isconnected():
            if not wifi():
                borrar()
                centrado("WIFI", ROJO)
                mostrar()
                dormir(5)
                continue
        while cola:
            mensaje(*cola.pop(0))
        if time.time() - t_lista > LISTA_SEG:
            t_lista = time.time()
            bajar_lista()
        if not hora_ok or time.time() - t_ntp > 6 * 3600:
            t_ntp = time.time()
            poner_hora()
        p = siguiente()
        if p is None or (hora_ok and ahora_utc() < p[0] - ANTES_SEG):
            # sin partido cerca: la hora, y la del proximo partido si es hoy
            actual, m = None, None
            pinta_hora()
            dormir(4)
            if p and p[0] - ahora_utc() < 12 * 3600:
                pinta_espera(p)
                dormir(2)
            continue
        if p[1] != actual:
            actual, m, t_poll = p[1], None, 0
            cl, cv = (ROJO, AZUL) if nuestro(p[4]) and not nuestro(p[3]) else (AZUL, ROJO)
            print("[PARTIDO]", p[2], p[3], "-", p[4])
        if t_poll == 0 or time.ticks_diff(time.ticks_ms(), t_poll) >= POLL * 1000:
            t_poll = time.ticks_ms() or 1
            try:
                d = get("/m/%s.json" % actual)
            except Exception as e:
                print("[MARCADOR]", e)
                d = None
            if d:
                m = d.get("m")
            del d
            gc.collect()
        if not m or not m.get("tiempo"):
            pinta_espera(p)
            dormir(1)
            continue
        if m.get("estado") == "FINALIZADO":
            pinta_marcador(m.get("rl", 0), m.get("rv", 0), cl, cv)
            dormir(1)
            if hora_ok and ahora_utc() - p[0] > 0 and fase > 300:
                hechos.append(actual)
                fase = 0
            fase += 1
            continue
        # reloj: la API da el tiempo de la ultima accion; si corre, se descuenta lo que pasa
        s = seg(m["tiempo"]) or 0
        corre = not (m.get("parado") or m.get("descanso"))
        clave = (m.get("cuarto"), m["tiempo"])
        if ancla[0] != clave:
            dt = seg_desde(m.get("hora_acc")) if corre else None
            ancla[0], ancla[1], ancla[2] = clave, s - (dt if dt is not None and dt < 300 else 0), time.ticks_ms()
        r = ancla[1] - (time.ticks_diff(time.ticks_ms(), ancla[2]) // 1000 if corre else 0)
        r = max(0, r)
        # 10 s reloj, 5 s marcador
        fase = (fase + 1) % 15
        if fase < 10:
            pinta_reloj(m.get("cuarto", ""), r, fase % 2 == 0 or not corre)
        else:
            pinta_marcador(m.get("rl", 0), m.get("rv", 0), cl, cv)
        dormir(1)
    except Exception as e:
        import sys
        sys.print_exception(e)
        dormir(2)
