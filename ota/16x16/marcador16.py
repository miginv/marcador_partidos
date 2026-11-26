# Modo marcador de la 16x16: partido de la lista (partidos.json) leido del servidor propio
# (relay, http con la clave de relay.json), sin ciclos: todo a la vez en pantalla.
#   filas 0-6   tanteo local pegado a la izquierda y visitante pegado a la derecha, cada uno
#               con el color de su equipo (Serracines en azul, el rival en rojo)
#   filas 8-14  tiempo del cuarto centrado (M:SS), en ambar
#   fila 15     un guion por periodo: verde los jugados y el que se juega, rojo los que faltan
# Antes de empezar: hora de inicio. Al acabar: "FIN" un minuto y al siguiente partido.
import gc
import json
import time
import fbm_http
import fuente16
import pantalla16
import sistema16

ANTES_MIN = 15        # el marcador se activa 15 min antes del inicio
MAX_MIN = 150         # pasado esto el partido se da por acabado
POLL_MS = 5000        # sondeo al servidor propio (es nuestro, no la FBM)
LISTA_SEG = 15 * 60
FIN_SEG = 60
NOMBRES_MS = 3000
ESTADO_FILE = "estado.json"
PARTIDOS_FILE = "partidos.json"
NUESTROS = ("SERRACINES", "COSLADA")
ALIASES = {"SERRACINES": "SER", "LARRY": "LAR"}
MINIBASKET = ("benj", "alev", "mini", "premini")
AZUL, ROJO, VERDE = (0, 0, 255), (255, 0, 0), (0, 255, 0)
AMBAR, BLANCO = (255, 200, 0), (255, 255, 255)


def abreviar(nombre):
    nombre = (nombre or "").strip().upper()
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


def _nuestro(nombre):
    nombre = (nombre or "").upper()
    return any(k in nombre for k in NUESTROS)


def digitos(txt, hueco=1, hueco_puntos=1):
    """Columnas (7 px de alto) con los digitos de 3 px del reloj de fuente16."""
    cols = []
    prev = None
    for ch in txt:
        if ch != ":" and ch not in fuente16._P3:
            continue
        if prev is not None:
            cols += [0] * (hueco_puntos if ":" in (ch, prev) else hueco)
        cols += fuente16.DOS_PUNTOS if ch == ":" else fuente16._P3[ch]
        prev = ch
    return cols


def _segundos(t):
    try:
        mm, ss = t.split(":")
        return int(mm) * 60 + int(ss)
    except Exception:
        return None


class Marcador:
    def __init__(self):
        self.url, clave = sistema16.relay()
        fbm_http.URL = self.url
        fbm_http.CLAVE = clave
        self.lista = self._cargar_local()
        self.t_lista = 0
        try:
            with open(ESTADO_FILE) as f:
                self.hechos = json.load(f).get("hechos", [])
        except Exception:
            self.hechos = []
        self.actual = None
        self.d = None            # ultimo /m/<notif>.json
        self.t_poll = None
        self.t_dato = 0          # ticks de cuando se leyo d (para el reloj)
        self.ancla = {"q": None, "api": None, "rem": 0, "t": 0}
        self.fin_t = None
        self.nombres_hasta = None
        self.desc_prev = False
        self.pintado = None

    # ---------- lista de partidos ----------

    def _cargar_local(self):
        try:
            with open(PARTIDOS_FILE) as f:
                return sorted(json.load(f).get("partidos", []), key=lambda p: p.get("ts") or 0)
        except Exception:
            return []

    def bajar_lista(self):
        """partidos.json del servidor propio (cada 15 min)."""
        if not self.url:
            return
        self.t_lista = time.time()
        try:
            d = fbm_http._get("/partidos.json")
            if d and "partidos" in d:
                self.lista = sorted(d["partidos"], key=lambda p: p.get("ts") or 0)
                with open(PARTIDOS_FILE, "w") as f:
                    json.dump(d, f)
                print("[LISTA]", len(self.lista), "partidos")
        except Exception as e:
            print("[LISTA] fallo:", e)
        gc.collect()

    def revisar(self):
        if self.url and time.time() - self.t_lista >= LISTA_SEG:
            self.bajar_lista()

    @staticmethod
    def clave(p):
        return str(p.get("notif") or (p.get("fecha", "") + p.get("hora", "")))

    def _min_desde_inicio(self, p):
        if not sistema16.hora_ok[0] or not p.get("ts"):
            return None
        return (time.time() + sistema16.EPOCH_2000 - p["ts"]) // 60

    def siguiente(self):
        for p in self.lista:
            if self.clave(p) in self.hechos or not p.get("notif"):
                continue
            m = self._min_desde_inicio(p)
            if m is None or m > MAX_MIN:
                continue
            if m < -ANTES_MIN:
                return None             # la lista va por hora: el siguiente aun no toca
            return p
        return None

    def marcar_hecho(self, p):
        k = self.clave(p)
        if k not in self.hechos:
            self.hechos.append(k)
            del self.hechos[:-40]
        try:
            with open(ESTADO_FILE, "w") as f:
                json.dump({"hechos": self.hechos}, f)
        except Exception as e:
            print("[ESTADO]", e)

    def activo(self):
        """Hay partido que seguir (y la placa tiene clave del servidor y hora)."""
        if not self.url:
            return False
        p = self.siguiente()
        if p is None:
            if self.actual is not None:
                self.actual = None
            return False
        if self.clave(p) != self.actual:
            self.actual = self.clave(p)
            self.partido = p
            self.d = None
            self.t_poll = None
            self.fin_t = None
            self.nombres_hasta = time.ticks_add(time.ticks_ms(), NOMBRES_MS)
            self.pintado = None
            nuestro_visit = _nuestro(p.get("visit")) and not _nuestro(p.get("local"))
            self.col_l = ROJO if nuestro_visit else AZUL
            self.col_v = AZUL if nuestro_visit else ROJO
            cat = (p.get("categoria") or "").lower()
            self.nper = 6 if any(c in cat for c in MINIBASKET) else 4
            print("[MARCADOR]", p.get("fecha"), p.get("hora"), p.get("local"), "-", p.get("visit"))
        return True

    # ---------- datos ----------

    def sondear(self):
        ahora = time.ticks_ms()
        if self.t_poll is not None and time.ticks_diff(ahora, self.t_poll) < POLL_MS:
            return
        self.t_poll = ahora
        try:
            d = fbm_http._get("/m/%s.json" % self.partido["notif"])
        except Exception as e:
            print("[MARCADOR] servidor:", e)
            d = None
        gc.collect()
        if d and d.get("m"):
            self.d = d
            self.t_dato = time.ticks_ms()
            m = d["m"]
            if m.get("descanso") and not self.desc_prev:
                self.nombres_hasta = time.ticks_add(time.ticks_ms(), NOMBRES_MS)
            self.desc_prev = bool(m.get("descanso"))
            if m.get("estado") == "FINALIZADO" and self.fin_t is None:
                self.fin_t = time.time()
                print("[MARCADOR] FINALIZADO", m.get("rl"), "-", m.get("rv"))

    def _seg_desde(self, hora):
        if not sistema16.hora_ok[0] or not hora:
            return None
        try:
            h, mi, s = [int(x) for x in hora.split(":")[:3]]
        except Exception:
            return None
        ahora = int(sistema16.ahora_local()) % 86400
        return (ahora - (h * 3600 + mi * 60 + s)) % 86400

    def restante(self, m):
        """Segundos que quedan. La FBM da el tiempo de la ULTIMA ACCION: si esa accion para el
        reloj (falta, tiempo muerto...) o es descanso se queda quieto; si no, baja desde la
        hora real de la accion."""
        s = _segundos(m.get("tiempo") or "")
        if s is None:
            return None
        if m.get("descanso") or m.get("parado"):
            self.ancla["api"] = None
            return s
        a = self.ancla
        now = time.time()
        if a["q"] != m.get("cuarto") or a["api"] != m.get("tiempo"):
            a["q"] = m.get("cuarto")
            a["api"] = m.get("tiempo")
            a["rem"] = s
            a["t"] = now
            dt = self._seg_desde(m.get("hora_acc"))
            if dt is not None and dt < 300:
                a["rem"] = s - dt
        return max(0, a["rem"] - int(now - a["t"]))

    # ---------- pantalla ----------

    def _guiones(self, jugados):
        n = max(self.nper, jugados) if jugados <= 6 else self.nper
        for i in range(n):
            x0 = (i * 16 + n // 2) // n
            x1 = ((i + 1) * 16 + n // 2) // n - 1        # 1 px de separacion
            col = VERDE if i < jugados else ROJO
            c = pantalla16.escala(col)
            for x in range(x0, max(x0 + 1, x1)):
                pantalla16.pixel(x, 15, c)

    def pintar(self):
        m = self.d["m"] if self.d else None
        ahora = time.ticks_ms()
        if self.nombres_hasta is not None and time.ticks_diff(self.nombres_hasta, ahora) > 0:
            clave = ("N",)
            if clave != self.pintado:
                al = abreviar(self.partido.get("local"))
                av = abreviar(self.partido.get("visit"))
                pantalla16.limpiar()
                pantalla16.texto(al, (16 - pantalla16.ancho(al)) // 2, pantalla16.FILA1, self.col_l)
                pantalla16.texto(av, (16 - pantalla16.ancho(av)) // 2, pantalla16.FILA2, self.col_v)
                pantalla16.mostrar()
                self.pintado = clave
            return
        if m is None or (not m.get("rl") and not m.get("rv") and not m.get("tiempo")
                         and m.get("estado") != "FINALIZADO"):
            # espera: hora de inicio (horas arriba, minutos abajo) alternando con los nombres
            if time.ticks_ms() // NOMBRES_MS % 2:
                self.nombres_hasta = time.ticks_add(time.ticks_ms(), NOMBRES_MS)
                return
            hora = (self.d or {}).get("hora") or self.partido.get("hora", "")[:5]
            clave = ("E", hora)
            if clave != self.pintado:
                hh, _, mi = hora.partition(":")
                pantalla16.limpiar()
                for txt, y in ((hh, 0), (mi, 8)):
                    cols = digitos(txt)
                    pantalla16.columnas(cols, VERDE, (16 - len(cols)) // 2, y)
                self._guiones(0)
                pantalla16.mostrar()
                self.pintado = clave
            return
        rl, rv = str(m.get("rl", 0)), str(m.get("rv", 0))
        q = m.get("cuarto") or "Q1"
        try:
            nq = int(q[1:]) if q.startswith("Q") else self.nper
        except ValueError:
            nq = 1
        fin = m.get("estado") == "FINALIZADO"
        if fin:
            reloj = "FIN"
        else:
            r = self.restante(m)
            reloj = "" if r is None else "%d:%02d" % (r // 60, r % 60)
        clave = (rl, rv, reloj, nq, self.col_l)
        if clave == self.pintado:
            return
        self.pintado = clave
        pantalla16.limpiar()
        cl, cv = digitos(rl), digitos(rv)
        pantalla16.columnas(cl, self.col_l, 0, 0)
        pantalla16.columnas(cv, self.col_v, 16 - len(cv), 0)
        if fin:
            pantalla16.texto("FIN", (16 - pantalla16.ancho("FIN")) // 2, pantalla16.FILA2, BLANCO)
            self._guiones(self.nper)
        else:
            cols = digitos(reloj)
            pantalla16.columnas(cols, AMBAR, (16 - len(cols)) // 2, 8)
            self._guiones(nq)
        pantalla16.mostrar()

    def paso(self):
        """Una vuelta del bucle principal en modo marcador."""
        self.sondear()
        if self.fin_t is not None and time.time() - self.fin_t > FIN_SEG:
            self.marcar_hecho(self.partido)
            self.actual = None
            return
        self.pintar()

    def olvidar(self):
        self.pintado = None
