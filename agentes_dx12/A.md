# Agente A - tanda D3D12, paso 1: separar "que dibujar" (PICA200) de "como dibujarlo" (backend)

Estado (8 oct 2026): **COMPLETO y verificado SIN correr el juego** (arnes de equivalencia 21/21 escenarios IGUALES byte a byte,
sabotajes detectados). Pendiente solo la prueba con el juego real (abajo, script listo).

## Que quedo
- `recomp\render\raster_backend.h` (NUEVO): la interfaz. Tabla `RasterBackend` de ~50 funciones + tipos (`RbEstado`, bloques de
  constantes `RbCbVertice/Fragmento/Niebla/Luz`, `RbVerticesCrudos`, `RbMuestreador`, `RbGiro`) + 9 decisiones de diseno
  documentadas en la cabecera (PSO inmutable, constant buffers, descriptores, lecturas con fence, pases, **como se pasan los shaders
  a un backend: fuente GLSL + clave (hv, hf, gs) + layout de constantes** -> esto es lo que consume el agente B).
- `recomp\render\raster_backend_gl.c` (NUEVO, ~1.160 lineas): el codigo GL movido, misma secuencia de llamadas. Se incluye con
  `#include` AL FINAL de `raster_gl.c` (no hizo falta tocar `compilar.py`). La capa comun NO puede nombrar GL: compila sin las
  cabeceras de GL (garantia por compilacion, no por disciplina).
- `recomp\render\raster_gl.c` (2.723 -> ~2.200 lineas): capa comun. `presentador_gl.inc`: ahora solo habla con el backend.
  `raster_gl.h`: solo comentario. `raster_uber.c`: sin cambios (los shaders siguen siendo texto GLSL; ver abajo).
- Seleccion `SM3DL_BACKEND=gl|d3d12`: `elegir_backend()` al final de raster_gl.c; `d3d12` hoy es un stub (`rb_d3d12_obtener()` devuelve
  NULL) que loguea "NO IMPLEMENTADO todavia ... uso gl" y cae a gl. Desconocido -> aviso y gl. Log `backend de GPU: gl` al primer uso.
- Sabotaje `SM3DL_BACKEND_SABOTAJE=n` (solo backend GL): 1 = ningun dibujo escribe el canal azul (cambia cualquier imagen);
  2 = la base se corre 1 px a la derecha al copiarla a la ventana (camino de presentacion por GPU, `SM3DL_FOTO_VENTANA`);
  3 = las dos. Sin definir = nada.

## Como se dividio (que decodifica la capa comun / que ejecuta el backend)
Comun (raster_gl.c): registros PICA -> `RbEstado` (`estado_de`), -> bloques de constantes (`subir_uniforms`, `subir_luz`),
TEV/clave de fragment shader/cache de programas (`vs_para`, `fs_para`, `programa_para`), texturas (decodificar, cache por hash,
`muestreador_de`), LUTs de luz (cache por contenido, filas), niebla, vertices (`armar_vertices` CPU, `armar_crudo` -> `RbVerticesCrudos`),
render targets y su sincronia con la memoria del 3DS (`rt_para`, `bajar_color`, `subir_color`, diferidos, MemoryFill), pantalla en alta
(mapa afin, anillo de lecturas), cronometros. Backend: todo lo que toca la GPU.

Mapa de cada llamada GL que se movio -> funcion del backend (el inventario completo antes/despues esta en `A\inventario_gl.txt`:
**104 funciones GL distintas antes, 104 despues, ninguna perdida ni nueva**; 451 sitios -> 338 porque lo repetido se unifico):

| GL de antes (donde) | Backend |
|---|---|
| `iniciar_gl` entero (ventana oculta, wgl, carga de ~75 punteros, ClipControl, VAO/VBO/EBO del camino CPU, PixelStore) | `iniciar` |
| `contexto_actual` (wglGetCurrentContext/MakeCurrent), `crono_reporte` (wglGetCurrentContext) | `contexto_actual`, `es_actual` |
| `raster_gl_hacer_actual` (GetPixelFormat/SetPixelFormat/wglMakeCurrent) | `hacer_actual_dc` |
| `glGetError` (log de dibujar) | `ultimo_error` |
| `compilar` (CreateShader/ShaderSource/CompileShader/GetShaderiv/InfoLog/DeleteShader) | `etapa_compilar`, `etapa_destruir` |
| `binario_cargar/guardar/ruta/iniciar` (ProgramBinary, GetProgramBinary, GetString) | `prog_cargar_cache`, `prog_guardar_cache` |
| `programa_para`: CreateProgram/ProgramParameteri/AttachShader/LinkProgram/GetProgramiv/InfoLog, GetUniformLocation, UseProgram + Uniform1i de las unidades | `prog_enlazar` (+ `prog_ubicar` interno, tambien en cache) |
| `DeleteProgram`, `DeleteShader` (cache llena / olvidar) | `prog_destruir`, `etapa_destruir` |
| `UseProgram` (dibujar) | `prog_usar` |
| `subir_uniforms`/`subir_luz`: ~60 Uniform* | `constantes(prog, RB_BLOQUE_V/F/NIEBLA/LUZ, &bloque)` (mismos valores, mismos Uniform*) |
| `aplicar_estado`: Disable/Enable CULL, CLIP_DISTANCE0, DEPTH, STENCIL, BLEND, LOGIC_OP, DepthFunc/Mask, Stencil*Separate, ColorMask, Blend*, LogicOp | `fijar_estado(RbEstado)` (tablas FUNC_PRUEBA/FACTOR/ECUACION/LOGICA/STENCIL_OP se mudaron) |
| `BindFramebuffer(t->fbo)` + `glViewport` (dibujar) | `fijar_destino(rt, viewport)` |
| `armar_crudo` GL: VAO por layout (cache 128), VertexAttribFormat/Binding, BufferData, BindVertexBuffer, VertexAttrib4f | `vertices_crudos(RbVerticesCrudos)` |
| `dibujar` camino float: BindVertexArray/BindBuffer/BufferData | `vertices_floats` |
| `dibujar`: BindBuffer(ELEMENT)/BufferData/DrawElements/DrawArrays | `dibujar(topologia, n, indices o NULL)` |
| `rt_para`: GenTextures/TexImage2D/TexParameteri, Renderbuffer*, Framebuffer*, CheckFramebufferStatus | `rt_crear(w,h,con_ds,banderas)` |
| `rt_para`/`tras_fill`: Disable(SCISSOR)/DepthMask/StencilMask/ColorMask/Clear* | `rt_limpiar(mascara,color,z,stencil)` |
| `destruir_rt` (DeleteFramebuffers/Renderbuffers/Textures) | `rt_destruir` |
| `subir_color` (BindTexture + TexSubImage2D) | `rt_subir` |
| `fbo_nativo` + `ligar_nativo` (Blit lineal a un FBO a tamano nativo) | `rt_reducir` |
| `bajar_color`, `raster_alta_sinc`, `alta_ref_cpu`, instantaneas (verif.): ReadPixels sincronos | `rt_leer` (RGBA/BGRA) |
| `copiar_alta`, instantaneas, `raster_alta_a_ventana`, `raster_pres_guardar`, `raster_pres_base` (BlitFramebuffer + binds) | `copiar(dst o NULL=ventana, src, rect, rect, lineal)` |
| `completar_dif`/`transfer_diferido`/`antes_de_leer`: Gen/Bind/BufferData PBO, ReadPixels(0), FenceSync, Flush, ClientWaitSync, GetSynciv, DeleteSync, MapBufferRange/Unmap | `lectura_emitir`, `lectura_lista`, `lectura_esperar`, `lectura_cerrar`, `lectura_mapear`, `lectura_desmapear` |
| `raster_alta` (anillo de PBO persistentes: BufferStorage + MapBufferRange coherente, rehacer si no alcanza) | `lectura_emitir(..., persistente)` + `lectura_mapa_persistente` |
| `giro_listo` (compilar/enlazar giro_alta, VAO) + `raster_alta_sinc`/`alta_girar` (ActiveTexture 5, Bind, TexParameteri, Uniform*, DrawArrays) | `girar(dst, alta, RbGiro)` |
| `textura_para`: GenTextures/BindTexture/TexImage2D por nivel/BASE_LEVEL/MAX_LEVEL | `tex_cargar_mips` |
| `parametros_textura`: TexParameteri/f/fv | `tex_enlazar(unidad, tex, RbMuestreador)` |
| `preparar_unidad`: ActiveTexture(k) | `tex_enlazar(k, NULL, NULL)` |
| LUTs de luz: GenTextures/TexImage2D RG32F/TexSubImage2D/ActiveTexture(3) | `tex_crear(RG32F)`, `tex_subir`, `tex_enlazar(3, ...)` |
| `raster_pres_subir` (GenTextures LINEAR/CLAMP, TexImage2D BGRA, PixelStore, ROW_LENGTH, TexSubImage2D) | `tex_crear(BGRA8, LINEAR_CLAMP)`, `tex_subir(..., fila_px)` |
| `raster_pres_empezar` (Bind 0, Viewport, Disables, ClearColor, Clear) | `ventana_empezar` |
| `raster_pres_capa` (programa de la capa, blend ONE/ONE_MINUS_SRC_ALPHA, VAO, Draw) | `pres_capa` |
| `raster_pres_mostrar` (wglSwapIntervalEXT, SwapBuffers) | `presentar` |
| `raster_pres_leer` (ReadBuffer(BACK), ReadPixels BGRA) | `rt_leer_ventana` |
| `glGetTexImage` (verificacion de la API de textura) | `rt_volcar_bgra` |
| `gq_*` (GenQueries/BeginQuery/EndQuery/GetQueryObject*) | `gpu_crono_ini/fin/leer` |

Cambios deliberados (no alteran lo que se dibuja): (1) `rt_crear` chequea FBO completo solo para RT con D24S8, como antes;
(2) `copiar` siempre desactiva tijera y pone ColorMask total y deja ligado el FBO 0 (antes algunos sitios lo hacian y otros no;
cada consumidor vuelve a fijar su estado); (3) los mips de una textura se decodifican TODOS antes de subirlos (antes: decodificar
y subir nivel a nivel; mismo resultado, ~33 % mas de memoria temporal); (4) `PACK_ALIGNMENT=4` solo en lecturas BGRA (irrelevante:
todos los pixeles son de 4 bytes); (5) los bloques de constantes son layout de cbuffer; el GL los reparte en Uniform* (nada de std140/UBO).

## Verificacion (todo SIN correr el juego)
1. Compila: `py -I recomp\arranque\compilar.py -o sm3dl_A.exe` -> 0 errores, 0 warnings (`-Wall`; el baseline tambien 0), tras cada
   etapa. Etapas reales: (a) cabecera + backend compilado SOLO (`A\prueba_backend_solo.c`, `-Wall -Wextra` limpio); (b) migracion de la
   capa comun con `A\tools\migrar_raster.py` (reemplazos exactos: aborta si el texto viejo no esta una sola vez), compilando y
   revisando el diff (`A\diff_raster_gl.txt`); (c) presentador + seleccion + sabotaje. Una mezcla comun/backend en estados
   intermedios exigia duplicar la tabla de punteros GL, por eso la migracion fue de una vez, con el backend ya aislado y compilado.
2. Inventario de llamadas GL (arriba): 104 = 104 funciones, ninguna perdida (`A\tools\inventario_gl.py`).
3. **Arnes de equivalencia** (`A\prueba_equiv.c` + `A\tools\equiv.py`, `construir_equiv.py`): parte del arnes de R
   (agentes_noche\R\prueba_raster.c: raster_gl.c REAL + pica.c + gsp.c, VRAM falsa, GPU real, ventana oculta de 64x64 por unos
   segundos; NO es el juego). Se compilan DOS arneses: `equiv_antes.exe` contra los respaldos `.antes_dx12_A` (`A\antes\`) y
   `equiv_nuevo.exe` contra el codigo nuevo; mismo guion de registros PICA -> la salida (pixeles del RT, memoria codificada de
   los 5 formatos, pantalla en alta girada, presentacion con ranuras/capas/base) se compara BYTE A BYTE. Resultado
   (`A\resultado_equiv.txt`): **21/21 IGUALES**: tev, tev_uber, estado (150 dibujos con blend/logic op/depth/stencil/cull/tijera/alpha/
   mascara/formatos de profundidad al azar), mips (40 texturas con filtros/envolturas/borde/LOD al azar), luz (+uber; 8 luces, 24 LUTs,
   niebla, GS de flip), vertices (arrays, elements u8/u16, camino CPU, sin elementos, topologias lista/tira/abanico), memoria (los 5
   formatos de color, MemoryFill completo/parcial/profundidad, RT que cambia de forma), alta x2/x3 (diferido + giro GPU + lectura
   asincrona, con y sin cero copia, sincrona, CPU, VERIFICAR), pres x2/x4, diferido apagado (este ultimo da salida vacia: solo prueba
   que el interruptor sigue igual). Cache de programas en disco: mismos nombres y mismos bytes que antes, y cada version carga la
   cache escrita por la otra. Todo con `gl error 0x0`. (Nota: la lectura asincrona de la pantalla en alta NO es determinista por
   diseno: entrega el cuadro anterior si la GPU no termino; el arnes pone `glFinish()` entre las dos llamadas para fijarlo. Sin eso el
   exe de ANTES ya difiere de si mismo entre corridas.)
4. **Sabotajes** (la comparacion debe fallar): `--sabotaje 1` -> 7/7 escenarios DISTINTOS; `--sabotaje 2` -> pres_x2/pres_x4
   DISTINTOS y el control tev IGUAL (como debe: ese sabotaje solo toca la presentacion). `comparar_capturas.py` (PNG/BMP, 0 px exacto)
   probado contra una captura vieja distinta: detecta 91.542 px.
5. `SM3DL_BACKEND=d3d12|D3D12|xyz|gl|(vacio)`: avisos correctos y salida identica en el arnes.

## Hallazgos (no tocados, para decision)
- **Latente, ya existia** (`dibujar` -> `subir_uniforms` -> `preparar_unidad` -> `textura_para` -> `antes_de_leer` -> `bajar_color`): si una
  textura muestreada es un RT con dibujo pendiente, `bajar_color` deja ligado el FBO de ESE RT y el dibujo en curso sale ahi, no en su
  destino. La refactorizacion lo CONSERVA (identico comportamiento, a proposito). Arreglo propuesto cuando se quiera cambiar
  comportamiento: llamar `fijar_destino` DESPUES de preparar las texturas (en D3D12 el orden de OMSetRenderTargets lo exige igual).
- `ventana_gpu.c` recibe `unsigned tex_gl` de `raster_alta_textura`: es un id de textura GL (`rt_id_nativo`), no sirve en D3D12. Hoy
  no se usa para dibujar (se usa `raster_pres_base`); en el paso 7 cambiar la firma a un handle opaco.

## Para el agente B (shaders): lo que el backend recibe
Ver el punto 6 de `raster_backend.h` (autoritativo). Resumen: `etapa_compilar(RB_ETAPA_VS|FS|GS, texto GLSL 4.50, nombre)`;
VS = `.vert` generado + `envolver_vert` + `VERT_ENVOLTORIO` (omap, clip, bloque de salida V); FS = cabecera de especializacion +
`FRAG_UBER`; GS = `GEOM_FLIP`; clave = (hash FNV del texto VS, del FS, gs). Constantes: 4 bloques con layout de cbuffer
(`RbCbVertice` b0, `RbCbFragmento` b1, `RbCbNiebla` b2, `RbCbLuz` b3; arrays densos = int4/uint4/float4[]); texturas t0..t2 PICA, t3 LUTs.
Entradas del VS: 16 locations float4 (`RbVerticesCrudos.layout`). z de clip en [0, w]; y de la PICA hacia arriba (voltear en D3D12);
abanico de triangulos -> el backend lo convierte.

## PRUEBA PENDIENTE para la sesion principal (NO corrida)
```
py -I recomp\arranque\compilar.py -o sm3dl_A.exe                    # ya compilado (recomp\arranque\sm3dl_A.exe)
py -I agentes_dx12\A\tools\compilar_antes.py                         # ya compilado: recomp\arranque\sm3dl_A0.exe = arbol actual + raster de ANTES
powershell -File agentes_dx12\A\prueba_pendiente_juego.ps1 -Resolucion 1     # luego -Resolucion 2 (y 3/4 si se quiere)
```
El script corre la misma partida (`sesion_juego\j8\partida.txt`, TURBO 3, ventana oculta, `SM3DL_CAPTURAS`) con: `sm3dl_A0.exe` dos veces
(control del piso de ruido; DEBE dar 0 px), `sm3dl_A.exe`, `sm3dl_A.exe` con `SM3DL_BACKEND=d3d12` (cae a gl) y `sm3dl_A.exe` con
`SM3DL_BACKEND_SABOTAJE=1`; compara las carpetas con `comparar_capturas.py` (EXACTO). Criterio: antes1==antes2, antes==nuevo,
antes==nuevo_d3d12 con 0 px; antes vs sabotaje1 debe DETECTAR diferencia (`--esperar-diferencia`). Va con `SM3DL_SIN_DIFERIDO=1` y
`SM3DL_ALTA_ASINC=0` para que dos corridas del mismo exe sean comparables. Opcional: camino de presentacion por GPU con ventana real +
`SM3DL_FOTO_VENTANA` (BMP) y el sabotaje 2. Despues, medir velocidad contra A0 (el backend agrega una llamada indirecta por funcion; el
costo esperado es despreciable frente al driver, pero no esta medido).

## Archivos
Tocados: `recomp\render\raster_gl.c`, `presentador_gl.inc`, `raster_gl.h` (solo comentario). Nuevos: `recomp\render\raster_backend.h`,
`raster_backend_gl.c`. Respaldos: `*.antes_dx12_A` (raster_gl.c, raster_uber.c, presentador_gl.inc, raster_gl.h). Exes: `recomp\arranque\sm3dl_A.exe`
(nuevo), `sm3dl_A0.exe` (linea base). Trabajo en `agentes_dx12\A\`: `prueba_equiv.c`, `prueba_backend_solo.c`, `prueba_pendiente_juego.ps1`,
`resultado_equiv.txt`, `inventario_gl.txt`, `diff_raster_gl.txt`, `antes\` (copia de los respaldos para el arnes), `trabajo\` (temporales),
`tools\` (util.py, migrar_raster.py, inventario_gl.py, construir_equiv.py, equiv.py, comparar_capturas.py, compilar_antes.py).

## Pedidos de integracion
Ninguno obligatorio (compilar.py no cambia: el backend va por `#include`). Sugeridos para pasos siguientes: (1) cuando exista el backend
D3D12, o se lista su .c en compilar.py o se `#include` desde `raster_gl.c` (el hueco esta marcado en `elegir_backend`); (2) paso 7:
quitar el id de textura GL de `raster_alta_textura` (ver hallazgos); (3) mencionar `SM3DL_BACKEND` en el menu/ajustes cuando D3D12 exista.
