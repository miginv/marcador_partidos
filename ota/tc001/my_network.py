import network
import time
import ntptime
import urequests as requests
import json
from machine import Pin
import sys
#from my_display import draw_centered_text, scroll_text_left
import socket
import urequests
import machine
import re
import ubinascii

sys.path.append('lib')  # Agregar el directorio lib si se necesita

import my_shared

sta = network.WLAN(network.STA_IF)

position_y = 3
#UTC_OFFSET = 3600  # UTC+1 en segundos (ajusta según tu zona horaria)
UTC_OFFSET = 1*3600  # UTC+1 en segundos (ajusta según tu zona horaria)
DST_OFFSET = 3600  # Horario de verano (UTC+2)

def get_ntp_time():
    rtc = machine.RTC()
    current_time = rtc.datetime()
    
    # Si el año es mayor a 2020, asumimos que ya hay una hora válida en el RTC
    if current_time[0] > 2020:
        print("Hora RTC válida, no se realiza nueva petición.")

        print(f"Minture before conversion {current_time[5]}")

        if int(current_time[5]) < 10:
            print("minute lower than 10")
            str_minute = "0"+str(current_time[5])
        else:
            str_minute = str(current_time[5])
            
        if int(current_time[4]) < 10:
            str_hour = "0"+str(current_time[4])
        else:
            str_hour = str(current_time[4])
            
        print(f"Minture after conversion {str_minute}")

        return (
            str(current_time[0] % 100),
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][current_time[3]],
            #str(current_time[4]), # hour
            str_hour,
            #str(current_time[5]), # minute
            str_minute,
            str(current_time[6]),
            str(current_time[2]),
            str(current_time[1])
        )
    
    url = "https://www.timeapi.io/api/Time/current/zone?timeZone=Europe/Madrid"
    
    try:
        print(f"Obteniendo datos de: {url}")
        response = urequests.get(url)
        print(f"Código de estado HTTP: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: Código de estado {response.status_code}")
            response.close()
            return 'desconocido', '00', '00', '00', '00', '00', '00'
        
        try:
            raw_text = response.text
            print(f"Respuesta cruda: {raw_text}")
            data = response.json()
            print(f"Datos JSON parseados: {data}")
        except ValueError:
            print("Error: Respuesta no es un JSON válido")
            response.close()
            return 'desconocido', '00', '00', '00', '00', '00', '00'
        
        response.close()
        
        year = int(data.get("year"))
        month = int(data.get("month"))
        day = int(data.get("day"))
        hour = int(data.get("hour"))
        minute = int(data.get("minute"))
        second = int(data.get("seconds"))
        day_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(data.get("dayOfWeek")) + 1
        print(f"Minture before conversion {minute}")


        if int(minute) < 10:
            print("minute lower than 10")
            str_minute = "0"+str(minute)
        else:
            str_minute = str(minute)
            
        if hour < 10:
            str_hour = "0"+str(hour)
        else:
            str_hour = str(hour)
            
        print(f"Minture after conversion {str_minute}")

        if all(v is not None for v in [year, month, day, hour, minute, second]):
            # Configurar RTC con la nueva hora obtenida
            rtc.datetime((year, month, day, day_of_week, hour, minute, second, 0))
            return (
                str(year % 100), str(day_of_week), str_hour, str_minute,
                str(second), str(day), str(month)
            )
        
    except Exception as e:
        print(f"Error al obtener la hora de Madrid: {e}")
    
    return 'desconocido', '00', '00', '00', '00', '00', '00'


def get_ntp_time2():
    # Lista de servidores NTP para intentar
    ntp_servers = ['pool.ntp.org', 'time.google.com', 'europe.pool.ntp.org']
    
    # Lista de días de la semana
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # Verificar si la hora local ya está establecida
    local_time = time.localtime()
    if local_time[0] > 2000:  # Año válido indica que ya hay hora local
        print("Hora local válida detectada, no se sincroniza con NTP")
        return format_time(local_time, days_of_week, is_summer_time(local_time))

    # Intentar sincronizar con el primer servidor NTP exitoso
    for server in ntp_servers:
        try:
            ntptime.host = server
            ntptime.settime()
            print(f"Sincronización con {server} exitosa")
            
            # Obtener hora local ajustada
            current_time = time.localtime()
            adjusted_time = adjust_time_for_timezone(current_time)
            return format_time(adjusted_time, days_of_week, is_summer_time(adjusted_time))
        except Exception as e:
            print(f"Error al sincronizar con {server}: {e}")

    # Si todos los intentos fallan, devolver valores por defecto
    print("Fallo en todos los servidores NTP, devolviendo valores predeterminados")
    return '00', 'desconocido', '00', '00', '00', '00', '00'

def format_time(local_time, days_of_week, is_summer):
    """Formatea la hora local en valores legibles."""
    year = f"{local_time[0] % 100:02}"  # Los dos últimos dígitos del año
    weekday = days_of_week[local_time[6]]  # Día de la semana
    hours = f"{local_time[3] + (1 if is_summer else 0):02}"
    minutes = f"{local_time[4]:02}"
    seconds = f"{local_time[5]:02}"
    day = f"{local_time[2]}"  # Día sin ceros iniciales
    month = f"{local_time[1]}"  # Mes sin ceros iniciales
    return year, weekday, hours, minutes, seconds, day, month

def adjust_time_for_timezone(local_time):
    """Ajusta la hora local considerando la zona horaria y horario de verano."""
    offset = UTC_OFFSET
    if is_summer_time(local_time):
        offset += DST_OFFSET
        print("Ajuste a horario de verano (UTC+2)")
    return time.localtime(time.mktime(local_time) + offset)


def is_summer_time(utc_time):
    """España DST: UTC+2 desde el último domingo de marzo 01:00 UTC hasta el último domingo de octubre 01:00 UTC."""
    year = utc_time[0]
    month = utc_time[1]
    day = utc_time[2]
    hour = utc_time[3]

    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True

    # Último domingo de marzo/octubre (ambos tienen 31 días)
    wd_31 = time.localtime(time.mktime((year, month, 31, 12, 0, 0, 0, 0)))[6]
    last_sun = 31 - (wd_31 - 6) % 7

    # Transición a las 01:00 UTC (02:00 CET→CEST en marzo; 03:00 CEST=01:00 UTC en octubre)
    if month == 3:
        return day > last_sun or (day == last_sun and hour >= 1)
    else:  # october
        return not (day > last_sun or (day == last_sun and hour >= 1))
NTP_INTERVALO_MS = 3600 * 1000
_ULTIMA_SYNC = None


def get_ntp_time_local():

    # Lista de servidores NTP para intentar
    ntp_servers = ['pool.ntp.org', 'time.google.com', 'europe.pool.ntp.org']

    # Lista de días de la semana
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # NTP solo una vez por hora: cada llamada bloquea hasta ~1 s por servidor y el
    # servidor la usaba cada segundo, dejando la pantalla sin atender HTTP/UDP.
    global _ULTIMA_SYNC
    sync = _ULTIMA_SYNC is None or time.ticks_diff(time.ticks_ms(), _ULTIMA_SYNC) > NTP_INTERVALO_MS
    for server in (ntp_servers if sync else [None]):
        try:
            if server:
                ntptime.host = server
                ntptime.settime()
                _ULTIMA_SYNC = time.ticks_ms()
                print(f"Sincronización con {server} exitosa")

            utc_time = time.localtime()
            offset = UTC_OFFSET + (DST_OFFSET if is_summer_time(utc_time) else 0)
            current_time = time.localtime(time.time() + offset)
            hours = f"{current_time[3]:02}"
            minutes = f"{current_time[4]:02}"
            seconds = f"{current_time[5]:02}"
            day = f"{current_time[2]}"  # Día sin ceros iniciales
            month = f"{current_time[1]}"  # Mes sin ceros iniciales
            year = f"{current_time[0] % 100:02}"  # Los dos últimos dígitos del año
            weekday = days_of_week[current_time[6]]  # Día de la semana
            return year, weekday, hours, minutes, seconds, day, month
        except Exception as e:
            print(f"Error al sincronizar con {server}: {e}")

    if sync:
        # Sin NTP (p. ej. sin internet): reintentar en 5 min y usar el reloj interno
        print("Fallo en todos los servidores NTP; reintento en 5 min, uso el reloj interno")
        _ULTIMA_SYNC = time.ticks_add(time.ticks_ms(), -(NTP_INTERVALO_MS - 300000))
        return get_ntp_time_local()
    return '00', 'desconocido', '00', '00', '00', '00', '00'
def get_matrix_id():
    """Genera el ID único basado en la MAC: matrix_a1b2c3d4e5f6"""
    mac = network.WLAN(network.STA_IF).config('mac')
    # Convertimos a hex, quitamos 'b' y formateamos a minúsculas sin separadores
    mac_str = ubinascii.hexlify(mac).decode()
    return "matrix_" + mac_str

def setup_hostname():
    """Configura el hostname en el stack de red"""
    hostname = get_matrix_id()
    print("Configurando Hostname:", hostname)
    try:
        # En algunas versiones de MicroPython se hace así:
        network.hostname(hostname)
    except:
        # En otras versiones se pasa a través de la configuración de la interfaz
        pass
    return hostname


# Conectar a la red Wi-Fi
def connect_wifi():
    with open('config.json', 'r') as f:
        config = json.load(f)
    f.close()
    
    if not config["wifi_credentials"]:  # Si no se proporcionan credenciales
        print("No se proporcionaron credenciales Wi-Fi, activando hotspot...")
        start_hotspot(config)  # Llama a la función que maneja la escritura en config.json
        with open('config.json', 'r') as f:
            config = json.load(f)
        f.close()        
        # return

    sta.active(True)
    
    hostname = setup_hostname() # <--- Añadido
    
    for cred in config["wifi_credentials"]:
        ssid = cred["ssid"]
        password = cred["password"]
        print(f"Intentando conectar a Wi-Fi: {ssid}")
        #draw_centered_text(ssid, position_y, color=(0, 0, 0))

        sta.connect(ssid, password)
        start_time = time.time()
        while not sta.isconnected():
            if time.time() - start_time > 10:  # Tiempo máximo de espera
                print(f"No se pudo conectar a {ssid}")
                break
            time.sleep(0.5)
        if sta.isconnected():
            print(f"Conectado a {ssid}")
            print("Dirección IP:", sta.ifconfig()[0])
            print(str(sta.ifconfig()[0].split(".")[3]))
            #draw_centered_text(str(sta.ifconfig()[0].split(".")[3]), position_y, color=(0, 0, 0))
            break
    else:  # Si no se conecta a ninguna red
        print("No se pudo conectar a ninguna red Wi-Fi, activando hotspot...")
        start_hotspot(config)  # Maneja nuevas credenciales
def start_hotspot(config):
    # Definir el nombre de la WiFi
    hotspot_ssid = "Pantalla"  # Nombre de la red WiFi
    position_y = 3

    # Configurar punto de acceso
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=hotspot_ssid, authmode=network.AUTH_OPEN)
    ip = ap.ifconfig()[0]
    print(f"Hotspot activado con SSID: {hotspot_ssid}")
    #scroll_text_left("Wifi " + str(hotspot_ssid) + " " + str(ip), y=position_y, color=(255, 255, 0), delay=0.07)

    # Página web HTML
    def web_page():
        return """<!DOCTYPE html>
        <html>
        <head><title>Configurar WiFi</title></head>
        <body>
        <h1>Configura tu WiFi</h1>
        <form action="/config">
            <label for="ssid">Nombre de la red (SSID):</label><br>
            <input type="text" id="ssid" name="ssid"><br><br>
            <label for="password">Clave:</label><br>
            <input type="password" id="password" name="password"><br><br>
            <input type="submit" value="Confirmar">
        </form>
        </body>
        </html>
        """

    # Servidor HTTP
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    srv = socket.socket()
    srv.bind(addr)
    srv.listen(1)
    print(f"Servidor web iniciado en: http://{ip}:80")

    while True:
        try:
            cl, addr = srv.accept()
            request = cl.recv(1024).decode()

            if "/config?" in request:
                # Obtener parámetros de la solicitud
                params = request.split(" ")[1].split("?")[1].split("&")
                wifi_config = {}
                for param in params:
                    key, value = param.split("=")
                    wifi_config[key] = value

                ssid = wifi_config.get("ssid", "").replace("%20", " ")
                password = wifi_config.get("password", "").replace("%20", " ")
                print(f"Configurando WiFi con SSID: {ssid}, Contraseña: {password}")

                config["wifi_credentials"] = [{"ssid": ssid, "password": password}]
                
                # Guardar la configuración en un archivo
                with open('config.json', 'w') as f:
                    json.dump(config, f)
                
                print(f"Credenciales Wi-Fi guardadas: {config['wifi_credentials']}")

                # Responder al cliente
                response = "<h1>Credenciales guardadas correctamente.</h1>"
                cl.send(b"HTTP/1.1 200 OK\nContent-Type: text/html\n\n" + response.encode())
                cl.close()
                return

            # Responder con la página principal
            response = web_page()
            cl.send(b"HTTP/1.1 200 OK\nContent-Type: text/html\n\n" + response.encode())
            cl.close()

        except Exception as e:
            print(f"Error al manejar la solicitud: {e}")
            try:
                cl.close()
            except Exception:
                pass




# Obtener el pronóstico del tiempo actual
def get_weather_forecast(CODPROV, COD_GEO):
    url = f"https://www.el-tiempo.net/api/json/v2/provincias/{CODPROV}/municipios/{COD_GEO}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            max_temp = int(data['temperaturas']['max'].split("°")[0])
            min_temp = int(data['temperaturas']['min'].split("°")[0])
            current_temp = int(data['temperatura_actual'].split("°")[0])
            weather_status = data['stateSky']['description']
            precip_mm = int(round(float(data.get('precipitacion', '0'))))
            return max_temp, min_temp, current_temp, weather_status, precip_mm
        else:
            print(f"Error al obtener los datos del clima: {response.status_code}")
            return None, None, None, "Error al obtener los datos", 0
    except Exception as e:
        print(f"Error al hacer la solicitud para obtener el clima: {e}")
        return None, None, None, "Error al obtener los datos", 0

def get_ssid():
    return sta.config('essid')

def get_ip():
    return sta.ifconfig()[0]

def get_hostname():
    import network
    return network.hostname()


def _local_fw_version():
    """Lee la versión instalada desde fw_version.txt; si no existe usa my_shared."""
    try:
        with open('fw_version.txt', 'r') as f:
            return f.read().strip()
    except:
        return my_shared.FIRMWARE_VERSION


def check_for_updates():
    """Comprueba si hay actualizaciones en GitHub y descarga archivo por archivo si es necesario.
    Nunca toca my_shared.py ni config.json — la versión instalada se guarda en fw_version.txt."""
    try:
        print("Comprobando actualizaciones...")
        with open('config.json', 'r') as f:
            config = json.load(f)
        token = config.get("github_token", "")
        headers = {"Authorization": "token " + token} if token else {}

        r = urequests.get(my_shared.UPDATE_URL, headers=headers, timeout=15)
        if r.status_code != 200:
            print("Error descargando version.json:", r.status_code)
            r.close()
            return
        remote_data = r.json()
        r.close()

        local_version = _local_fw_version()
        remote_version = remote_data.get("version", "0.0.0")
        print("Version local:", local_version, "remota:", remote_version)
        if compare_versions(local_version, remote_version) < 0:
            print("Actualización disponible:", remote_version, ">", local_version)
            files = remote_data.get("files", my_shared.UPDATE_FILES)
            base = my_shared.GITHUB_RAW_BASE
            updated = 0
            import gc
            for fname in files:
                gc.collect()                 # TLS necesita mucha RAM libre
                try:
                    r = urequests.get(base + fname, headers=headers, timeout=30)
                    if r.status_code == 200:
                        with open(fname, 'wb') as f:
                            f.write(r.content)
                        print("Actualizado:", fname)
                        updated += 1
                    else:
                        print("Error descargando", fname, ":", r.status_code)
                    r.close()
                except Exception as e:
                    print("Error en", fname, ":", e)
            if updated > 0:
                with open('fw_version.txt', 'w') as f:
                    f.write(remote_version)
                print("Reiniciando para aplicar actualización...")
                machine.reset()
        else:
            print("Firmware al día:", local_version)
    except Exception as e:
        print("Error en check_for_updates:", e)


def compare_versions(local, remote):
    """Compara versiones semánticas. Retorna -1 si local < remote, 0 si igual, 1 si local > remote"""
    local_parts = [int(x) for x in local.split('.')]
    remote_parts = [int(x) for x in remote.split('.')]
    for l, r in zip(local_parts, remote_parts):
        if l < r:
            return -1
        elif l > r:
            return 1
    return 0


def download_icon(icon_id):
    """TC001: True si el icono ya esta en /ICONS. Si falta NO se descarga ahora (por
    https se queda sin memoria y podria colgar la pantalla): se apunta en
    icons_pendientes.txt y mensajes_tc001 lo baja en el siguiente arranque."""
    import os
    icon_path = "/ICONS/{}.gif".format(icon_id)
    try:
        if os.stat(icon_path)[6] > 0:
            return True
    except OSError:
        pass
    try:
        try:
            with open("icons_pendientes.txt") as f:
                ya = [l.strip() for l in f]
        except OSError:
            ya = []
        if str(icon_id) not in ya:
            with open("icons_pendientes.txt", "a") as f:
                f.write("{}\n".format(icon_id))
            print("Icono {} pendiente: se bajara al reiniciar".format(icon_id))
    except Exception:
        pass
    return False

   
def get_future_forecast(CODPROV, COD_GEO):
    # URL de la API para obtener el tiempo actual
    url = f"https://www.el-tiempo.net/api/json/v2/provincias/{CODPROV}/municipios/{COD_GEO}"
    print("URL:", url)

    # Hacer la solicitud a la API
    try:
        response = requests.get(url)
    except Exception as e:
        print("Error en la solicitud:", e)
        return ["Error al obtener los datos"]

    if response.status_code == 200:
        data = response.json()
        forecast_list = []

        # Extraer el pronóstico de los próximos 5 días
        for day_data in data['proximos_dias'][:3]:  # Tomar solo los próximos días
            fecha = day_data["@attributes"]["fecha"]
            dia = fecha.split("-")[2]  # Extraer solo el día (número)

            min_temp = day_data["temperatura"]["minima"]
            max_temp = day_data["temperatura"]["maxima"]

            # Precipitación máxima del día
            precip_mm = max([int(p) for p in day_data["prob_precipitacion"] if p.isdigit()])

            # Cota de nieve más baja (si existe)
            snow_levels = [int(c) for c in day_data.get("cota_nieve_prov", []) if isinstance(c, str) and c.isdigit()]
            snow_mm = min(snow_levels) if snow_levels else 0

            # Velocidad máxima del viento durante el día
            wind_speeds = []
            viento_data = day_data["viento"]
            if isinstance(viento_data, list):
                wind_speeds = [int(v["velocidad"]) for v in viento_data if "velocidad" in v]
            elif isinstance(viento_data, dict):
                wind_speeds = [int(viento_data["velocidad"])]
            max_wind_speed = max(wind_speeds) if wind_speeds else 0

            # Estado del cielo, obteniendo el primer estado del día como referencia
            weather_status = day_data["estado_cielo_descripcion"][0]

            # Formatear el pronóstico del día
            forecast_str = f"Dia {dia}: {min_temp}º/{max_temp}º"
            if precip_mm > 15:
                forecast_str += f". {precip_mm} % lluvia"
            #if snow_mm < 1300:
            #    forecast_str += f". Nieve a {snow_mm} m"
            if max_wind_speed > 40:
                forecast_str += f". Viento {max_wind_speed} km/h"

            # Añadir el pronóstico formateado a la lista
            forecast_list.append(forecast_str)

        response.close()
        return forecast_list

    else:
        response.close()
        return ["Error al obtener los datos"]
