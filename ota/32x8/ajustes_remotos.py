# Ajustes de esta pantalla que manda el servidor propio: GET <relay>/ajustes.json?k=<clave>
#   {"v": "<huella>", "brillo": 0-100, "brillo_marcador": 0-100, "wifis": "<cifrado>"}
# Solo se aplican los campos de esta lista; lo demas se ignora. Se guardan en
# ajustes_remotos.json y nunca se tocan config.json ni my_shared.py.
# Las WiFis van cifradas (AES-256-CBC) con el secreto de la placa ("secreto" en relay.json,
# 64 hex), que se le da por la red local o el USB y nunca viaja por internet:
#   base64(iv[16] + cifrado + sha256(kmac + sha256(kmac + iv + cifrado))[:16]),
#   kmac = sha256(secreto + b"mac"); dentro, JSON [{"ssid": ..., "password": ...}, ...]
# Las WiFis se suman a las de config.json (nunca las quitan); sirven en el siguiente arranque.
import json
import gc

FICH = "ajustes_remotos.json"


def leer():
    try:
        with open(FICH) as f:
            return json.load(f)
    except Exception:
        return {}


def _relay():
    try:
        with open("relay.json") as f:
            d = json.load(f)
        if d.get("clave"):
            return d.get("url") or "http://34.30.243.27", d["clave"], d.get("secreto", "")
    except Exception:
        pass
    return None


def _descifrar(texto, secreto):
    import ubinascii
    import hashlib
    import cryptolib
    raw = ubinascii.a2b_base64(texto)
    clave = ubinascii.unhexlify(secreto)
    iv, ct, tag = raw[:16], raw[16:-16], raw[-16:]
    kmac = hashlib.sha256(clave + b"mac").digest()
    if hashlib.sha256(kmac + hashlib.sha256(kmac + iv + ct).digest()).digest()[:16] != tag:
        raise ValueError("firma")
    pt = cryptolib.aes(clave, 2, iv).decrypt(ct)
    return json.loads(pt[:-pt[-1]])


def bajar():
    """Baja los ajustes; si han cambiado los guarda y devuelve el dict, si no None."""
    r = _relay()
    if not r:
        return None
    gc.collect()
    try:
        import requests
        resp = requests.get(r[0] + "/ajustes.json?k=" + r[1])
        try:
            if resp.status_code != 200:
                return None
            d = json.loads(resp.text)
        finally:
            resp.close()
    except Exception as e:
        print("[AJUSTES] fallo:", e)
        return None
    if d.get("v") == leer().get("v"):
        return None
    nuevo = {"v": d.get("v")}
    for k in ("brillo", "brillo_marcador"):
        try:
            nuevo[k] = max(1, min(100, int(d[k])))
        except Exception:
            pass
    if d.get("wifis") and r[2]:
        try:
            nuevo["wifis"] = [{"ssid": str(w["ssid"]), "password": str(w.get("password", ""))}
                              for w in _descifrar(d["wifis"], r[2]) if w.get("ssid")][:8]
        except Exception as e:
            print("[AJUSTES] wifis:", e)
    with open(FICH, "w") as f:
        json.dump(nuevo, f)
    print("[AJUSTES] nuevos:", [k for k in nuevo if k != "v"])
    gc.collect()
    return nuevo


def brillo(marcador=False):
    """Brillo mandado (0-1) o None."""
    d = leer()
    b = d.get("brillo_marcador") if marcador else None
    b = b or d.get("brillo")
    return b / 100.0 if b else None


def wifis():
    return leer().get("wifis", [])
