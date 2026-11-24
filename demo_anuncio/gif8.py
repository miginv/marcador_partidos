# Lector de GIF 8x8 (iconos LaMetric), copiado de my_display de la Awtrix

class GifPlayer:
    def __init__(self, filename):
        self.f = open(filename, 'rb')
        self.f.seek(10)
        packed = ord(self.f.read(1))
        self.gct_size = 3 * (2 << (packed & 0x07)) if packed & 0x80 else 0
        self.f.seek(13)
        self.gct = self.f.read(self.gct_size)
        self.start_pos = 13 + self.gct_size
        self.transparent_idx = -1  # se actualiza con cada GCE

    def decompress_lzw(self, min_code_size, data):
        clear_code = 1 << min_code_size
        end_code = clear_code + 1
        code_size = min_code_size + 1
        result = []
        table = [[i] for i in range(clear_code + 2)]
        bit_buf = bit_count = pos = 0

        def get_code():
            nonlocal bit_buf, bit_count, pos
            while bit_count < code_size:
                if pos >= len(data):
                    return end_code
                bit_buf |= data[pos] << bit_count
                pos += 1
                bit_count += 8
            code = bit_buf & ((1 << code_size) - 1)
            bit_buf >>= code_size
            bit_count -= code_size
            return code

        prev_code = None
        while True:
            code = get_code()
            if code == end_code:
                break
            if code == clear_code:
                table = [[i] for i in range(clear_code + 2)]
                code_size = min_code_size + 1
                prev_code = None
                continue
            if code < len(table):
                val = table[code]
                if prev_code is not None:
                    table.append(table[prev_code] + [val[0]])
            else:
                val = table[prev_code] + [table[prev_code][0]]
                table.append(val)
            result.extend(val)
            prev_code = code
            if len(table) == (1 << code_size) and code_size < 12:
                code_size += 1
        return result

    def get_next_frame(self):
        """Busca el siguiente frame de imagen y devuelve indices y su paleta específica"""
        max_iters = 5000
        iters = 0
        while iters < max_iters:
            iters += 1
            block = self.f.read(1)
            if not block or block == b'\x3b':
                self.f.seek(self.start_pos)
                continue
            if block == b'\x21':
                ext = self.f.read(1)
                if ext == b'\xf9':  # Graphic Control Extension
                    sz = self.f.read(1)
                    if sz and ord(sz) >= 4:
                        gce = self.f.read(ord(sz))
                        if gce and (gce[0] & 0x01):  # transparent flag
                            self.transparent_idx = gce[3]
                        else:
                            self.transparent_idx = -1
                        self.f.read(1)  # block terminator
                    continue
                sub_iters = 0
                while sub_iters < 256:
                    sub_iters += 1
                    size_b = self.f.read(1)
                    if not size_b or ord(size_b) == 0:
                        break
                    self.f.read(ord(size_b))
                continue
            if block == b'\x2c':
                self.f.read(8)
                packed = ord(self.f.read(1))
                palette = self.f.read(3 * (2 << (packed & 0x07))) if packed & 0x80 else self.gct
                lzw_min = ord(self.f.read(1))
                data = b''
                sub_iters = 0
                while sub_iters < 4096:
                    sub_iters += 1
                    s = self.f.read(1)
                    if not s or ord(s) == 0:
                        break
                    data += self.f.read(ord(s))
                return self.decompress_lzw(lzw_min, data), palette
        # Si se supera el límite, reiniciar y devolver vacío
        self.f.seek(self.start_pos)
        return [], b''
