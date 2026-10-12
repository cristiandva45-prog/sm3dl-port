# Brief — backend Direct3D 12 del raster (8 oct noche, 2 agentes a la vez: C y D)

Lee también `agentes_dx12\BRIEF_COMUN.md`: **todas sus reglas siguen** (en especial: NO correr el juego; solo compilar y
pruebas LIVIANAS de segundos). Responde y escribe en español.

## Qué hay ya (no re-derivar; léelo)
- Interfaz: `recomp\render\raster_backend.h` (agente A). Backend GL de REFERENCIA: `recomp\render\raster_backend_gl.c`
  (la semántica exacta de cada función está ahí: imítala). Capa común: `recomp\render\raster_gl.c` (cómo se llaman).
- Esqueleto D3D12 (sesión principal): `recomp\render\raster_backend_d3d12.c` = tipos compartidos `DxTex DxRT DxEtapa
  DxProg DxLectura` (los punteros Rb* de la interfaz se convierten con `DX_TEX(p)` etc.: el backend GL define `struct
  RbTex` en el MISMO archivo de compilación), estado común `dx` y la tabla. Se incluye al final de `raster_gl.c`
  (con `-DSM3DL_CON_D3D12`). **Prefijo `dx_`/`DX_` en todo** (mismo archivo que la capa común y el backend GL).
- Partes con RELLENO que cada uno reemplaza: `raster_d3d12_recursos.inc` (C) y `raster_d3d12_dibujo.inc` (D).
- Módulos D3D12 de la sesión principal, ya probados con sabotaje (`agentes_dx12\principal.md`):
  `d3d12_base.h/.c` (dispositivo, swap chain flip + objeto de latencia, **LISTA CONTINUA**: `d3d_lista()` la abre sola,
  `d3d_vaciar()` manda sin esperar y devuelve la fence, `d3d_esperar_valor`, anillos `d3d_subir` / `d3d_srv_reservar` /
  `d3d_smp_reservar` reciclados por fence, `d3d_atras_empezar/presentar`), `d3d12_recursos.h/.c` (texturas/RT/D24S8 en
  dos planos, `d3d_tex_subir`, lecturas `d3d_leer_*` con fence, liberación diferida, caché de PSO `d3d_pso_obtener`),
  `d3d12_presentador.h/.c` (base escalada + capas premultiplicadas; HLSL con d3dcompiler_47).
- Shaders (agente B, `agentes_dx12\B.md` — LÉELO: "Contrato HLSL", "Coordenadas", cbuffers): 741/741 GLSL → DXIL
  precompilados en `agentes_dx12\B\cache_d3d12\` (nombre = FNV-1a del TEXTO); borrador de carga `B\shaders_d3d12.c`
  (`sd_etapa_desde_texto`, `sd_programa`, uber de respaldo); layouts `B\cb_layouts.h`. El VS emite (x,-y,-z,w): fila r
  del RT D3D12 = fila r de GL (fila 0 = ABAJO de la PICA) → lecturas, tijera y z sin cambios; viewport normal,
  `FrontCounterClockwise=FALSE`; DXC con `-Gis`.

## Compilar
`py -I recomp\arranque\compilar.py --d3d12 -o sm3dl_<C|D>.exe` (≈30 s; enlaza d3d12_*.c y -ld3d12 -ldxgi -ldxguid
-ld3dcompiler_47). Debe compilar SIEMPRE con la parte del otro como esté (si el otro rompe la compilación, avísalo en tu
bitácora y espera/compila con su respaldo). 0 warnings nuevos con -Wall.

## Reparto
**C — `raster_d3d12_recursos.inc` (+ puede AGREGAR funciones a `d3d12_recursos.h/.c` sin romper las existentes ni
`recomp\render\prueba_d3d12_recursos.c`/`prueba_d3d12_pres.c`, que deben seguir pasando: compílalas y córrelas, son
de segundos):**
iniciar (dispositivo vía `d3d_iniciar(NULL,…)` sin ventana hasta `hacer_actual_dc`/`ventana_empezar`, que crean la
swap chain sobre el HWND del DC con `WindowFromDC`; luego `dx_dibujo_iniciar()` de D), listo/contexto/es_actual
(D3D12 no tiene contexto: 1 si listo), texturas (RGBA8/BGRA8/RG32F, **mips** — agrega soporte de niveles en
d3d12_recursos), `tex_enlazar` (guarda en `dx.tex[u]`/`dx.mues[u]`; el descriptor lo arma D al dibujar), RT (color
RGBA8 + D24S8 opcional, `rt_subir`, `rt_limpiar` con máscara, `rt_reducir` lineal, `rt_leer` síncrono con fila 0 =
ABAJO como GL (con la convención de B es la fila 0 del RT tal cual: verifícalo contra el GL), `rt_leer_ventana`,
`copiar` con escalado/volteo y destino NULL = buffer de atrás, `rt_volcar_bgra`), lecturas asíncronas (persistente:
puede devolver 0 en `*persistente_ok`), `girar` (afín sobre la copia en alta; HLSL propio con d3dcompiler_47 o el DXIL
de B `aux\giro_alta.*`), `ventana_empezar`/`pres_capa`/`presentar` (usa d3d12_presentador o su lógica; `presentar`
= `d3d_atras_presentar(intervalo)`), cronómetros (pueden quedar en 0 por ahora: anótalo).

**D — `raster_d3d12_dibujo.inc`:**
`dx_dibujo_iniciar` (firma raíz `dx.rs`: b0..b3 como CBV raíz, tabla SRV t0..t3, tabla de muestreadores s0..s3 — o
lo que exija el HLSL de B: manda el contrato de B), etapas/programas (DXIL desde la caché de B por hash del texto;
lleva la caché a `extraido\shaders\cache_d3d12\` — eso es un pedido de integración: deja el comando; puedes leerla de
`agentes_dx12\B\cache_d3d12\` mientras), `prog_cargar_cache`/`guardar` (pueden ser no-op: el DXIL ya está en disco),
`constantes` (memcpy al anillo con `d3d_subir(…, 256, &va)` → `dx.cb_va[bloque]`), `fijar_destino`, `fijar_estado`
(→ clave de PSO = prog + RbEstado sin blend_color/stencil_ref (dinámicos: OMSetBlendFactor/OMSetStencilRef) + formato
del destino + con/sin DS + layout de vértices + tipo de topología; `d3d_pso_obtener`), traducción de RbEstado (tablas
PICA → D3D12 de blend/ecuación/cmp/stencil op; **logic op**: D3D12 solo lo admite con RT UINT — COPY con blend
apagado = sin blend; los demás: avisar una vez y documentar la propuesta), `vertices_floats` (16 × float4 por vértice,
un input layout fijo), `vertices_crudos` (puede devolver 0 al principio = usa floats; si lo haces, layout por dibujo en
la clave del PSO), `dibujar` (lista/tira; ABANICO → lista de índices; índices de 32 bits por el anillo; arma la tabla
de SRV + muestreadores de `dx.tex/dx.mues` — RbMuestreador → D3D12_SAMPLER_DESC: wrap PICA, borde, lod, sesgo, mip).

## Verificación sin correr el juego
Cada uno arma una prueba LIVIANA propia en `agentes_dx12\<C|D>\` (exe aparte, sin ventana o una ventana chica unos
segundos) que use SU parte a través de la tabla `RasterBackend` y compare contra el backend GL o contra un valor
conocido, con un SABOTAJE que se vea fallar. Ideal (coordinad por bitácoras): el arnés de R `agentes_noche\R\prueba_raster`
/ el de A (`agentes_dx12\A\`) con `SM3DL_BACKEND=d3d12` — si es liviano (segundos, sin el juego), úsalo. Deja escrita
la "prueba pendiente" con el juego para la sesión principal.

## Archivos
C: `raster_d3d12_recursos.inc`, agregados a `d3d12_recursos.h/.c`, `agentes_dx12\C\`, `agentes_dx12\C.md`.
D: `raster_d3d12_dibujo.inc`, `agentes_dx12\D\`, `agentes_dx12\D.md`.
Nadie más toca `raster_backend_d3d12.c` (esqueleto), `raster_gl.c`, `raster_backend.h`, `d3d12_base.*`,
`d3d12_presentador.*`: si hace falta un campo en `dx` o un cambio ahí → pedido de integración en la bitácora (la sesión
principal lo aplica). Respaldo `.antes_dx12_<id>` antes de editar algo existente.

## Entrega
Bitácora completa + respuesta final de máximo 15 líneas (qué funciona medido, sabotajes, archivos, pendientes, pedidos).
