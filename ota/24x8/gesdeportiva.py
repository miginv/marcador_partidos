"""
gesdeportiva.py — FBM scraper MicroPython para ESP32.
Usa socket+ssl directo (sin urequests) para evitar ECONNABORTED en SSL.
VERSION DEBUG con prints. Streaming en buscar y get_marcador.
"""
import socket
import ssl
import ujson
import gc
import my_shared


def _dbg(*a):
    if my_shared.DEBUG:
        _dbg(*a)

_HOST = "appaficionfbm.gesdeportiva.es"
_PORT = 443
_UA = "Dalvik/2.1.0 (Linux; U; Android 13; sdk_gphone64_arm64 Build/TE1A.220922.021)"
_sid = None
_key = None
_CUARTOS = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4", 5: "OT1", 6: "OT2"}


def _urlencode(d):
    def _enc(s):
        return (str(s)
                .replace('%','%25').replace('&','%26')
                .replace('+','%2B').replace(' ','+'))
    return "&".join("{}={}".format(k, _enc(v)) for k, v in d.items())


def _ssl_connect(path, body_str):
    """Abre conexion SSL y envia POST. Devuelve socket listo para leer body."""
    body_b = body_str.encode()
    req = (
        "POST /{} HTTP/1.0\r\n"
        "Host: {}\r\nUser-Agent: {}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Content-Length: {}\r\nConnection: close\r\n\r\n"
    ).format(path, _HOST, _UA, len(body_b)).encode() + body_b
    addr = socket.getaddrinfo(_HOST, _PORT, 0, socket.SOCK_STREAM)[0][-1]
    s = socket.socket()
    s.settimeout(15)
    s.connect(addr)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(s, server_hostname=_HOST)
    s.write(req)
    gc.collect()
    return s


def _https_post_small(path, body_str):
    """Para respuestas pequenas (<8KB): registro. NO usar para busqueda/marcador."""
    gc.collect()
    _dbg("[HTTP] POST /" + path, "body len:", len(body_str))
    s = _ssl_connect(path, body_str)
    resp = b""
    try:
        while True:
            try:
                chunk = s.read(512)
            except Exception:
                break
            if not chunk:
                break
            resp += chunk
            gc.collect()
    finally:
        s.close(); gc.collect()
    idx = resp.find(b"\r\n\r\n")
    body = resp[idx+4:] if idx >= 0 else resp
    del resp; gc.collect()
    _dbg("[HTTP] Body len:", len(body))
    j = ujson.loads(body)
    del body; gc.collect()
    return j


def _registrar():
    global _sid, _key
    import ubinascii, os
    uid = "esp-" + ubinascii.hexlify(os.urandom(4)).decode()
    _dbg("[FBM] Registrando uid:", uid)
    body = _urlencode({
        "accion": "registrar", "uid": uid,
        "plataforma": "android", "tipo_dispositivo": "phone", "version": "5",
    })
    j = _https_post_small("dispositivo.ashx", body)
    _dbg("[FBM] Registro resp:", j.get("resultado"), "err:", j.get("error",""))
    if j.get("resultado") != "correcto":
        raise RuntimeError("Registro: " + str(j.get("error", j)))
    _sid = j["id_dispositivo"]
    _key = j["key"]
    del j; gc.collect()
    _dbg("[FBM] Registro OK sid:", _sid[:8], "...")


def _extract_str(buf, key_b):
    """Extrae valor string de buf: key_b + '"' + value + '"'"""
    ki = buf.find(key_b)
    if ki < 0:
        return None
    start = ki + len(key_b)
    end = buf.find(b'"', start)
    if end > start:
        return buf[start:end].decode()
    return None


def _extract_int(buf, key_b):
    """Extrae valor entero de buf: key_b + digits"""
    ki = buf.find(key_b)
    if ki < 0:
        return None
    start = ki + len(key_b)
    end = start
    while end < len(buf) and chr(buf[end]).isdigit():
        end += 1
    if end > start:
        try:
            return int(buf[start:end])
        except:
            pass
    return None


_last_local = ""
_last_visit = ""
_last_hora = ""


_ACENTOS = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N", "Ü": "U",
            "À": "A", "È": "E", "Ì": "I", "Ò": "O", "Ù": "U"}


def _limpia(v):
    """Nombre de la API: decodifica \\u0026 (&) y quita tildes para la fuente 5 px."""
    v = v.replace("\\u0026", "&")
    return "".join(_ACENTOS.get(c, c) for c in v)


def _nombres_de(seg):
    """Extrae NombreEquipoLocal/Visitante del ultimo bloque antes de Fecha."""
    global _last_local, _last_visit, _last_hora
    _last_local = ""
    _last_visit = ""
    _last_hora = ""
    hi = seg.rfind(b'"Hora":"')
    if hi >= 0:
        hs = hi + 8
        he = seg.find(b'"', hs)
        if he > hs:
            _last_hora = seg[hs:he].decode("utf-8", "replace")
    for key, attr in ((b'"NombreEquipoLocal":"', 1), (b'"NombreEquipoVisitante":"', 2)):
        i = seg.rfind(key)
        if i >= 0:
            st = i + len(key)
            en = seg.find(b'"', st)
            if en > st:
                val = _limpia(seg[st:en].decode("utf-8", "replace"))
                if attr == 1:
                    _last_local = val
                else:
                    _last_visit = val


def _capturar_en_vivo(buf):
    """Guarda nombres y hora del ultimo bloque de partido visto en el stream."""
    global _last_local, _last_visit, _last_hora
    for key, attr in ((b'"NombreEquipoLocal":"', 1), (b'"NombreEquipoVisitante":"', 2)):
        i = buf.rfind(key)
        if i >= 0:
            st = i + len(key)
            en = buf.find(b'"', st)
            if en > st:
                val = _limpia(buf[st:en].decode("utf-8", "replace"))
                if attr == 1:
                    _last_local = val
                else:
                    _last_visit = val
    hi = buf.rfind(b'"Hora":"')
    if hi >= 0:
        hs = hi + 8
        he = buf.find(b'"', hs)
        if he > hs:
            _last_hora = buf[hs:he].decode("utf-8", "replace")


def buscar_id_partido(nombre, fecha_ddmmyyyy, skip=0, notif=None):
    """Busqueda streaming sin acumular JSON. Rastrea last_id para superar imagenes base64."""
    global _sid, _key
    gc.collect()
    if not _sid:
        _registrar()
    gc.collect()

    fecha_b = ('"Fecha":"' + fecha_ddmmyyyy + '"').encode()
    id_prefix = b'"IdPartido":"'
    term_b = b'"Terminado"'
    cancel_b = b'"Cancelado"'
    notif_b = ('"IdPartidoNotificacion":"' + notif + '"').encode() if notif else None

    body_str = _urlencode({"id_dispositivo": _sid, "key": _key,
                           "accion": "buscarPartido", "texto": nombre, "skip": str(skip)})
    _dbg("[FBM] buscar streaming:", nombre, fecha_ddmmyyyy)

    s = _ssl_connect("v2/busqueda.ashx", body_str)
    id_found = None
    last_id = None
    buf = b""
    headers_done = False

    try:
        while True:
            try:
                chunk = s.read(512)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            _capturar_en_vivo(buf)

            if not headers_done:
                idx = buf.find(b"\r\n\r\n")
                if idx >= 0:
                    buf = buf[idx+4:]
                    headers_done = True
                else:
                    if len(buf) > 256:
                        buf = buf[-300:]
                    continue

            off = 0
            while True:
                ii = buf.find(id_prefix, off)
                if ii < 0:
                    break
                start = ii + len(id_prefix)
                end = buf.find(b'"', start)
                if end > start:
                    last_id = buf[start:end].decode()
                    off = end
                else:
                    break

            if notif_b:
                # IdPartido va justo antes de IdPartidoNotificacion en cada registro
                ni = buf.find(notif_b)
                if ni >= 0:
                    ii = buf.rfind(id_prefix, 0, ni)
                    if ii >= 0:
                        st = ii + len(id_prefix)
                        en = buf.find(b'"', st)
                        if 0 < en < ni:
                            last_id = buf[st:en].decode()
                    id_found = last_id
                    _dbg("[FBM] IdPartido por notif:", (id_found or "")[:20])
                    break
                if len(buf) > 600:
                    buf = buf[-600:]
                gc.collect()
                continue

            fi = buf.find(fecha_b)
            if fi >= 0:
                window_after = buf[fi:min(len(buf), fi+350)]
                if cancel_b not in window_after:
                    if last_id:
                        id_found = last_id
                        pass  # nombres y hora capturados en _capturar_en_vivo
                        _dbg("[FBM] IdPartido:", id_found[:20], "...")
                        break
                buf = buf[fi + len(fecha_b):]
                last_id = None
                continue

            if len(buf) > 100:
                buf = buf[-300:]
            gc.collect()

    finally:
        try: s.close()
        except: pass
        del buf; gc.collect()

    return id_found, _last_local, _last_visit


# ---------- jugada a jugada ----------
_TIPOS = {"CANASTA-1P": "+1", "CANASTA-2P": "+2", "CANASTA-3P": "+3", "FALTA-COMETIDA": "F"}
_NEUTRAS = ("CAMBIO-JUGADOR-ENTRA", "CAMBIO-JUGADOR-SALE", "TIEMPO-MUERTO-SOLICITADO")
# acciones tras las que el reloj esta parado (hasta la siguiente accion)
_PARAN = ("FALTA-COMETIDA", "TIEMPO-MUERTO-SOLICITADO", "CAMBIO-JUGADOR-ENTRA",
          "CAMBIO-JUGADOR-SALE")
MAX_ACCIONES = 25     # acciones del historial a revisar buscando la ultima canasta o falta
_INI_JUG = b'{"idequipo":'
_INI_ACC = b'{"autoincremental_id":'


def _int_c(buf, key_b):
    """Entero tras key_b, solo si ya ha llegado el caracter que lo termina."""
    ki = buf.find(key_b)
    if ki < 0:
        return None
    s = e = ki + len(key_b)
    if e < len(buf) and buf[e] == 45:      # '-'
        e += 1
    while e < len(buf) and 48 <= buf[e] <= 57:
        e += 1
    if e >= len(buf) or e == s:
        return None
    try:
        return int(buf[s:e])
    except Exception:
        return None


def _str_c(buf, key_b):
    """Cadena tras key_b (que acaba en comilla), admite cadena vacia."""
    ki = buf.find(key_b)
    if ki < 0:
        return None
    s = ki + len(key_b)
    e = buf.find(b'"', s)
    if e < 0:
        return None
    return buf[s:e].decode()


class _Lector:
    """Lee por trozos la respuesta de obtenerPartido: tanteo y estado, jugadores en
    pista (equipo+dorsal -> nombre, faltas) y la ultima canasta o falta del historial,
    que viene de la accion mas reciente a la mas antigua. Para en cuanto la tiene."""
    def __init__(self):
        self.buf = b""
        self.f = {}
        self.jug = {}
        self.periodo = None
        self.tiempo = None
        self.jugada = None
        self.n_acc = 0
        self.descanso = None   # True si lo ultimo (salvo cambios/tiempos muertos) es FINAL-PERIODO
        self.periodo_fin = None
        self.tipo0 = ""        # tipo y hora real de la accion mas reciente
        self.hora0 = None
        self.error = None
        self.fin = False

    def feed(self, chunk):
        b = self.buf + chunk
        if b'"resultado":"error"' in b:
            v = _str_c(b, b'"error":"')
            if v or len(b) > 400:
                self.error = v or "error"
                return True
        for k, fn in ((b'"tanteo_local":', _int_c), (b'"tanteo_visitante":', _int_c),
                      (b'"idlocal":', _int_c), (b'"estado_partido":"', _str_c),
                      (b'"numperiodos":', _int_c), (b'"duracion_periodo_normal_mm":', _int_c),
                      (b'"duracion_periodo_extra_mm":', _int_c)):
            if k not in self.f:
                v = fn(b, k)
                if v is not None:
                    self.f[k] = v
        # jugadores en pista: objetos sin llaves anidadas
        while True:
            i = b.find(_INI_JUG)
            if i < 0:
                break
            j = b.find(b'}', i)
            if j < 0:
                break
            o = b[i:j] + b','
            eq = _int_c(o, b'"idequipo":')
            d = _str_c(o, b'"dorsal":"')
            if eq is not None and d is not None:
                self.jug[(eq, d)] = (_str_c(o, b'"nombre":"') or "", _int_c(o, b'"faltas":'))
            b = b[j + 1:]
        # historial: los campos que interesan van antes de informacion_adicional
        while not self.fin:
            i = b.find(_INI_ACC)
            if i < 0:
                break
            j = b.find(b'"informacion_adicional"', i)
            if j < 0:
                break
            o = b[i:j]
            b = b[j:]
            self.n_acc += 1
            if self.periodo is None:
                self.periodo = _int_c(o, b'"numero_periodo":')
                self.tiempo = _str_c(o, b'"tiempo_partido":"')
                self.tipo0 = _str_c(o, b'"accion_tipo":"') or ""
                self.hora0 = _str_c(o, b'"hora_dia":"')
            if b'"eliminado":"True"' in o:
                continue
            tipo = _str_c(o, b'"accion_tipo":"')
            if self.descanso is None:
                if tipo == "FINAL-PERIODO":
                    self.descanso = True
                    self.periodo_fin = _int_c(o, b'"numero_periodo":')
                elif tipo not in _NEUTRAS:
                    self.descanso = False
            if tipo in _TIPOS:
                self.jugada = (tipo, _int_c(o, b'"equipo_id":'), _str_c(o, b'"dorsal":"') or "",
                               _int_c(o, b'"autoincremental_id":'))
                self.fin = True
            elif self.n_acc >= MAX_ACCIONES:
                self.fin = True
        if b'"EnVivoJugadoresOTT"' in b:      # se acabo el historial
            self.fin = True
        if not self.fin:
            k = max(b.rfind(_INI_JUG), b.rfind(_INI_ACC))
            if k >= 0:
                b = b[k:]                      # objeto a medias: guardarlo entero
            elif len(b) > 300:
                b = b[-120:]
        self.buf = b
        return self.fin


def _nombre_corto(nom):
    """'PEREZ AGUILERA, RAUL' -> 'RAUL'; sin coma, la primera palabra."""
    nom = _limpia(nom or "")
    if "," in nom:
        nom = nom.split(",", 1)[1]
    p = nom.split()
    return p[0].upper() if p else ""


def texto_jugada(L):
    """('+3 LUIS #9', equipo_id) o None."""
    if not L.jugada:
        return None
    tipo, eq, d, _id = L.jugada
    nom, faltas = L.jug.get((eq, d), ("", None))
    pre = _TIPOS[tipo]
    if pre == "F" and faltas:
        pre = "F" + str(faltas)
    n = _nombre_corto(nom)
    return (pre + " " + (n + " " if n else "") + "#" + d, eq)


def get_marcador(id_partido):
    """Obtiene marcador y ultima jugada en streaming, sin acumular la respuesta."""
    global _sid, _key
    _dbg("[FBM] get_marcador id:", id_partido[:20], "...")
    gc.collect()
    if not _sid:
        _registrar()
    gc.collect()

    for intento in range(2):
        body_str = _urlencode({"id_dispositivo": _sid, "key": _key,
                               "accion": "obtenerPartido", "id_partido": id_partido})
        s = _ssl_connect("v2/envivo/partido.ashx", body_str)
        L = _Lector()
        cab = b""
        try:
            while True:
                try:
                    chunk = s.read(256)
                except Exception:
                    break
                if not chunk:
                    break
                if cab is not None:
                    cab += chunk
                    idx = cab.find(b"\r\n\r\n")
                    if idx < 0:
                        if len(cab) > 300:
                            cab = cab[-150:]
                        continue
                    chunk = cab[idx + 4:]
                    cab = None
                if L.feed(chunk):
                    break
        finally:
            try: s.close()
            except: pass
            gc.collect()

        if L.error is not None:
            _dbg("[FBM] resultado=error:", L.error)
            err_low = L.error.lower()
            if intento == 0 and ("valido" in err_low or "invalid" in err_low):
                _sid = None; _key = None
                _registrar()
                continue
            return None

        rl = L.f.get(b'"tanteo_local":') or 0
        rv = L.f.get(b'"tanteo_visitante":') or 0
        estado = L.f.get(b'"estado_partido":"') or ""
        n = L.periodo or 0
        descanso = bool(L.descanso and L.periodo_fin)
        if descanso:
            # cuarto terminado: se muestra el siguiente, con el reloj parado al tiempo completo
            n = L.periodo_fin + 1
            npr = L.f.get(b'"numperiodos":') or 4
            mm = (L.f.get(b'"duracion_periodo_normal_mm":') or 10) if n <= npr else \
                 (L.f.get(b'"duracion_periodo_extra_mm":') or 5)
            L.tiempo = "00:%02d:00" % mm
        cuarto = _CUARTOS.get(n, "Q{}".format(n)) if n else "Q1"
        t_raw = L.tiempo or ""
        tiempo = ""
        if t_raw and ":" in t_raw:
            partes = t_raw.split(":")
            if len(partes) >= 3:
                tiempo = partes[1] + ":" + partes[2].split(".")[0]
            elif len(partes) == 2:
                tiempo = partes[0] + ":" + partes[1].split(".")[0]
        t0 = L.tipo0
        parado = t0 in _PARAN or ("TIRO" in t0 and "LIBRE" in t0)
        if t0.startswith("CANASTA-") and t0 != "CANASTA-1P" and n >= (L.f.get(b'"numperiodos":') or 4):
            # FIBA: en los 2 ultimos minutos del ultimo cuarto y prorrogas la canasta para el reloj
            try:
                mm, ss = tiempo.split(":")
                if int(mm) * 60 + int(ss) <= 120:
                    parado = True
            except Exception:
                pass
        jg = texto_jugada(L)
        jugada = None
        if jg:
            # id: autoincremental_id de la accion, para no repetir la misma jugada
            jugada = {"txt": jg[0], "local": jg[1] == L.f.get(b'"idlocal":'), "id": L.jugada[3]}
        _dbg("[FBM] {}-{} {} {} | {} | {}".format(rl, rv, cuarto, tiempo, estado, jugada))
        hora_acc = L.hora0
        del L
        gc.collect()
        return {"rl": rl, "rv": rv, "cuarto": cuarto, "tiempo": tiempo,
                "estado": estado, "vivo": estado not in ("FINALIZADO", ""),
                "jugada": jugada, "descanso": descanso, "parado": parado, "hora_acc": hora_acc}

    return None
