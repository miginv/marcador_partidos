# Lector de GIF animados para la 16x16: iconos de LaMetric (8x8) y propios de hasta 16x16.
# Va componiendo cada fotograma sobre un lienzo RGB (los fotogramas parciales con su
# posicion, transparencia y "disposal" basico), asi valen GIF de cualquier origen.
import time


class Gif:
    def __init__(self, ruta):
        self.f = open(ruta, "rb")
        cab = self.f.read(13)
        if cab[:3] != b"GIF":
            self.f.close()
            raise ValueError("no es GIF")
        self.w = cab[6] | cab[7] << 8
        self.h = cab[8] | cab[9] << 8
        if self.w > 32 or self.h > 32:
            self.f.close()
            raise ValueError("GIF demasiado grande %dx%d" % (self.w, self.h))
        packed = cab[10]
        self.gct = self.f.read(3 * (2 << (packed & 7))) if packed & 0x80 else b""
        self.inicio = self.f.tell()
        self.lienzo = bytearray(self.w * self.h * 3)
        self.transp = -1
        self.retardo = 100
        self.disposal = 0
        self._prev_rect = None
        self.t = 0
        self.listo = False

    def cerrar(self):
        try:
            self.f.close()
        except Exception:
            pass

    @staticmethod
    def _lzw(min_code, data, npix):
        clear = 1 << min_code
        fin = clear + 1
        size = min_code + 1
        out = bytearray()
        tabla = [bytes([i]) for i in range(clear)] + [b"", b""]
        buf = nb = pos = 0
        prev = None
        n = len(data)
        while len(out) < npix:
            while nb < size:
                if pos >= n:
                    return out
                buf |= data[pos] << nb
                pos += 1
                nb += 8
            code = buf & ((1 << size) - 1)
            buf >>= size
            nb -= size
            if code == clear:
                tabla = tabla[:clear + 2]
                size = min_code + 1
                prev = None
                continue
            if code == fin:
                break
            if code < len(tabla):
                val = tabla[code]
                if prev is not None:
                    tabla.append(prev + val[:1])
            elif prev is not None:
                val = prev + prev[:1]
                tabla.append(val)
            else:
                break
            out += val
            prev = val
            if len(tabla) == (1 << size) and size < 12:
                size += 1
        return out

    def _saltar_bloques(self):
        while True:
            s = self.f.read(1)
            if not s or s[0] == 0:
                return
            self.f.read(s[0])

    def siguiente(self):
        """Avanza un fotograma (vuelve al principio al acabar). True si ha cambiado."""
        for _ in range(200):
            b = self.f.read(1)
            if not b or b == b"\x3b":
                self.f.seek(self.inicio)
                continue
            if b == b"\x21":
                ext = self.f.read(1)
                if ext == b"\xf9":
                    sz = self.f.read(1)[0]
                    g = self.f.read(sz)
                    self.f.read(1)
                    self.disposal = (g[0] >> 2) & 7
                    self.retardo = max(40, (g[1] | g[2] << 8) * 10) if sz >= 3 else 100
                    self.transp = g[3] if g[0] & 1 and sz >= 4 else -1
                else:
                    self._saltar_bloques()
                continue
            if b == b"\x2c":
                d = self.f.read(9)
                fx, fy = d[0] | d[1] << 8, d[2] | d[3] << 8
                fw, fh = d[4] | d[5] << 8, d[6] | d[7] << 8
                packed = d[8]
                pal = self.f.read(3 * (2 << (packed & 7))) if packed & 0x80 else self.gct
                entrelazado = packed & 0x40
                min_code = self.f.read(1)[0]
                datos = bytearray()
                while True:
                    s = self.f.read(1)
                    if not s or s[0] == 0:
                        break
                    datos += self.f.read(s[0])
                if self._prev_rect:                 # disposal 2 del fotograma anterior
                    px, py, pw, ph = self._prev_rect
                    for yy in range(py, min(py + ph, self.h)):
                        for xx in range(px, min(px + pw, self.w)):
                            k = (yy * self.w + xx) * 3
                            self.lienzo[k] = self.lienzo[k + 1] = self.lienzo[k + 2] = 0
                    self._prev_rect = None
                idx = self._lzw(min_code, datos, fw * fh)
                filas = list(range(fh))
                if entrelazado:
                    filas = list(range(0, fh, 8)) + list(range(4, fh, 8)) + \
                        list(range(2, fh, 4)) + list(range(1, fh, 2))
                i = 0
                for fila in filas:
                    yy = fy + fila
                    for xx in range(fx, fx + fw):
                        if i >= len(idx):
                            break
                        c = idx[i]
                        i += 1
                        if c == self.transp or xx >= self.w or yy >= self.h:
                            continue
                        k = (yy * self.w + xx) * 3
                        p = c * 3
                        if p + 2 < len(pal):
                            self.lienzo[k] = pal[p]
                            self.lienzo[k + 1] = pal[p + 1]
                            self.lienzo[k + 2] = pal[p + 2]
                if self.disposal == 2:
                    self._prev_rect = (fx, fy, fw, fh)
                self.listo = True
                return True
            return False
        return False

    def tick(self):
        """Avanza si ya toca segun el retardo del GIF."""
        ahora = time.ticks_ms()
        if not self.listo or time.ticks_diff(ahora, self.t) >= self.retardo:
            self.t = ahora
            self.siguiente()

    def color(self, x, y):
        k = (y * self.w + x) * 3
        return self.lienzo[k], self.lienzo[k + 1], self.lienzo[k + 2]
