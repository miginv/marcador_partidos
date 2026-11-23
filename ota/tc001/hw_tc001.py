# Hardware del Ulanzi TC001 (ESP32-D0WD, pines sacados del firmware Awtrix 3):
#  matriz 32x8 WS2812 en GPIO32, filas en zigzag (fila 0 izq->der, fila 1 der->izq...)
#  zumbador GPIO15, botones izq 26 / centro 27 / der 14 (activos a nivel bajo)
#  LDR (luz) GPIO35, bateria GPIO34 (divisor), I2C SDA 21 / SCL 22 (SHT31 0x44 o HTU21 0x40)
import machine
import time

PIN_DATA = 32
PIN_SCK = 33          # el SPI de los LED necesita reloj; GPIO33 no va conectado a nada
TOTAL_LEDS = 256
WIDTH = 32

# El zumbador pita si su pin queda flotando: lo primero, a nivel bajo
_buzz = machine.Pin(15, machine.Pin.OUT, value=0)

# Arranca a brillo minimo (de noche no deslumbra al reiniciar); el brillo automatico de
# ajustes_tc001 lo sube segun la luz en cuanto arranca el servidor. Si el automatico esta
# desactivado en ajustes_tc001.json se deja el brillo de my_shared.
try:
    import json as _json
    import my_shared as _ms
    try:
        with open("ajustes_tc001.json") as _f:
            _auto = _json.load(_f).get("brillo", {}).get("auto", True)
    except Exception:
        _auto = True
    if _auto:
        _ms.BRIGHTNESS = 1 / 255
except Exception as _e:
    print("[HW] brillo inicial:", _e)


def led_index(x, y):
    if y & 1:
        return y * 32 + 31 - x
    return y * 32 + x



# --- botones ---
BOTONES = {"izq": 26, "centro": 27, "der": 14}
_btn = {k: machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_UP) for k, p in BOTONES.items()}


def botones():
    """{'izq': True/False, ...} True = pulsado."""
    return {k: p.value() == 0 for k, p in _btn.items()}


# --- luz y bateria ---
_ldr = machine.ADC(machine.Pin(35))
_ldr.atten(machine.ADC.ATTN_11DB)
_bat = machine.ADC(machine.Pin(34))
_bat.atten(machine.ADC.ATTN_11DB)
BAT_MIN, BAT_MAX = 475, 665     # lecturas de 10 bits del Awtrix 3 (vacia / llena)


def luz():
    """0..1023 (mas alto = mas luz)."""
    return _ldr.read_u16() >> 6


def bateria():
    """(porcentaje, lectura de 10 bits)."""
    raw = sum(_bat.read_u16() >> 6 for _ in range(8)) // 8
    pct = (raw - BAT_MIN) * 100 // (BAT_MAX - BAT_MIN)
    return max(0, min(100, pct)), raw


# --- temperatura y humedad ---
_i2c = None
_sensor = None


def _init_sensor():
    global _i2c, _sensor
    if _i2c is None:
        _i2c = machine.I2C(0, sda=machine.Pin(21), scl=machine.Pin(22), freq=100000)
        found = _i2c.scan()
        _sensor = "sht31" if 0x44 in found else ("htu21" if 0x40 in found else "")
    return _sensor


def temp_hum():
    """(temperatura C, humedad %) o (None, None) si no hay sensor."""
    try:
        s = _init_sensor()
        if s == "sht31":
            _i2c.writeto(0x44, b"\x24\x00")        # medida unica, repetibilidad alta
            time.sleep_ms(20)
            d = _i2c.readfrom(0x44, 6)
            t = -45 + 175 * ((d[0] << 8) | d[1]) / 65535
            h = 100 * ((d[3] << 8) | d[4]) / 65535
            return round(t, 1), round(h, 1)
        if s == "htu21":
            _i2c.writeto(0x40, b"\xf3")
            time.sleep_ms(60)
            d = _i2c.readfrom(0x40, 3)
            t = -46.85 + 175.72 * (((d[0] << 8) | d[1]) & 0xFFFC) / 65536
            _i2c.writeto(0x40, b"\xf5")
            time.sleep_ms(20)
            d = _i2c.readfrom(0x40, 3)
            h = -6 + 125 * (((d[0] << 8) | d[1]) & 0xFFFC) / 65536
            return round(t, 1), round(h, 1)
    except Exception as e:
        print("[HW] sensor:", e)
    return None, None


def stats():
    t, h = temp_hum()
    pct, raw = bateria()
    return {"temp": t, "hum": h, "lux": luz(), "bat": pct, "bat_raw": raw,
            "sensor": _sensor or "", "botones": botones()}


def pitido(ms=80, freq=2000):
    pwm = machine.PWM(_buzz, freq=freq, duty_u16=32768)
    time.sleep_ms(ms)
    pwm.deinit()
    _buzz.init(machine.Pin.OUT, value=0)
