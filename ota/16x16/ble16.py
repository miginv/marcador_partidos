# Segundo canal para la posesion: Bluetooth LE (la ESP32-C3 no tiene Bluetooth clasico).
# La placa anuncia el servicio UART de Nordic con el nombre "pos16-<4 ultimos de la MAC>"; el
# emisor (Mac o Raspberry) escribe en la caracteristica RX las mismas lineas que manda por
# UDP ("POS R 1234 #57"). main16 las procesa igual que las del WiFi y descarta las repetidas
# por el numero de secuencia (#n), asi da igual cual de los dos canales llegue antes.
import bluetooth

SERVICIO = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
RX = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
_CONECTA, _DESCONECTA, _ESCRIBE = 1, 2, 3
MAX_LINEAS = 20


def _anuncio(tipo, dato):
    return bytes((len(dato) + 1, tipo)) + dato


class Ble:
    def __init__(self, nombre):
        self.nombre = nombre
        self.lineas = []
        self.conectados = set()
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        try:
            self.ble.config(gap_name=nombre)
        except Exception:
            pass
        ((self.rx,),) = self.ble.gatts_register_services(
            ((SERVICIO, ((RX, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),)),))
        self.ble.gatts_set_buffer(self.rx, 128, True)
        self.ble.irq(self._irq)
        # el UUID de 128 bits en el anuncio y el nombre en la respuesta al escaneo (no caben juntos)
        self.adv = _anuncio(0x01, b"\x06") + _anuncio(0x07, bytes(SERVICIO))   # ya va en little endian
        self.resp = _anuncio(0x09, nombre.encode())
        self._anunciar()

    def _anunciar(self):
        try:
            self.ble.gap_advertise(100000, adv_data=self.adv, resp_data=self.resp, connectable=True)
        except Exception as e:
            print("[BLE] anuncio", e)

    def _irq(self, ev, data):
        if ev == _CONECTA:
            self.conectados.add(data[0])
        elif ev == _DESCONECTA:
            self.conectados.discard(data[0])
            self._anunciar()
        elif ev == _ESCRIBE and data[1] == self.rx:
            if len(self.lineas) < MAX_LINEAS:
                self.lineas.append(bytes(self.ble.gatts_read(self.rx)))

    def leer(self):
        """Lineas recibidas desde la ultima llamada."""
        if not self.lineas:
            return ()
        l, self.lineas = self.lineas, []
        return l
