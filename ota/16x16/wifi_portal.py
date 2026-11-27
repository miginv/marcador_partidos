# WiFi al arrancar: prueba las redes guardadas en config.json (wifi_credentials) y, si
# no conecta ninguna, abre la red abierta "scoreboard" con un portal cautivo como las
# redes de invitados: al conectarse el movil abre la pagina, se elige la red y la clave,
# se guarda (la primera de la lista) y la placa se reinicia.
import json
import time
import network
import socket
import select
import machine

AP_SSID = "scoreboard"
AP_IP = "192.168.4.1"
INTENTO_SEG = 15            # por red guardada (tras un reinicio el router a veces tarda)
VUELTAS = 3                 # vueltas a las redes guardadas antes de abrir el portal
PORTAL_MAX_SEG = 10 * 60    # sin nadie usando el portal: reinicia y vuelve a probar
CONFIG_FILE = "config.json"

sta = network.WLAN(network.STA_IF)


def _creds():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f).get("wifi_credentials", [])
    except Exception:
        return []


def conectar(hostname=None, disp=None):
    """Prueba las redes guardadas que se ven. True si queda conectada."""
    sta.active(True)
    if hostname:
        try:
            network.hostname(hostname)
        except Exception as e:
            print("[WIFI] hostname:", e)
    if sta.isconnected():
        return True
    creds = _creds()
    try:
        visibles = set(r[0].decode("utf-8", "ignore") for r in sta.scan())
    except Exception:
        visibles = None
    for c in creds:
        ssid = c.get("ssid", "")
        if visibles is not None and ssid not in visibles:
            continue
        print("[WIFI] conectando a", ssid)
        if disp:
            disp.draw_centered_text("WIFI", 3, (0, 80, 255))
        try:
            sta.connect(ssid, c.get("password", ""))
        except Exception as e:
            print("[WIFI]", e)
            continue
        t0 = time.time()
        while not sta.isconnected() and time.time() - t0 < INTENTO_SEG:
            time.sleep(0.5)
        if sta.isconnected():
            print("[WIFI] conectado a", ssid, sta.ifconfig()[0])
            return True
        try:
            sta.disconnect()
        except Exception:
            pass
    return False


def asegurar(hostname=None, disp_mod=None):
    """Conecta con las redes guardadas; si no puede, portal (no vuelve: reinicia)."""
    disp = None
    if disp_mod:
        disp = __import__(disp_mod)
    for vuelta in range(VUELTAS):
        if conectar(hostname, disp):
            if disp:
                disp.clear()
            return True
        print("[WIFI] vuelta", vuelta + 1, "sin conexion")
    if disp is None:
        disp = __import__("marcador_disp")
    portal(disp)


# ---------- portal ----------

def _unquote(s):
    s = s.replace("+", " ")
    out = bytearray()
    i = 0
    b = s.encode()
    while i < len(b):
        if b[i] == 37 and i + 2 < len(b):          # %XX
            try:
                out.append(int(b[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(b[i])
        i += 1
    return out.decode("utf-8", "ignore")


def _parse(qs):
    d = {}
    for par in qs.split("&"):
        if "=" in par:
            k, v = par.split("=", 1)
            d[_unquote(k)] = _unquote(v)
    return d


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def guardar(ssid, password):
    """Pone la red la primera de wifi_credentials sin tocar el resto de config.json."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    creds = [c for c in cfg.get("wifi_credentials", []) if c.get("ssid") != ssid]
    creds.insert(0, {"ssid": ssid, "password": password})
    cfg["wifi_credentials"] = creds[:8]
    with open(CONFIG_FILE + ".tmp", "w") as f:
        json.dump(cfg, f)
    import os
    try:
        os.remove(CONFIG_FILE)
    except OSError:
        pass
    os.rename(CONFIG_FILE + ".tmp", CONFIG_FILE)
    print("[PORTAL] red guardada:", ssid)


def _pagina(redes, aviso=""):
    ops = "".join('<option value="%s">' % _esc(r) for r in redes)
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Scoreboard WiFi</title><style>body{font-family:sans-serif;margin:24px;"
            "max-width:420px}input,button{font-size:18px;width:100%;padding:10px;margin:6px 0 14px;"
            "box-sizing:border-box}button{background:#1565c0;color:#fff;border:0;border-radius:6px}"
            "</style></head><body><h2>Marcador: WiFi</h2>" + aviso +
            "<form method='post' action='/guardar'><label>Red</label>"
            "<input name='ssid' list='r' autocomplete='off' required><datalist id='r'>" + ops +
            "</datalist><label>Clave (vac&iacute;a si es abierta)</label>"
            "<input name='password' type='password'><button>Guardar</button></form>"
            "<p>Redes guardadas: %d</p></body></html>" % len(_creds()))


def _dns_respuesta(q):
    """Responde a cualquier consulta con la IP del portal (portal cautivo)."""
    try:
        fin = 12
        while q[fin] != 0:
            fin += q[fin] + 1
        fin += 5                                   # 0 final + tipo + clase
        return (q[:2] + b"\x81\x80" + q[4:6] + q[4:6] + b"\x00\x00\x00\x00" + q[12:fin] +
                b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" +
                bytes(int(x) for x in AP_IP.split(".")))
    except Exception:
        return None


def _leer_peticion(cl):
    cl.settimeout(3)
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 4096:
        c = cl.recv(1024)
        if not c:
            break
        data += c
    cab, _, cuerpo = data.partition(b"\r\n\r\n")
    lineas = cab.decode("utf-8", "ignore").split("\r\n")
    metodo, ruta = (lineas[0].split(" ") + ["", ""])[:2]
    largo = 0
    for l in lineas[1:]:
        if l.lower().startswith("content-length:"):
            largo = int(l.split(":", 1)[1].strip() or 0)
    while len(cuerpo) < largo and len(cuerpo) < 2048:
        c = cl.recv(1024)
        if not c:
            break
        cuerpo += c
    return metodo, ruta, cuerpo.decode("utf-8", "ignore")


def _enviar(cl, estado, cuerpo="", extra=""):
    cl.send(("HTTP/1.1 %s\r\nContent-Type: text/html; charset=utf-8\r\n%s"
             "Connection: close\r\nContent-Length: %d\r\n\r\n" %
             (estado, extra, len(cuerpo.encode()))).encode())
    if cuerpo:
        cl.sendall(cuerpo.encode())


def portal(disp):
    try:
        redes = sorted(set(r[0].decode("utf-8", "ignore") for r in sta.scan() if r[0]))
    except Exception:
        redes = []
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, authmode=network.AUTH_OPEN)
    try:
        ap.ifconfig((AP_IP, "255.255.255.0", AP_IP, AP_IP))
    except Exception:
        pass
    print("[PORTAL] red abierta", AP_SSID, "en", AP_IP)

    web = socket.socket()
    web.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    web.bind(socket.getaddrinfo("0.0.0.0", 80)[0][-1])
    web.listen(3)
    web.setblocking(False)
    dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns.bind(socket.getaddrinfo("0.0.0.0", 53)[0][-1])
    dns.setblocking(False)
    pl = select.poll()
    pl.register(web, select.POLLIN)
    pl.register(dns, select.POLLIN)

    texto = "WIFI: " + AP_SSID
    fijo = sum(disp._ancho_scroll(c) + 1 for c in "HOTSPOT") - 1 <= disp.WIDTH
    if not fijo:                                   # 24x8: no cabe, va tambien en el scroll
        texto = "HOTSPOT - " + texto
    ancho = sum(disp._ancho_scroll(c) + 1 for c in texto)
    ultimo_uso = time.time()
    k = 0 if fijo else 1
    fase_t = time.ticks_add(time.ticks_ms(), 0 if fijo else -3000)
    while True:
        # pantalla sin bloquear: "HOTSPOT" 3 s y luego el nombre de la red en scroll
        fase = time.ticks_diff(time.ticks_ms(), fase_t)
        if fase < 3000:
            if k == 0:
                disp.draw_centered_text("HOTSPOT", 3, (255, 160, 0))
                k = 1
        else:
            x = disp.WIDTH - (k - 1)
            disp.fb.fill(0)
            for c in texto:
                disp.draw_char_at_position(c, x, 3)
                x += disp._ancho_scroll(c) + 1
            disp.show_framebuffer((0, 120, 255))
            k += 1
            if k - 1 > ancho + disp.WIDTH:
                k = 0 if fijo else 1
                fase_t = time.ticks_add(time.ticks_ms(), 0 if fijo else -3000)

        if pl.poll(60):
            # ambos sin bloquear: no depende de que objeto devuelva poll
            try:
                q, addr = dns.recvfrom(512)
                r = _dns_respuesta(q)
                if r:
                    dns.sendto(r, addr)
            except OSError:
                pass
            try:
                cl, _ = web.accept()
            except OSError:
                cl = None
        else:
            cl = None
        if cl is not None:
            ultimo_uso = time.time()
            try:
                metodo, ruta, cuerpo = _leer_peticion(cl)
                if ruta.startswith("/guardar"):
                    d = _parse(cuerpo if metodo == "POST" else ruta.partition("?")[2])
                    ssid = d.get("ssid", "").strip()
                    if ssid:
                        guardar(ssid, d.get("password", ""))
                        _enviar(cl, "200 OK", "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                                "<meta name='viewport' content='width=device-width'></head><body>"
                                "<h2>Guardado</h2><p>El marcador se reinicia y se conecta a <b>%s</b>."
                                "</p></body></html>" % _esc(ssid))
                        cl.close()
                        disp.draw_centered_text("OK", 3, (0, 255, 0))
                        time.sleep(2)
                        machine.reset()
                    _enviar(cl, "200 OK", _pagina(redes, "<p style='color:red'>Falta la red</p>"))
                elif ruta == "/" or ruta.startswith("/?"):
                    _enviar(cl, "200 OK", _pagina(redes))
                else:
                    # comprobaciones de conectividad de Android/iOS/Windows: al portal
                    _enviar(cl, "302 Found", "", "Location: http://%s/\r\n" % AP_IP)
            except Exception as e:
                print("[PORTAL] peticion:", e)
            try:
                cl.close()
            except Exception:
                pass

        if time.time() - ultimo_uso > PORTAL_MAX_SEG:
            print("[PORTAL] sin uso, reinicio para volver a probar las redes guardadas")
            machine.reset()
