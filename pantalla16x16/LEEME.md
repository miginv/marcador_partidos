# Pantalla 16x16 (ESP32-C3, MicroPython)

Matriz 16x16 hecha con una tira WS2812 en zigzag: filas de 16 LED y uno sin usar en cada
curva (271 LED). La tira empieza abajo a la izquierda. Datos en GPIO4.

- `my_shared.py`: layout (`MATRIX_TILES = 16161`), pin, orden de color y brillo.
- `pantalla16.py`: mapa de LED y pintado por columnas / por capas.
- `fuente16.py`: números de 16 px (posesión en grande) y de 7 px (dos líneas).
- `boot.py`: demos en bucle: posesión 24→0 en grande y, después, tiempo del cuarto
  (12:00, sigue la cuenta desde el arranque) con la posesión debajo.
