# D4b — vertices crudos ENTEROS nativos en D3D12 (BYTE/UBYTE/SHORT sin normalizar)

## Estado: HECHO. Un solo DXIL por VS sirve para todos los layouts; enteros por la IA, conversion en el VS. Sin el juego.

## 9 oct 2026 — inicio
- Leidos BRIEF_15, BRIEF_COMUN, D4.md (propuesta int4), B.md (contrato HLSL), E1.md, D1.md, partes D1/D4/D5.
- Diseno elegido (un solo DXIL por VS, sin variantes):
  - El VS declara las entradas como `uint4` (GLSL `in uvec4 dx_entK`) y arma `vK` (global float4) al empezar main()
    con un selector de 4 bits por registro en un cbuffer NUEVO b4 (constantes RAIZ, 4 DWORD = uvec4 dx_vtipo):
    bits 0-1: 0 = bits de float (formato *_FLOAT, como hoy), 1 = entero con signo (*_SINT), 2 = sin signo (*_UINT);
    bit 2: w = 1 (atributo de 3 componentes de 8/16 bits leido con formato de 4: DXGI no tiene 3 x 8/16).
  - Formato del elemento != tipo de la entrada del VS: legal en D3D (los bits pasan tal cual; el debug layer solo avisa).
  - Firma raiz de D1: parametro 6 = 4 constantes raiz en b4 (visibilidad VERTEX). D5 aplica los vertices DESPUES de
    SetGraphicsRootSignature (cambiar la firma invalida las constantes).

## 23:05 hito 1 — cadena + parte + firma (todo compila)
- `agentes_dx12\B\cadena_shaders.py` (respaldo `.antes_dx12_D4b`): `entradas_enteras()` al final de `vulkanizar()` (solo VS
  con `layout(location = K) in vec4 vK;`): entrada `uvec4 dx_entK` + global `vec4 vK` + `CB4 { uvec4 dx_vtipo; }` (b4) +
  `dx_vconv()` al empezar `main()`. `CADENA_VERSION` -> `...+vulkanizar-2`. PS/GS/auxiliares: texto identico al de antes.
- `recomp\render\raster_d3d12_vertices.inc` (respaldo `.antes_dx12_D4b`): formatos *_SINT/_UINT por tipo, selector
  `dx_vert_.tipos[4]`, `dx_vertices_aplicar` ademas hace `SetGraphicsRoot32BitConstants(DX_RS_VTIPO, 4, ...)`; contador
  `n_crudos_ent`; log "vertices crudos N (M con enteros nativos; rechazados: ...)". Sabotajes nuevos 3 (con signo leido
  sin signo) y 4 (sin w = 1).
- `recomp\render\raster_d3d12_prog.inc` (respaldo `.antes_dx12_D4b`): `DX_RS_VTIPO 6`, `DX_RS_N 7` (param 6 = 4 constantes
  raiz en b4, VERTEX), `DX_PROG_VERSION` -2; el sabotaje 1 de D1 ahora mueve b3 a b5 (b4 ya es del selector); sabotaje 3
  nuevo (firma sin b4).
- `recomp\render\raster_d3d12_dibujar.inc` (respaldo `.antes_dx12_D4b`): UNA linea movida: `dx_vertices_aplicar(l)` va
  DESPUES de `SetGraphicsRootSignature`.
- Chequeo de la unidad (`sh agentes_dx12/D4b/chequeo.sh`, banderas de compilar.py + -DSM3DL_CON_D3D12): 0 errores, 0 warnings.

## HALLAZGO: regla de alineacion del input layout (medida; la doc no la escribe)
`prueba_vertices.exe sondeo` (RTX 5050): CreateGraphicsPipelineState da E_INVALIDARG si AlignedByteOffset no es multiplo de
min(4, bytes del FORMATO): R8 cualquiera; R8G8/R16 par; R8G8B8A8/R16G16/R16G16B16A16/R32* multiplo de 4. La 1a version
aceptaba "UBYTE x2 en 15" / "SHORT x2 en 18" y el PSO fallaba (= dibujo perdido): la prueba lo agarro. Regla aplicada a
offset Y stride; con eso el 4o componente leido de un atributo de 3 (8/16 bits) cae siempre dentro del stride (no hace falta
relleno). Lo que la PICA admite y DXGI no (UBYTE x4 en offset impar, BYTE x3 seguido de BYTE x3...) sigue cayendo a floats,
contado en "rechazados por alineacion".

## 23:15 hito 2 — DXIL regenerados e instalados
- `py -I tools\precompilar_d3d12.py regenerar --hilos 2 --solo "^vert/"`: 21/21 VS a DXIL (10 s de pared; DXC mediana 306 ms,
  max 2,08 s); 0/21 identicos a lo instalado (esperado). Tamano 947.860 -> 963.812 B (+1,7 %).
- `--solo` solo compara, no instala: `py -I agentes_dx12\D4b\mezclar_cache.py` arma `D4b\cache_mezcla\` (cache instalada + los
  21 VS nuevos + VERSION -2) y `py -I tools\precompilar_d3d12.py instalar --desde agentes_dx12\D4b\cache_mezcla` la valida
  e instala (os.replace). **`verificar` -> OK (732 esperados, 8,2 MB)**.
- Byte a byte despues: `--solo "^vert/(nwfont|code_2AC800)"` 3/3 identicos; `--solo "^(frag/R1\.frag|frag/R1_L[0-9]+\.frag|
  flip\.geom|aux/.*|uber\.frag)$"` **36/36 identicos** (PS/GS/aux no cambiaron). `precompilar_d3d12.py sabotaje`: todo bien.
- La cache de B (`agentes_dx12\B\cache_d3d12\`, -1) queda IGNORADA por version (D1 lo loguea).

## 23:20 hito 3 — verificacion (sin el juego)
1. **Prueba de D4 extendida** `agentes_dx12\D4b\prueba_vertices.exe` (compilar: `sh agentes_dx12/D4b/compilar_prueba.sh`, que
   genera el VS de paso `D4b\glsl\vert\paso16.vert` con la CADENA REAL -> `out_prueba\vert__paso16.vert.dxil`; firma con las
   constantes b4; stream output bit a bit vs semantica GL). Salida: `D4b\salida_prueba_vertices.txt`.
   1 floats (con -0, +-inf, NaN con carga, denormales) 592/0 distintos · 2 crudos float 592/0 · 3 rechazos 7/7 (short impar,
   float desalineado, fuera del stride, loader vacio, UBYTE x4 impar, SHORT x2 en 14, stride 30) con estado intacto · 4 hash
   (otro tipo = otro hash) · **5 crudos ENTEROS** (BYTE 1/3, UBYTE 2/3/4, SHORT 1/2/3/4, FLOAT 3 en 4 loaders; extremos
   -128/127/255/-32768/32767; 4o byte/short basura) **592/0 distintos** · 6 selector 01050250/01101612 == esperado. TODO BIEN.
   SABOTAJES (se ven fallar): =1 -> 2 y 5: 37 distintos; =2 -> 1: 576; =3 -> 5: 213; =4 -> 5: 111. Todos "HAY FALLAS".
2. **Prueba de D1** (`agentes_dx12\D1\prueba_prog.c` compilada en `D4b\prueba_prog_sab0.exe 9`): **737 textos -> VS 21,
   FS 715 (0 al uber), GS 1, NULL 0; 122 PSO creados / 0 rechazados**; claves bien. (1a corrida 60 s: el driver compila los
   122 PSO con los VS nuevos.) Sabotaje 3 nuevo (firma sin b4, `prueba_prog_sab3.exe`): **122/122 PSO rechazados** -> FALLA.
3. **Arnes de E2** (`py -I agentes_dx12\E2\tools\e2.py`, 28-32 s): antes (exe y caches viejos) 24/29 IGUALES; despues
   (`e2.py convertir` + `construir_e2.py`) **24/29 IGUALES, los MISMOS 5 distintos con las mismas cifras** (estado 29741,
   pres_x2/x4 92, estado_logic 54837, pres_pasos_x2 184: logic op y empates de punto, ajenos). vertices_arrays/u8/u16/cpu/
   sin_elem IGUAL. `--sab-env SM3DL_D4_SABOTAJE=1`: 3/3 crudos detectados; `=2`: detectado en vertices_cpu.
   OJO: ningun escenario de E2/A usa atributos enteros (u8/u16 son INDICES): el log dice "0 con enteros nativos".
4. **Escenarios enteros de punta a punta** `py -I agentes_dx12\D4b\e2_enteros.py` (importa e2.py; GL vs D3D12 con el exe de
   E2: armar_crudo + D4 + dibujar REAL de D5 + VS REAL de la cache): mix (FLOAT4+UBYTE4+BYTE3+SHORT2+SHORT3+BYTE1), p16
   (posicion SHORT x4: el signo se ve), p3 (posicion SHORT x3 con basura en el 4o: w = 1): **3/3 IGUAL**, log "con enteros
   nativos" > 0. Sabotajes: `--sab 1` 3/3 detectados, `--sab 3` p16 detectado, `--sab 4` p3 detectado. (El color NO sirve
   para el signo: la PICA usa min(|c|, 1), -1 y 255 dan igual; por eso p16/p3 van por la posicion.)
5. Exe integrado: `py -I recomp\arranque\compilar.py --d3d12 -o "C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\D4b\sm3dl_D4b.exe"`
   rc 0 (15,8 MB; contiene "con enteros nativos" y "vulkanizar-2").
- Incidente: ~23:10 `d3d12_recursos.c:432` (de C2) tenia un literal partido y no compilaba (ROTO POR C2, transitorio); a las
  23:13 ya compilaba.

## Archivos
Editados (respaldo `.antes_dx12_D4b`): `recomp\render\raster_d3d12_vertices.inc`, `raster_d3d12_prog.inc`,
`raster_d3d12_dibujar.inc` (1 linea movida), `agentes_dx12\B\cadena_shaders.py`. Regenerado: `extraido\shaders\cache_d3d12\`
(21 VS + VERSION). Datos de E2 regenerados con SUS comandos (`e2.py convertir`, `construir_e2.py`):
`E2\cache_arnes\V_4F0463BC.dxil`, `E2\trabajo\extraido\shaders\cache_d3d12\`, `E2\prueba_e2.exe`; lo viejo en
`D4b\respaldo_e2\`. Propios en `agentes_dx12\D4b\`: `prueba_vertices.c/.exe`, `compilar_prueba.sh`, `chequeo.sh`,
`extraer_dx.py`, `prueba_conv.py`, `glsl\vert\paso16.vert`, `mezclar_cache.py`, `e2_enteros.py`, `prueba_prog_sab0/3.exe`,
`d5gen\` (prueba de D5 compilada aparte: BIEN), salidas `*.txt`, `sm3dl_D4b.exe`.

## Pedidos
PEDIDO D5: (1) en `raster_d3d12_dibujar.inc` movi `dx_vertices_aplicar(l)` a DESPUES de `SetGraphicsRootSignature` (fija las
  constantes raiz del selector). (2) Tu `prueba_d5.c` arma una firma propia de 6 parametros: agrega el 7o
  (`D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS`, b4, 4 valores, VERTEX); hoy pasa (BIEN, compilada en `D4b\d5gen\`) pero
  `SetGraphicsRoot32BitConstants(6, ...)` sobre una firma de 6 es indefinido. Las `#define DX_RS_*` siguen en una linea c/u.
PEDIDO D1: edite tu `raster_d3d12_prog.inc` (param 6 + version -2 + sabotajes 1/3); toda firma futura debe conservar b4.
PEDIDO B / principal: `agentes_dx12\B\shaders_d3d12.c` (borrador sin enlazar) sigue con SD_CADENA_VERSION "-1": subirla a "-2"
  si se usa; la cache `agentes_dx12\B\cache_d3d12\` (-1, VS con float4) ya no vale.
PEDIDO E2: sumar los 3 escenarios de `D4b\e2_enteros.py` (mix/p16/p3) a `e2.py` (hoy ninguno usa atributos enteros).
PEDIDO principal: (1) un `regenerar` completo ya produce los VS nuevos (la cadena esta parcheada); (2) `regenerar --solo` no
  instala: para un subconjunto, `D4b\mezclar_cache.py` + `instalar --desde`.

## PRUEBA PENDIENTE CON EL JUEGO (no corrida, regla 1)
`set SM3DL_BACKEND=d3d12` y `"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\D4b\sm3dl_D4b.exe"` desde la
raiz; en el log `[raster] d3d12: vertices crudos N (M con enteros nativos; rechazados: A por alineacion, S por subida)` (1o,
2o y cada 5000): M/N = fraccion que ahora va nativa (antes 0), A = lo que sigue cayendo a floats por la alineacion DXGI.
Medir CPU del raster contra `agentes_dx12\D4\sm3dl_D4.exe` en el mismo tramo (esperado: el salto de GL con vertices
nativos, ~2x en la decodificacion) y comparar contra GL con
`powershell -File agentes_dx12\E2\prueba_pendiente_juego.ps1 -Exe agentes_dx12\D4b\sm3dl_D4b.exe`.
