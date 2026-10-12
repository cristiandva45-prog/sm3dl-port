# C1b — PEDIDO C1 de E2: pres_capa punto escalada con Load de texel entero (9 oct 2026)
Archivo exclusivo: `recomp\render\raster_d3d12_init.inc` (respaldo `.antes_dx12_C1b`). No toco raster_d3d12_copiar.inc (C5b).
- Inicio: leído C1.md y E2.md (PEDIDO C1: 31 px en x = 7 y 22, 40x30→30x30, `e2.py pres_pasos_x2`).

## Resultado: PEDIDO C1 NO aplicable tal cual (medido) — pres_capa queda con Sample punto
- Prueba propia `py -I agentes_dx12\C1b\empates.py [--sab]` (exe propio `C1b\prueba_e2_c1b.exe` via `C1b\construir_c1b.py`,
  carpeta `C1b\trabajo\`, para no pisar `E2\prueba_e2.exe`, que C5b tenia bloqueado): capa 40x30 en punto escalada en
  5 rects (30x30, 30x45, 3,2-33,47, 50x50, 20x15), GL vs D3D12, px fuera de +-1:
  | variante del PS punto | 30x30 (= paso E2) | 30x45 | corrida | 50x50 | 20x15 | total |
  |---|---|---|---|---|---|---|
  | Sample punto (original) | 31 (x=7,22) | 74 | 74 | 0 | 10 | **189** |
  | Load s=((2(X-x0)+1)sw) div (2dw) (el pedido) | 269 (todas las x de empate) | 699 | 699 | 500 | 298 | 2465 |
  | Load con empate hacia abajo en x | 31 (x=7,22) | 451 | 451 | 0 | 292 | 1225 |
  | Load con uv en float estilo GL (y desde abajo) | 269 | 548 | 548 | 500 | 270 | 2135 |
- Lectura: en los empates exactos el GL de esta PC (RTX 5050) cae ABAJO en x=1,4,10,13... y ARRIBA en parte de x=7 y 22
  (depende del triangulo de la tira: ruido de float del interpolador de NVIDIA en GL). La formula entera del pedido es
  el valor EXACTO, no el de GL. El Sample punto de D3D12 ya da "empate abajo" en todos: es la mas cercana.
  Igualar los 31 px exigiria emular el interpolador GL de NVIDIA (no reproducible con certeza) → no lo hice.
- Sabotaje de la prueba: `--sab` (SM3DL_C1_SABOTAJE=1, capa corrida 1 px) → 6077 px (detecta).
- Estado final de `raster_d3d12_init.inc`: = respaldo `.antes_dx12_C1b` + un comentario con estas cifras (sin cambio de
  codigo). Prueba C1 32/32 BIEN; sabotajes 1 y 2 → MAL (1 y 2 fallas). e2.py autoprueba (GL vs GL) no se ve afectada
  (sin cambio de codigo); no la corri para no competir por `E2\prueba_e2.exe` con C5b.
- Propuesta: aceptar +-1 texel en los empates de punto escalado en E2 (o comparar pres_capa punto solo con escalas sin
  empates), igual que para C5. Si se insiste en igualar, PEDIDO E2: medir GL con mas rects para modelar el interpolador.
