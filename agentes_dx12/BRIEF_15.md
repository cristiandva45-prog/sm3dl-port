# Brief — tanda de 15 agentes (9 oct 2026): terminar el backend Direct3D 12

Lee ANTES, en este orden: `agentes_dx12\BRIEF_COMUN.md` (reglas duras: TODAS siguen), `agentes_dx12\BRIEF_BACKEND.md`
(qué hay ya, contrato con B, semántica), `recomp\render\raster_backend.h` (interfaz) y `agentes_dx12\principal.md`.
El backend GL de REFERENCIA es `recomp\render\raster_backend_gl.c`: la semántica de cada función es la suya.
Responde y escribe en español.

## Qué cambió hoy
Las dos partes (`raster_d3d12_recursos.inc` y `raster_d3d12_dibujo.inc`) son ahora ÍNDICES de la sesión principal
que incluyen 12 subarchivos, uno por agente, cada uno con su relleno (todo falla con aviso). El orden de inclusión
es C1..C7 y después D1..D5. **Una función de otra parte se usa con un prototipo `static` propio arriba de tu archivo**
(repetir el prototipo es legal; la definición es del dueño de la parte). Nunca definas una función de otra parte.

## Reparto (dueño EXCLUSIVO de cada archivo; nadie más escribe ahí)
| Id | Archivo(s) | Qué |
|---|---|---|
| C1 | `raster_d3d12_init.inc` | iniciar (`d3d_iniciar(NULL,…)` sin ventana, luego `dx_dibujo_iniciar()`), listo/contexto/es_actual, `hacer_actual_dc` (swap chain sobre `WindowFromDC`), ultimo_error, `ventana_empezar`, `pres_capa`, `presentar` (con `d3d12_presentador`) |
| C2 | `raster_d3d12_tex.inc` + **único** que agrega a `d3d12_recursos.h/.c` | tex_crear/destruir/subir/cargar_mips (RGBA8/BGRA8/RG32F, MIPS). Si otro agente necesita algo en d3d12_recursos, te lo pide en su bitácora: revisa `agentes_dx12\*.md` buscando "PEDIDO C2" en cada hito |
| C3 | `raster_d3d12_mues.inc` | `tex_enlazar` + traducción `RbMuestreador` → `D3D12_SAMPLER_DESC` (wrap PICA 0-7, borde, lod, sesgo 1.4.8, mip). Exporta `static void dx_mues_desc(const RbMuestreador*, D3D12_SAMPLER_DESC*)` para D5 |
| C4 | `raster_d3d12_rt.inc` | rt_crear (RGBA8 + D24S8 opcional), destruir, rt_subir, rt_limpiar con máscara, rt_id_nativo |
| C5 | `raster_d3d12_copiar.inc` | copiar (escalado/volteo, destino NULL = buffer de atrás; CopyTextureRegion si coincide), rt_reducir (lineal), girar (afín; HLSL propio con d3dcompiler_47 o el DXIL de B `aux\giro_alta.*`). Su propia firma raíz/PSO de blit |
| C6 | `raster_d3d12_lecturas.inc` | rt_leer (fila 0 = ABAJO, comparar contra GL), rt_leer_ventana, rt_volcar_bgra, todas las `lectura_*` (persistente puede dar `*persistente_ok = 0`) |
| C7 | `raster_d3d12_crono.inc` | cronómetros por timestamp queries (RB_GQ_*), equivalentes a los del GL |
| D1 | `raster_d3d12_prog.inc` | `dx_dibujo_iniciar` (firma raíz `dx.rs` según el contrato de B), etapas/programas desde la caché DXIL de B por hash del texto, uber de respaldo, prog_usar |
| D2 | `raster_d3d12_cb.inc` | `constantes` (anillo `d3d_subir(…,256,&va)` → `dx.cb_va[bloque]`, layout = `B\cb_layouts.h`, verificar offsets con prueba), `fijar_destino` |
| D3 | `raster_d3d12_estado.inc` | `fijar_estado`: tablas PICA → D3D12 (blend, ecuación, cmp, stencil op, cull, máscara), logic op (COPY = sin blend; resto: aviso + propuesta). Exporta `static void dx_estado_a_desc(const RbEstado*, D3D12_GRAPHICS_PIPELINE_STATE_DESC*)` y `static uint64_t dx_estado_clave(const RbEstado*)` para D5 |
| D4 | `raster_d3d12_vertices.inc` | vertices_floats (16 × float4, layout fijo) y vertices_crudos (layout por dibujo en `dx.vb_elems` + `dx.vb_layout_hash`; puede empezar devolviendo 0) |
| D5 | `raster_d3d12_dibujar.inc` | `dibujar`: arma la clave de PSO (prog + estado + formato destino + DS + layout + topología) con `d3d_pso_obtener`, tablas SRV + muestreadores desde `dx.tex/dx.mues` (usa `dx_mues_desc` de C3), blend factor / stencil ref dinámicos, abanico → lista de índices, índices de 32 bits por el anillo |
| E1 | `tools\precompilar_d3d12.py` (nuevo) + `agentes_dx12\E1\` | llevar la caché DXIL a `extraido\shaders\cache_d3d12\` y que se pueda regenerar de cero desde los materiales del ROM (lista de programas de `programas.tsv` + los textos que arma la capa común); deja el comando exacto. Pedido de integración para que D1 lea de ahí |
| E2 | `agentes_dx12\E2\` | paso 8: arnés de comparación por píxel GL vs D3D12 SIN el juego (reusa el de A `agentes_dx12\A\` y el de R `agentes_noche\R\prueba_raster`): mismos escenarios por la tabla `RasterBackend` en ambos backends, tolerancia ±1 en caminos float, sabotaje. Mientras las partes estén en relleno, prepara y prueba el arnés con GL vs GL + sabotaje; córrelo contra D3D12 cuando las partes avancen (lee sus bitácoras) |
| E3 | `recomp\gpu\gsp_interp.inc` (solo `alto_*`) | modo Monitor en GL: línea de tiempo = nº de cuadro × 33,367 ms en `alto_cerrar` en vez de la hora de cierre real, + `desfase` para los tirones (diseño probado en `principal.md`, "Prototipo del paso 7"). Detrás de `SM3DL_ALTO_LINEA=1` (default apagado). Prueba con el simulador del prototipo, NO con el juego. Exe propio `sm3dl_E3.exe` |

## Compilar sin calentar la laptop (somos 15)
- ⚠️ (aviso de C7) `zig cc -fsyntax-only` da "FileNotFound": usar `-c -o agentes_dx12\<id>\chequeo.o`. Y **no uses `rb`
  como nombre de nada** (es macro en `raster_gl.c:48`; ya rompió la unidad una vez).
- Chequeo rápido (lo normal, segundos): solo la unidad del raster,
  `py -m ziglang cc -fsyntax-only -Wall -DSM3DL_CON_D3D12 -Irecomp\render -Irecomp <resto de -I que use compilar.py> recomp\render\raster_gl.c`
  (mira en `recomp\arranque\compilar.py` las banderas exactas y anótalas en tu bitácora).
- Enlace completo `py -I recomp\arranque\compilar.py --d3d12 -o "C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\<id>\sm3dl_<id>.exe"`
  SOLO en hitos (**ruta ABSOLUTA**: una relativa se resuelve desde `recomp\arranque`; ~20 s). Verificado el 9 oct: el
  conjunto partido enlaza (`agentes_dx12\principal\sm3dl_partido.exe`). Si sale `WinError 4551` = Smart App Control
  se reencendió: anótalo y avisa, no lo esquives.
- **Tu archivo nunca queda sin compilar**: edita, chequea, y si rompe arréglalo en el acto. Si lo que rompe es la parte
  de OTRO, anótalo en tu bitácora ("ROTO POR <id>") y sigue con un chequeo de tu archivo aislado.
- Pruebas propias LIVIANAS (segundos, sin el juego) en `agentes_dx12\<id>\`, con exe aparte que use tu parte a través
  de la tabla `RasterBackend` o directo, contra GL o un valor conocido, **con un SABOTAJE que se vea fallar**.

## Coordinación
- Bitácora `agentes_dx12\<id>.md` desde el minuto 1 y en cada hito (si existe, retoma desde ahí).
- Pedidos a otro agente: una línea `PEDIDO <id_destino>: …` en TU bitácora. Revisa `grep -l "PEDIDO <tu_id>" agentes_dx12\*.md` en cada hito.
- Campos nuevos en el estado común `dx` (raster_backend_d3d12.c, de la sesión principal): no lo edites; pon tu estado en
  un `static struct` propio con prefijo `dx_<parte>_`, y si de verdad hace falta compartirlo, `PEDIDO principal:`.
- Prefijo `dx_`/`DX_` en todo (mismo archivo de compilación que la capa común y el backend GL).
- NO correr el juego. Deja la "prueba pendiente con el juego" escrita con el comando exacto.

## Entrega
Bitácora completa (hecho, cifras, sabotajes, archivos, pendientes, pedidos). Respuesta final: máximo 15 líneas.
