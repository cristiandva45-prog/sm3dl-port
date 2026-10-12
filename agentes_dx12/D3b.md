# Bitácora D3b — PEDIDO D3 de E2: blend MIXTO exacto con D3D12_BLEND_ALPHA_FACTOR

## 9 oct 2026 — HECHO
Leídos BRIEF_COMUN, BRIEF_15, D3.md, E2.md (PEDIDO D3: `e2.py estado_blend` difería en 3/150 dibujos, todos blend RGB con
CONSTANT_COLOR y CONSTANT_ALPHA a la vez). NO corrí el juego (regla 1): solo la prueba WARP de D3 y el arnés E2.

Respaldos: `recomp\render\raster_d3d12_estado.inc.antes_dx12_D3b`, `agentes_dx12\D3\prueba_estado.c.antes_dx12_D3b`.
`raster_d3d12_dibujar.inc` (D5) NO se tocó: ya llama `dx_estado_factor(&est, bf)` y en el caso mixto el factor sigue (r,g,b,a).

Cambio en `raster_d3d12_estado.inc` (nota 2 reescrita):
- `dx_estado_alfa_factor()`: consulta perezosa UNA vez de `OPTIONS13.AlphaBlendFactorSupported` sobre `DX_ESTADO_DEV`
  (por defecto `g_d3d.dev`; sin dispositivo devuelve 0 y reintenta). Lo anota en el log:
  `[raster] d3d12: OPTIONS13.AlphaBlendFactorSupported = 1 (...)`.
- `dx_es_mixto(e)`; en `dx_estado_normal`, si es mixto y hay soporte, el RGB conserva PICA 12/13 (ya no se pliegan a 10/11),
  así la clave del PSO los distingue; `dx_blend_rgb()` los traduce a `D3D12_BLEND_ALPHA_FACTOR` / `INV_ALPHA_FACTOR`.
- El aviso "mezcla CONSTANT_COLOR y CONSTANT_ALPHA" solo sale si NO hay soporte (camino viejo, aproximado).
- Sabotaje de prueba nuevo: `sab_prueba & 16` = ignorar el soporte.

Medido:
- RTX 5050 Laptop y WARP: AlphaBlendFactorSupported = 1.
- `py -I agentes_dx12\E2\tools\construir_e2.py` → rc 0; `e2.py estado_blend` → **IGUAL** (antes DISTINTO);
  `diag_estado.py estado_blend` → **0 dibujos introducen diferencia (de 150)** (antes 3). El log d3d12_B de la corrida
  trae la línea OPTIONS13 = 1 y ningún aviso de mezcla.
- `e2.py autoprueba` → BIEN (7/7 detectadas, 0 reintentos).
- `prueba_estado.exe` (WARP): 0 → PASA; 600 casos de píxel con **114 mixtos ahora incluidos** (antes excluidos), 0 fuera de
  ±1, error máx 0 LSB; la clave se prueba otra vez con el dispositivo (11.390 claves, 0 colisiones). Sabotajes, todos FALLAN:
  1 → 24, 2 → 416, 4 → 114, 8 → 477, **16 (nuevo: sin ALPHA_FACTOR) → 72**. Salidas en `agentes_dx12\D3\sal_<n>.txt`.
- Chequeo de la unidad (`raster_gl.c` con `-DSM3DL_CON_D3D12`, comando de D3.md): 0 warnings.

Archivos tocados: `recomp\render\raster_d3d12_estado.inc`, `agentes_dx12\D3\prueba_estado.c` (+ .exe y sal_*.txt).
Pendiente (sesión principal): re-enlazar el exe integrado (`compilar.py --d3d12`) para que lleve el cambio; la prueba con
el juego sigue pendiente (ver D3.md/E2.md).
