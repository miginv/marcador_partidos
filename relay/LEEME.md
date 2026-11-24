# Servidor del marcador (relay)

Un solo cliente consulta la FBM y publica los datos en un servidor propio; las pantallas leen
de ese servidor por http normal (el Ulanzi TC001 no tiene memoria para TLS) con una clave por
pantalla.

```
recolector.py ──PUT (X-Token)──► servidor.py ◄──GET ?k=<clave>── Ulanzi, 32x8...
     │                              (Google Cloud e2-micro, puerto 80)
     └── consulta la FBM (gesdeportiva.py de ota/32x8)
```

| Fichero | Qué hace |
|---|---|
| `servidor.py` | Guarda y sirve los JSON (`/partidos.json`, `/m/<notif>.json`). Leer exige clave si existe `claves.json`; 120 lecturas/min por IP |
| `recolector.py` | Sigue los partidos de la lista (de -20 a +150 min) y los publica. `fin_forzado.txt`: partidos a dar por terminados a mano. `PARTIDOS_URL` para fijar otra lista |
| `instalar_vm.sh` | Instala servidor + recolector como servicios en una VM Ubuntu |
| `repartir_claves.py` | En nano: entrega a cada pantalla su clave (cuando está en modo mensajes) |
| `nano/` | Servicio y temporizador de systemd de `repartir_claves.py` |
| `oracle_crear_vm.py` | Intento de VM gratuita en Oracle (sin capacidad en Madrid; abandonado) |
| `simular.py` | Partido ficticio para pruebas |

Nunca van al repositorio: `token.txt`, `claves.json`, `fin_forzado.txt`, `datos/`.
