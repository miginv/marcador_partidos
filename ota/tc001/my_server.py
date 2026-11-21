import socket
import json
import my_display
import my_shared

message_queue = []


def send_json_response(cl, status_code, body):
    status_text = 'OK' if status_code == 200 else 'Service Unavailable' if status_code == 503 else 'OK'
    cl.send('HTTP/1.1 {} {}\r\nContent-Type: application/json\r\n\r\n{}'.format(status_code, status_text, body))


def recv_request(cl):
    """Lee el request HTTP completo respetando Content-Length para evitar truncar el body."""
    cl.settimeout(3.0)
    raw = b''
    try:
        # Leer cabeceras hasta encontrar \r\n\r\n
        while b'\r\n\r\n' not in raw:
            chunk = cl.recv(512)
            if not chunk:
                break
            raw += chunk
        # Extraer Content-Length si existe y leer el body completo
        header_part, _, body_part = raw.partition(b'\r\n\r\n')
        content_length = 0
        for line in header_part.split(b'\r\n'):
            if line.lower().startswith(b'content-length:'):
                try:
                    content_length = int(line.split(b':',1)[1].strip())
                except Exception:
                    pass
        while len(body_part) < content_length:
            chunk = cl.recv(min(512, content_length - len(body_part)))
            if not chunk:
                break
            body_part += chunk
        return (header_part + b'\r\n\r\n' + body_part).decode('utf-8', 'ignore')
    except OSError:
        return raw.decode('utf-8', 'ignore')
    finally:
        cl.settimeout(None)


def enqueue_awtrix_payload(payload):
    if len(message_queue) >= my_shared.MESSAGE_QUEUE_MAX:
        return False
    message_queue.append(payload)
    return True


def process_next_message():
    if not message_queue:
        return
    payload = message_queue.pop(0)
    msg_type = payload.get("_type", "awtrix")
    print('Procesando mensaje tipo:', msg_type, '. Pendientes:', len(message_queue))
    if msg_type == "scoreboard":
        try:
            my_display.display_scoreboard(
                payload["local"], payload["visitor"],
                payload["local_color"], payload["visitor_color"],
                payload["local_pts"], payload["visitor_pts"],
                payload["minutes"], payload["seconds"],
                payload["quarter"],
            )
        except Exception as e:
            print("Error en display_scoreboard:", e)
    else:
        my_display.process_awtrix(payload)


def handle_settings_request(cl, body):
    try:
        payload = json.loads(body)
        if 'BRI' in payload:
            bri = payload['BRI']
            try:
                bri_value = int(float(bri))
                my_shared.BRIGHTNESS = max(0, min(100, bri_value)) / 100.0
            except Exception:
                pass
        response_body = json.dumps({'success': True, 'BRI': int(my_shared.BRIGHTNESS * 100)})
        send_json_response(cl, 200, response_body)
        print('Ajuste de brillo Awtrix:', response_body)
        return True
    except Exception as e:
        print('Error leyendo JSON en settings:', e)
        return False


def version_info():
    """JSON con la versión instalada (fw_version.txt) y datos del equipo."""
    import os
    try:
        with open('fw_version.txt') as f:
            fw = f.read().strip()
    except Exception:
        fw = my_shared.FIRMWARE_VERSION
    info = {'version': fw, 'tiles': my_shared.MATRIX_TILES,
            'marcador': 'marcador_mondo.py' in os.listdir()}
    try:
        import marcador_mondo
        info['error'] = marcador_mondo.ultimo_error
        info['activo'] = marcador_mondo._ultimo is not None
    except Exception:
        pass
    try:
        import my_network
        info['hostname'] = my_network.get_hostname()
        info['ip'] = my_network.get_ip()
    except Exception:
        pass
    return json.dumps(info)


def handle_client(cl):
    """Maneja una conexión cliente."""
    try:
        cl.settimeout(5.0)
        raw_request = cl.recv(2048).decode('utf-8', 'ignore')
        request_line = raw_request.split('\r\n', 1)[0] if raw_request else ''

        if request_line.startswith('POST /api/settings'):
            parts = raw_request.split('\r\n\r\n', 1)
            if len(parts) > 1 and handle_settings_request(cl, parts[1]):
                return

        if request_line.startswith('GET /api/stats'):      # TC001: sensores, luz, bateria
            import hw_tc001
            send_json_response(cl, 200, json.dumps(hw_tc001.stats()))
            return

        if request_line.startswith('GET /api/version'):
            send_json_response(cl, 200, version_info())
            return

        if request_line.startswith('GET /api/settings'):
            body = json.dumps({'BRI': int(my_shared.BRIGHTNESS * 100)})
            send_json_response(cl, 200, body)
            return

        if request_line.startswith('POST /api/reboot'):
            send_json_response(cl, 200, '{"success": true}')
            cl.close()
            import machine
            machine.reset()
            return

        if request_line.startswith('POST /api/scoreboard'):
            parts = raw_request.split('\r\n\r\n', 1)
            if len(parts) > 1:
                try:
                    d = json.loads(parts[1])
                    payload = {
                        "_type":        "scoreboard",
                        "local":        str(d.get("local",        "LOC")),
                        "visitor":      str(d.get("visitor",      "VIS")),
                        "local_color":  d.get("local_color",  [255, 255, 255]),
                        "visitor_color":d.get("visitor_color",[255, 255, 255]),
                        "local_pts":    int(d.get("local_pts",  0)),
                        "visitor_pts":  int(d.get("visitor_pts",0)),
                        "minutes":      int(d.get("minutes",    0)),
                        "seconds":      int(d.get("seconds",    0)),
                        "quarter":      int(d.get("quarter",    1)),
                    }
                    if enqueue_awtrix_payload(payload):
                        send_json_response(cl, 200, '{"success": true}')
                        print('Marcador encolado:', payload["local"], "vs", payload["visitor"])
                    else:
                        send_json_response(cl, 503, '{"success": false, "error": "queue full"}')
                    return
                except Exception as e:
                    print('Error JSON scoreboard:', e)

        if request_line.startswith('POST /api/notify') or request_line.startswith('POST /api/custom'):
            parts = raw_request.split('\r\n\r\n', 1)
            if len(parts) > 1:
                try:
                    payload = json.loads(parts[1])
                    if enqueue_awtrix_payload(payload):
                        send_json_response(cl, 200, '{"success": true}')
                        print('Payload recibido y encolado. Cola:', len(message_queue))
                    else:
                        send_json_response(cl, 503, '{"success": false, "error": "queue full"}')
                        print('Cola llena, mensaje descartado.')
                    return
                except Exception as e:
                    print('Error: JSON invalido', e)

        cl.send('HTTP/1.1 404 Not Found\r\n\r\n')
    except Exception as e:
        print('Error manejando peticion:', e)
    finally:
        cl.close()


def _atender(s, marcador_mondo):
    """Tras un aviso de poll: leer UDP y aceptar HTTP, ambos sin bloquear.
    No depende de qué objeto devuelva poll (así nunca se queda un evento sin atender)."""
    if marcador_mondo:
        try:
            marcador_mondo.leer_udp()
        except Exception as e:
            print('Error UDP marcador:', e)
            marcador_mondo.ultimo_error = repr(e)[:120]
    try:
        cl, addr = s.accept()
    except OSError:
        return
    handle_client(cl)


def start_api_server_with_clock():
    """Servidor no bloqueante: dibuja un frame del reloj cada 100ms y acepta
    conexiones entre frames, sin bloquear nunca más de 100ms."""
    import my_display
    import my_network
    import time

    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(2)
    s.setblocking(False)            # accept() no bloquea; handle_client fija su timeout
    print('Servidor API (Awtrix compatible) con reloj activo en puerto 80')

    # Estado del reloj
    clock_hours = '00'
    clock_minutes = '00'
    clock_day = '1'
    last_ntp = 0

    # Modo marcador (reloj MONDO por UDP 4210 o por USB): ver marcador_mondo.py
    import sys
    import select
    poll = select.poll()
    poll.register(s, select.POLLIN)
    udp = marcador_mondo = None
    try:
        import marcador_mondo           # si falta el fichero, la pantalla sigue como antes
        udp = marcador_mondo.abrir_udp()
        poll.register(udp, select.POLLIN)
        # USB (stdin) desactivado: en el ESP32-C3 sys.stdin.read(1) puede bloquear el bucle
        # y dejar la pantalla sin API. Solo WiFi.
    except Exception as e:
        print('Modo marcador no disponible:', e)

    while True:
        # Modo marcador: sin reloj ni cola; esperar como mucho 5 ms entre lecturas
        if marcador_mondo and marcador_mondo.activo():
            if poll.poll(5):
                _atender(s, marcador_mondo)
            continue

        # Procesar un mensaje si hay pendientes
        if message_queue:
            process_next_message()
            # No hacer continue: actualizar reloj y aceptar conexiones entre mensajes

        # Actualizar hora desde NTP una vez por segundo
        now = time.time()
        if now - last_ntp >= 1:
            try:
                _, _, hours, minutes, _, day, _ = my_network.get_ntp_time_local()
                h = int(hours) % 24  # get_ntp_time_local ya aplica DST
                clock_hours = '{:02d}'.format(h)
                clock_minutes = minutes
                clock_day = day
            except Exception as e:
                print('Error NTP:', e)
            last_ntp = now

        # Dibujar un frame del reloj (no bloqueante)
        separator_on = int(time.time()) % 2 == 0
        my_display.display_clock_frame(clock_hours, clock_minutes, clock_day, separator_on)

        # Esperar hasta 100 ms a HTTP, UDP o USB (un mensaje del marcador despierta al instante)
        if poll.poll(100):
            _atender(s, marcador_mondo)
