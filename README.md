# marcador_partidos

`partidos.json` es la cola de partidos que sigue el marcador LED. La placa lo descarga al arrancar y cada 15 minutos.

Para quitar un partido, borra su bloque `{...}` y haz commit (se puede hacer desde la web de GitHub). La placa sigue los partidos en orden de `ts`.

Campos de cada partido:
- `ts`: inicio en epoch UTC (segundos). Es lo que usa la placa para ordenar y saber cuándo empieza.
- `fecha`, `hora`: lo mismo en hora de España, para leerlo.
- `local`, `visit`, `campo`, `categoria`: informativos.
- `notif`: IdPartidoNotificacion de la FBM. Identifica el partido.
- `buscar`, `skip`: término y página de la búsqueda FBM donde está el partido. La placa prueba `skip`, `skip-50` y `skip+50`.

Se genera con `buscar_partidos.py --json partidos.json` (repo smart_scoreboard).

## OTA de los marcadores (`ota/`)

`ota/32x8/` tiene el código de la pantalla Awtrix 32x8. En modo mensajes (sin partido cerca), la placa mira `version.json` al arrancar y cada 6 h. Si la versión es mayor que la instalada (`ota_version.txt` en la placa), baja los ficheros de `files`. Solo los sustituye si han llegado todos, y después se reinicia.

Para publicar un cambio: copia los ficheros aquí y sube `version` (1.0.0 → 1.0.1). Nunca se tocan `config.json` ni `my_shared.py`.
