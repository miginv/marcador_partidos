# Reloj de posesion. La Raspberry de la consola MONDO manda por UDP (puerto 4210):
#   "POS R <reloj>"          el reloj del partido esta en marcha (cada trama de la MONDO)
#   "POS S <atras> <reloj>"  el reloj se ha parado hace <atras> decimas
#   "POS H <reloj>"          sigue conectada, reloj parado (cada segundo)
#   "POS 24" / "POS 14"      reseteo de la posesion
#   "POS OFF"                fin: la pantalla vuelve a su modo normal
#   "POS M"                  cambia la vista (se guarda): 1 = posesion grande en 16x16,
#                            2 = dos lineas, arriba el reloj del partido y abajo la posesion
# Cada linea puede llevar al final " #<n>" (numero de secuencia): en modo pabellon llega la
# misma linea por WiFi y por Bluetooth y solo vale la primera copia (linea()).
# <reloj> = decimas que quedan en el reloj del partido (-1 si no se sabe). La placa lleva la
# cuenta atras: corre mientras llegan "R" y se congela con "S" (o si deja de recibir "R").
# Si el reloj del partido tiene menos tiempo que la posesion, la posesion se apaga (FIBA).
import time
import pantalla16
import fuente16

COLOR = (255, 0, 0)
AMBAR = (255, 200, 0)   # reloj del partido (como en el marcador)
VISTA_FICHERO = "vista16.txt"


def _leer_vista():
    try:
        with open(VISTA_FICHERO) as f:
            return 2 if f.read().strip() == "2" else 1
    except OSError:
        return 1
ACTIVO_MS = 5000        # sin nada de la Raspberry en 5 s se sale del modo posesion
SIN_R_MS = 1500         # en marcha y sin "R" en 1,5 s: se congela (Raspberry caida)
RELOJ_INICIAL = 7200    # reloj del partido hasta que llegue el de verdad: 12:00 (en decimas)
SEQ_REINICIO_MS = 3000  # sin nada en 3 s se acepta cualquier secuencia (emisor reiniciado)


class Posesion:
    def __init__(self):
        self.ms = 24000
        self.corre = False
        self.t_ref = 0
        self.t_msg = None
        self.t_r = 0
        self.reloj = RELOJ_INICIAL
        self.pintado = None
        self.seq = None
        self.t_seq = 0
        self.vista = _leer_vista()

    def linea(self, txt):
        """Linea de WiFi o Bluetooth: descarta las copias repetidas (" #n") y la procesa."""
        if " #" in txt:
            txt, _, n = txt.rpartition(" #")
            try:
                n = int(n) & 0xFFFF
            except ValueError:
                n = None
            if n is not None:
                ahora = time.ticks_ms()
                if (self.seq is not None and time.ticks_diff(ahora, self.t_seq) < SEQ_REINICIO_MS
                        and not 0 < (n - self.seq) & 0xFFFF < 0x8000):
                    return True               # repetida o vieja
                self.seq, self.t_seq = n, ahora
        return self.mensaje(txt)

    def activo(self):
        return self.t_msg is not None and time.ticks_diff(time.ticks_ms(), self.t_msg) < ACTIVO_MS

    def _congelar(self, en_ticks):
        if self.corre:
            self.ms = max(0, self.ms - time.ticks_diff(en_ticks, self.t_ref))
            self.corre = False

    def mensaje(self, txt):
        """Procesa una linea "POS ...". Devuelve True si era de posesion."""
        p = txt.split()
        if not p or p[0] != "POS":
            return False
        ahora = time.ticks_ms()
        if len(p) < 2:
            return True
        c = p[1]
        if c == "OFF":
            self._congelar(ahora)
            self.t_msg = None
            self.pintado = None
            return True
        self.t_msg = ahora
        if c in ("24", "14"):
            if self.corre:
                self.t_ref = ahora
            self.ms = int(c) * 1000
        elif c == "R":
            self._reloj(p, 2)
            if not self.corre:
                self.corre = True
                self.t_ref = ahora
            self.t_r = ahora
        elif c == "S":
            atras = 0
            try:
                atras = int(p[2]) * 100
            except (IndexError, ValueError):
                pass
            self._reloj(p, 3)
            if self.corre:
                self._congelar(time.ticks_add(ahora, -atras))
        elif c == "H":
            self._reloj(p, 2)
        elif c == "M":
            self.vista = 1 if self.vista == 2 else 2
            self.pintado = None
            try:
                with open(VISTA_FICHERO, "w") as f:
                    f.write(str(self.vista))
            except OSError:
                pass
        return True

    def _reloj(self, p, i):
        try:
            self.reloj = int(p[i])
        except (IndexError, ValueError):
            pass

    def valor(self):
        ahora = time.ticks_ms()
        if self.corre and time.ticks_diff(ahora, self.t_r) > SIN_R_MS:
            self._congelar(time.ticks_add(self.t_r, 1000))
        if self.corre:
            # la MONDO manda una trama por segundo (cada 0,1 s en el ultimo minuto): sin la
            # siguiente no se adelanta mas de eso, asi al parar casi no hay que corregir
            tope = time.ticks_diff(self.t_r, self.t_ref) + (1050 if self.reloj >= 600 or self.reloj < 0 else 150)
            return max(0, self.ms - min(time.ticks_diff(ahora, self.t_ref), tope))
        return self.ms

    def texto(self):
        v = self.valor()
        if 0 <= self.reloj and self.reloj * 100 < v:
            return ""                         # queda menos de partido que de posesion
        d = v // 100                          # decimas
        if d >= 100:
            return str((d + 9) // 10)         # 24..10 redondeando hacia arriba
        return "%d.%d" % (d // 10, d % 10)

    def pintar(self, forzar=False):
        t = self.texto()
        r = self.reloj if self.vista == 2 else None
        clave = (self.vista, t, r)
        if clave == self.pintado and not forzar:
            return
        self.pintado = clave
        pantalla16.limpiar()
        if self.vista == 2:
            # arriba (filas 0-6) el reloj del partido tal como lo manda la MONDO; abajo
            # (filas 9-15) la posesion
            if r is not None and r >= 0:
                cols = fuente16.reloj7((r + 0.05) / 10)   # +0,05: floats de 32 bits
                pantalla16.columnas(cols, AMBAR, (16 - len(cols)) // 2, 0)
            if t:
                cols = fuente16.posesion7(t)
                pantalla16.columnas(cols, COLOR, (16 - len(cols)) // 2, 9)
        elif t:
            cols = fuente16.texto(t)
            pantalla16.columnas(cols, COLOR, (16 - len(cols)) // 2, 0)
        pantalla16.mostrar()
