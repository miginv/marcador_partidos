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
