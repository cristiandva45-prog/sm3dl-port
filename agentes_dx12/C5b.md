# C5b — PEDIDO C5 de E2: empates del copiar punto escalado (9 oct 2026)

Archivo tocado: `recomp\render\raster_d3d12_copiar.inc` (respaldo `.antes_dx12_C5b`). Nada más fuera de `agentes_dx12\C5\`.

## Hecho
- PS `blit` camino PUNTO: texel en ENTEROS. Constantes reinterpretadas solo en punto: A = (sx0, sy0, dw, dh),
  B = (dx0, dy0, sw, sh) (con signo = volteo); lineal sin cambios. n = (2(X-d0)+1)*sw, d = 2*dw, signo normalizado a d > 0,
  texel = s0 + floor((n-1)/d) (= ceil(n/d) - 1) y Load con clamp.
- MEDIDO (copia privada del arnés, `agentes_dx12\C5\e2\`, paso "base punto (2,3)-(62,60)" 800x480 -> 60x57):
  floor(s) en float (antes) = 20 px; floor(n/d) exacto (la propuesta literal de E2) = los MISMOS 20 px (el GL NO toma
  el valor exacto en el empate); floor((n-1)/d) (empate al texel de abajo) = **0 px**. pres_pasos_x2 total: 226 -> 184 B;
  lo que queda (op 73/80, 31 px en x = 7 y 22) es la capa punto escalada = PEDIDO C1, no es mío.
- `prueba_copiar`: TODO OK; sabotajes SM3DL_C5_SABOTAJE=1..6: cada uno sigue fallando su caso (1 falla c/u).
- `e2.py autoprueba` (copia privada): BIEN, 7/7 detectados, 0 reintentos. Chequeo de la unidad: sin warnings.

## Notas
- El arnés compartido `agentes_dx12\E2\prueba_e2.exe` y `E2\trabajo\` los estaban usando OTROS agentes a la vez (lld:
  "Permission denied" al enlazar; salidas pisadas: allí se ve 1634 B por cambios ajenos en op 73/80). Por eso hice una
  copia privada: `agentes_dx12\C5\e2\` (tools con RAIZ corregida, prueba_e2.c, cache_arnes, glsl_arnes, trabajo\extraido).
  Diferencias por paso: `py -I agentes_dx12\C5\c5b_pasos.py` (tras `py -I agentes_dx12\C5\e2\tools\e2.py pres_pasos_x2`).
- La regla del empate está medida en ESTA GPU/driver (NVIDIA RTX 5050). Con volteo en x de la fuente el sentido del
  empate no está medido (el escenario solo voltea y en coordenadas GL, que en D3D12 queda sin volteo).
- Prueba pendiente con el juego: la misma de C5.md.
