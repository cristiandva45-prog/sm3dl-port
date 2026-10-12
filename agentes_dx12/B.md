# Agente B — paso 2: cadena de shaders GLSL → SPIR-V → HLSL → DXIL (8 oct 2026)

Estado final: **741/741 shaders del port llegan a DXIL firmado (SM 6.0)**, el TEV entero da **0 LSB contra `tools\tev_ref.py`
ejecutado en D3D12/WARP** (39 840 casos), y el layout de los cbuffers coincide con `RbCb*` de `raster_backend.h` (agente A).
No se corrió el juego ni nada en la GPU; solo procesos de segundos, prioridad baja, 2 hilos.

## 1. Herramientas (versiones fijas, `agentes_dx12\B\terceros\`, una carpeta nueva cada una)
| Herramienta | Versión | Fuente oficial | Notas |
|---|---|---|---|
| glslang | **16.6.0** (11 sep 2026) | github.com/KhronosGroup/glslang/releases/download/16.6.0/glslang-16.6.0-windows-x86_64-release.zip | sha256 del zip `82bf434e…8d9b`. `bin\glslang.exe` + `include\` + `lib\` |
| DXC | **v1.9.2609** (dxc_2026_09_29.zip, dxcompiler 1.9.2609.5) | github.com/microsoft/DirectXShaderCompiler/releases/tag/v1.9.2609 | sha256 `ad31b1fc…e1`. `bin\x64\dxc.exe` + `dxil.dll` (firma/valida el DXIL) |
| SPIRV-Cross | tag **vulkan-sdk-1.4.363.0** | github.com/KhronosGroup/SPIRV-Cross (archivo zip del tag) | sha256 `637ee991…0c90`. **No hay binarios Windows recientes en sus releases** (el último es de 2021): se compiló desde la fuente con `py -m ziglang c++ -O2` (36 s) → `terceros\spirv-cross-src\out\spirv-cross.exe`. Los zips se borraron tras extraer. |
`dxil.dll` junto a `dxc.exe` ⇒ todo DXIL sale firmado (el cache lo comprueba: contenedor DXBC con hash ≠ 0 y parte `DXIL`).
Versión de la cadena (cadena_shaders.py `CADENA_VERSION`): `glslang-16.6.0+SPIRV-Cross-vulkan-sdk-1.4.363.0+dxc-1.9.2609.5+vulkanizar-1`.

## 2. Inventario (qué genera realmente el port)
**Hallazgo**: el C **no** genera los VS en vivo. `raster_gl.c vs_para()` lee los `.vert` ya generados por `tools\shader_glsl.py`
(`extraido\shaders\glsl\`, 21 programas de `programas.tsv`) y los pasa por `envolver_vert()` + `VERT_ENVOLTORIO`. Comprobado
con `verif_vert_generador.py`: los 21 `.vert` son **idénticos** a lo que produce hoy `shader_glsl.py` desde los `.shbin` (no hay deriva
C/Python). Los fragment shaders sí salen en vivo: `fs_para()` = cabecera (`#define ESPECIALIZADO`, `const uvec4 tev[6]`, bloque `LUZ`)
+ `FRAG_UBER`.
Como el texto final lo arma el C, se **compiló un volcador que incluye el propio `raster_uber.c`** y copia verbatim `reemplazar/envolver_vert/fs_para/luz_mues_de/luz_soporta`
(`B\volcar_glsl.c` → `volcar_glsl.exe`); `cadena_shaders.py comparar-c` verifica que `FRAG_UBER` y `GEOM_FLIP` del volcador son **byte a byte** el texto de `raster_uber.c`.
Inventario en `B\glsl\` (+ `INDICE.tsv`, 13 MB):
- 21 VS reales (`vert\`) + 2 auxiliares (`aux\giro_alta.vert`, `aux\pres_capa.vert`) = **23 VS**
- 1 GS (`flip.geom`)
- **717 PS**: uber por uniforms (`uber.frag`, modo `SM3DL_RASTER_UBER=1`) + **332 especializados sin luz** (una por receta TEV de `extraido\shaders\frag\recetas.json`) +
  **382 especializados con luz** (pares receta×config de luz que el juego usa realmente: join `pica_materiales.tsv` × `shaders\luz\censo_luz.tsv`) + 2 auxiliares (`giro_alta.frag`, `pres_capa.frag`).
  Los registros de luz de las 105 configs se **reconstruyen** desde `configs.json` (`configs_luz()`): aproximación con la misma estructura (cfg, fresnel, bump, LUTs presentes/entradas/signo); los registros crudos reales solo existen en ejecución.
- Total **741 textos** (732 distintos: 9 coinciden). Los `.frag` legados `extraido\shaders\frag\R*.frag`/`luz\L*.glsl` NO los usa el C actual (se ignoran).

## 3. Resultados de la conversión (`cadena_shaders.py convertir`)
| | n | glslang | SPIRV-Cross | DXC (DXIL) |
|---|---|---|---|---|
| VS | 23 | 23 | 23 | **23** |
| GS | 1 | 1 | 1 | **1** |
| PS | 717 | 717 | 717 | **717** |
**Sin transformar el GLSL (baseline `--sin-vulkanizar`, 66 shaders de muestra): 0/66** — todos caen en glslang. Causas (glslang solo reporta la primera por shader):
| causa | n | arreglo (en `vulkanizar()`) |
|---|---|---|
| `non-opaque uniforms outside a block` (VS: `pica_c/i/b`, `omap`, `clip_*`) | 22 | uniforms sueltos → cbuffers std140 con el layout de `RbCb*` |
| `SPIR-V requires location for user input/output` (`in V {…}` del PS uber y los `in/out` sueltos de los aux) | 41 | `layout(location=N)` en bloques y varyings |
| `sampler/texture requires layout(binding)` | 2 | `layout(set=0, binding=N)`: `tex0..2`→t0..t2, `luz_luts`→t3 |
| `gl_VertexID` no existe en Vulkan-GLSL | 1 | `gl_VertexIndex` |
Problemas que **solo aparecen más adelante** (con la transformación base ya puesta) y su arreglo:
1. **GS en SPIRV-Cross→HLSL**: no admite bloques de interfaz en arrays ni `gl_in[].gl_ClipDistance`, y emite `gl_in[k].gl_Position` sin declarar `gl_in` (el valor está en `gl_PositionIn[k]`). Arreglo: `GEOM_D3D` (mismo cálculo, varyings sueltos por *location*; la clip distance viaja en un miembro nuevo `cd` del bloque `V` que escribe el VS) + parche textual `arreglar_hlsl()` (bug de SPIRV-Cross 1.4.363.0). `_gs_d3d()` aborta si `GEOM_FLIP` cambia (hay que re-portar).
2. **std140 y `vec3`**: `struct Luz` con `vec3` deja `da_escala` dentro del hueco de `spot` (offset 92) y A espera 96 (`RbLuz`). Arreglo: struct con `vec4` + accesos `.xyz`.
3. **Layout dependiente de `#ifdef`**: en el uber los uniforms existen o no según `ESPECIALIZADO`/`LUZ`, lo que movería offsets. Arreglo: **todos los miembros se declaran siempre** en un orden fijo (tabla `BLOQUES`); los que chocan con las `const` de `fs_para` (`tev`, `luz_n`, `luz_c0/c1/abs/ent/esc`, `luz_mues`) se llaman `cb_<n>` con `#define` bajo `#ifndef ESPECIALIZADO`. Un hueco explícito `_pad0` tras `luz_mues` reproduce el `_p0` de `RbCbLuz`.

## 4. Tiempos (procesos externos incluidos, 2 hilos, prioridad baja; `out\resultados.tsv`)
- **PS** (717): mediana **264 ms** por shader (glslang 129 + SPIRV-Cross 23 + DXC 106); p95 ≈ 330 ms; máx 359 ms en DXC.
- **VS** (23): mediana 389 ms, pero los 7 grandes `Shader_*` (88-96 KB de DXIL) tardan **1,6-1,8 s solo en DXC**; `-O0` es peor (9,9 s), `-O1`≈`-O3`.
- GS: 173 ms. Suma de CPU ≈ 204 s; pared 96-107 s para los 741.
- DXIL: PS media 10 KB (máx 44), VS media 41 KB (máx 96), GS 9 KB; `cache_d3d12\` = 735 archivos / 9,6 MB.
- **Decisión: PRECOMPILAR + caché en disco, NO compilar en vivo.** Una partida normal (~20 VS + ~130 PS) costaría ≈ 40 s de CPU en vivo (los VS grandes bloquearían ~2 s cada uno) — peor que el caso GL sin caché (81 s → 1,1 s con ella). El juego tampoco necesita glslang/SPIRV-Cross/DXC dentro del proceso.
- Respaldo para lo no visto: si falta un PS especializado se usa **`F_UBER.dxil`** (el uber por uniforms; mismo resultado, más lento; las constantes TEV/luz ya van en `RbCbFragmento`/`RbCbLuz`) y el texto GLSL se vuelca a `extraido\shaders\desconocidos_d3d12\` (mismo patrón que `desconocidos\` de los VS) para reconvertirlo fuera de línea.

## 5. Propuestas concretas para los problemas pedidos
**Constant buffers** (hecho y verificado). 4 cbuffers fijos, mismos que el header de A: b0=`RbCbVertice` (1792 B), b1=`RbCbFragmento` (224 B), b2=`RbCbNiebla` (1024 B), b3=`RbCbLuz` (1056 B).
Arrays escalares empaquetados a vec4 (`pica_b`→`uint4 pica_b4[4]`, `omap`→`omap4[6]`, `tev_const`→`tev_const4[2]`, `luz_fila`→`luz_fila4[6]`; `niebla_lut` vec2[128]→`float4[64]`); los bool son `uint` 0/1.
`cadena_shaders.py layouts` compara los `packoffset` de **715 PS + 21 VS** con `offsetof()` de `raster_backend.h` (`check_layout.exe`): **34 miembros idénticos**, un único layout por bloque en todas las variantes; escribe `cb_layouts.h`. Sabotaje (`layouts --sabotaje`, un offset esperado +4) → falla.
**Coordenadas**. PICA→GL hoy: `gl_Position=(x,y,-z,w)` + `glClipControl(LOWER_LEFT, ZERO_TO_ONE)`. D3D12 tiene Y de NDC hacia arriba pero el RT con la fila 0 **arriba**, rango de z 0..1 (igual que ZERO_TO_ONE), sin viewport de altura negativa (eso es de Vulkan). Propuesta (ya aplicada en `vulkanizar`): el VS emite **`(x, -y, -z, w)`**. Así la fila *r* del RT D3D12 es exactamente la fila *r* del RT de GL: la lectura de vuelta (fila 0 = abajo) y `copiar()` no cambian, `SV_Position.y == gl_FragCoord.y` (la tijera del shader y `z` no se tocan), y la profundidad no cambia (`-z` ya deja z en [0,w]). Consecuencia: el triángulo de frente de la PICA (antihorario en GL) queda **horario** en D3D12 ⇒ **`FrontCounterClockwise = FALSE`** (el valor por defecto) y `RbEstado.cull`: 1→`D3D12_CULL_MODE_FRONT`, 2→`BACK`. Viewport normal `(0,0,W,H,0,1)`. Con GS el giro ya va en el VS (el GS solo copia posición). Los auxiliares (`giro_alta`, `pres_capa`) NO se tocaron: su orientación depende de a qué superficie se dibuje (back buffer de D3D12 es fila 0 arriba) — lo decide el backend (paso 3/7).
Riesgo anotado: la regla top-left de D3D vs la de GL en bordes exactos de píxel puede dar diferencias de 1 píxel en aristas; se mira en la prueba de píxel.
**Texturas/samplers**: `sampler2D` combinado ⇒ SPIRV-Cross genera `Texture2D tN : register(tN)` + `SamplerState _tN_sampler : register(sN)`; `tex0..2`=t0..t2/s0..s2, `luz_luts`=t3/s3 (igual que A: unidades 0-3). `texelFetch`→`Load`. `muestra(int, sampler2D, vec2)` se resuelve con parámetros separados (compila).
**Geometry shader**: DXIL `gs_6_0` correcto (solo con luz). Se conserva porque el flip de cuaternión necesita los 3 vértices; alternativa sin GS (interpolación manual con baricéntricas SM6.1) no daría los mismos LSB. Medir coste en el paso 9.
**Enteros/bitwise del TEV**: pasan tal cual (shift aritmético, `sign`, `min/max/clamp` enteros; `d255` sin división). **Verificado en ejecución real de D3D12 (WARP) — ver §6.**
**`discard`**: sale como `discard` HLSL en `ps_6_0`; con `gl_FragDepth`→`SV_Depth` se pierde early-Z, igual que en GL. Alpha test y tijera conservan el orden (antes de la niebla).
**Precisión**: **`-Gis` (IEEE estricto) obligatorio**. Sin él DXC marca 1 625 operaciones del VS más grande como `fast` (⇒ `nnan`: el driver puede borrar `isnan` de `pmul`, el "0·inf = 0" de la PICA); con `-Gis` hay 0. El TEV no usa float. Luz/niebla (float): comparar con GL en la prueba de píxel (tolerancia ≤1 LSB como hoy).

## 6. Equivalencia sin GPU de juego y SABOTAJES
1. **TEV en D3D12 real (WARP, CPU)** — `verif_tev_warp.py` + `warp_cs.exe`: toma el texto exacto del TEV de `raster_uber.c` (`rgba8`…`combinar`), lo pasa por glslang→SPIRV-Cross→DXC como `cs_6_0` y lo ejecuta en el adaptador WARP ("Microsoft Basic Render Driver", software; no usa la GPU) sobre las **332 recetas reales × 120 entradas aleatorias con bordes = 39 840 casos**; compara contra `tools\tev_ref.py`.
   Resultado limpio: **39 840/39 840 idénticos, 0 LSB**. Pureza del HLSL: sin float en las funciones enteras.
   Sabotajes (el shader alterado, mismo flujo): `d255 >>7` → **35 035 casos distintos**; `1-x` sin invertir → 5 102; buffer del combinador una etapa antes → 3 502; escala x4 como x2 → 1 975 (error máx 255 LSB cada uno). Comando: `py -I agentes_dx12\B\verif_tev_warp.py [-n 120] [--sabotaje 1..4]`.
2. **Verificador estático** (`cadena_shaders.py sabotaje`): control bueno pasa; `d255` con `>>7` (huella del TEV distinta), `d255` con float (pureza: tipo/literal float y división), modificador invertido (huella), error de sintaxis (glslang) → **los 4 alterados se detectan**.
3. `layouts --sabotaje` (offset +4) y `prueba_cache.exe sab` (DXIL truncado / sin firma rechazado) detectan lo suyo. `comparar-c`: volcador == `raster_uber.c`. `verif_vert_generador.py`: 21/21 `.vert` == generador actual.
4. `prueba_cache.exe`: **735 shaders buscados por el TEXTO GLSL** (hash FNV-1a C == hash Python del índice, DXIL sano); un texto inexistente cae al respaldo y vuelca el `.glsl`.

## 7. Entregables (todo en `agentes_dx12\B\`)
`cadena_shaders.py` (inventario, convertir, resumen, comparar-c, empaquetar, layouts, sabotaje) · `volcar_glsl.c/.exe` · `verif_tev_warp.py` + `warp_cs.c/.exe` · `verif_vert_generador.py` · `check_layout.c/.exe` · `cb_layouts.h` · `shaders_d3d12.c` (**borrador sin enlazar**: búsqueda por hash de texto en `cache_d3d12\`, validación del contenedor DXBC, respaldo uber, volcado de faltantes; `py -m ziglang cc -DSD_PRUEBA -c shaders_d3d12.c` compila limpio) · `prueba_cache.c/.exe` · `glsl\` (inventario) · `out\` (spv borrado; `.vk.glsl`, `.hlsl`, `.dxil`, `resultados.tsv`) · `cache_d3d12\` (DXIL con nombre = hash del texto, `indice.tsv`, `VERSION.txt`) · `terceros\`.
Comandos de re-ejecución (raíz del proyecto): `py -I agentes_dx12\B\cadena_shaders.py inventario && … convertir && … empaquetar && … layouts`. Recompilar utilitarios: `py -m ziglang cc -O1 -o agentes_dx12\B\volcar_glsl.exe agentes_dx12\B\volcar_glsl.c -Irecomp\render`; `warp_cs.exe` con `-ld3d12 -ldxgi -ldxguid`; `check_layout.exe` con `-Irecomp\render`.
Prueba de caché (desde `agentes_dx12\B`): `py -m ziglang cc "-DSD_DIR_CACHE=\"cache_d3d12\\\\\"" "-DSD_DIR_FALTAN=\"tmp\\\\\"" -o prueba_cache.exe prueba_cache.c && prueba_cache.exe sab`.

## 8. Pruebas pendientes (necesitan GPU / backend D3D12, NO se corrieron)
- **Píxel real GL vs D3D12** (paso 8): cuando exista el backend, compilar `agentes_noche\R\prueba_raster.c` contra el backend D3D12 y correr el mismo `guion.bin` con `set SM3DL_BACKEND=gl` y `set SM3DL_BACKEND=d3d12`: `prueba_raster.exe guion.bin salida_gl.bin` / `…d3d12.bin`; comparar. Exigencia: TEV **0 LSB**; luz/niebla ≤1 LSB; revisar aristas (regla top-left) y orientación/culling.
- Luz por fragmento (float, `texelFetch` sobre RG32F) no tiene referencia entera: solo se compara contra GL en esa prueba.
- Rendimiento del GS y de `SV_Depth` (sin early-Z) en la Intel UHD 770: paso 9.

## 9. Pedidos de integración (no edité nada fuera de `agentes_dx12\B*`)
1. **Agente A / `raster_backend.h`** (nota 6 de SHADERS): el "D3D12 debe voltear y en el viewport (o usar altura negativa)" ya **no hace falta ni existe en D3D12**: el VS convertido emite `-y`; viewport normal, `FrontCounterClockwise=FALSE`, cull 1→FRONT / 2→BACK. Sugerido corregir el comentario. El layout de `RbCb*` quedó verificado tal cual (incluye `_p0` de `RbCbLuz` y `RbLuz` con vec4).
2. **Backend D3D12** (`etapa_compilar`): sustituir la compilación por `sd_etapa_desde_texto(tipo, src, nombre)` de `shaders_d3d12.c` (hash = `fnv_texto(src)` = el mismo `hv/hf` del cache GL); GS = `G_FLIP.dxil`. Root signature: b0..b3, t0..t3, s0..s3. Input layout: `TEXCOORD<k>` float4 para los `v<k>` usados. Interfaz VS→PS: TEXCOORD0..5 (el 5, `cd`, solo lo lee el GS), SV_ClipDistance0, SV_Position; PS: SV_Target0 + SV_Depth.
3. **Copiar `agentes_dx12\B\cache_d3d12\` a `extraido\shaders\cache_d3d12\`** al integrar (9,6 MB; fuera del respaldo igual que `cache_gl`) y hacer que `ESTADO.md`/el empaquetado lo mencione.
4. **`raster_uber.c` (opcional)**: si alguien cambia `FRAG_UBER`/`GEOM_FLIP`/`VERT_ENVOLTORIO`, re-correr `inventario → convertir → empaquetar → layouts` (`BLOQUES` aborta si aparece un uniform nuevo; `_gs_d3d` aborta si cambia el cálculo del GS) y subir `CADENA_VERSION` + `SD_CADENA_VERSION`. Ningún cambio de `recomp\` es necesario hoy.
5. Para cubrir lo no visto en el censo: el volcado `desconocidos_d3d12\*.glsl` se convertirá con `cadena_shaders.py` (subcomando `faltantes`: pendiente, hoy se hace copiando el `.glsl` a `B\glsl\frag\` y añadiendo la fila al `INDICE.tsv`).
