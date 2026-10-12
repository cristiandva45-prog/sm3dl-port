# Brief — gran actualización de TEXTURAS (9 oct 2026 noche, 7 agentes Sonnet a la vez: T1..T7)

Proyecto: port nativo a PC de Super Mario 3D Land (recompilación estática ARM11→C→x86-64). Raíz:
`C:\Users\usuario\Desktop\Decopilar\sm3dl-port\` (NO es git). Uso personal; nunca distribuir ROM/assets.
Backends de render: OpenGL (referencia) y Direct3D 12 (`SM3DL_BACKEND=d3d12`), misma capa común `recomp\render\raster_gl.c`.
Lee también `agentes_dx12\BRIEF_COMUN.md` (reglas de la casa) y, si tocas D3D12, `agentes_dx12\BRIEF_15.md`.

## Qué quiere el dueño
Mejores texturas: (1) filtrado anisotrópico, (2) sistema de texturas de REEMPLAZO por clave (como los emuladores),
(3) texturas en alta definición escaladas con IA LOCAL (Real-ESRGAN en su RTX 5050, gratis; NUNCA una API de pago),
primero una MUESTRA de ~20 para que él decida el estilo antes de procesar todo.

## REGLAS DURAS
1. **El dueño puede estar JUGANDO: NO corras el juego** ni toques `sm3dl_ajustes.ini` ni `sesion_juego\jugar\`. Solo
   compilar y pruebas livianas (segundos). Deja la "prueba con el juego" escrita con el comando exacto.
2. **Solo escribes en TUS archivos** (tabla abajo) + `agentes_tex\<id>\` + bitácora `agentes_tex\<id>.md` (desde el
   minuto 1; si existe, retoma). Cambio en archivo ajeno → `PEDIDO <id>:` en tu bitácora.
3. Respaldo `<archivo>.antes_<id>` antes de editar un archivo existente.
4. Todo verde necesita un SABOTAJE que se vea fallar.
5. Compilar: `py -I recomp\arranque\compilar.py --d3d12 -o "C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_tex\<id>\sm3dl_<id>.exe"`
   (ruta ABSOLUTA; ~20 s). Chequeo rápido: `-c -o <propio>.o` (NO `-fsyntax-only`: da un FileNotFound falso).
   `rb` es una MACRO en raster_gl.c: no lo uses como nombre. Python = `py` (con `-I`). Nunca matar procesos por nombre.
6. Otros agentes (H1, H2) están editando HOY: `recomp\gpu\gsp_interp.inc`, `recomp\render\interp.c`,
   `raster_d3d12_dibujar.inc`, `raster_d3d12_cb.inc`, `raster_d3d12_vertices.inc` y quizá partes de `raster_gl.c`
   (re-ejecución de intermedios). No toques esos; en `raster_gl.c` T2 edita SOLO `textura_para` y alrededores, con
   ediciones pequeñas y exactas.
7. Descargas (Real-ESRGAN, etc.): solo releases OFICIALES de GitHub, cada una en una carpeta NUEVA
   `agentes_tex\<id>\terceros\<nombre-version>\`, versión anotada. Nada de instaladores globales.
8. Calor: la GPU/CPU del dueño. Procesos pesados con prioridad baja y en lotes chicos.
9. Respuesta final: máximo 12 líneas, en español.

## CONTRATO (ya existe, compila: `recomp\render\texturas_hd.h` + relleno `texturas_hd.c`, ya en compilar.py)
- **Clave** de una textura = `fnv()` de raster_gl.c (FNV-1a por palabras de 32 bits) sobre los bytes CRUDOS del NIVEL 0
  en memoria del 3DS (antes de decodificar). OJO: el `h` actual de `textura_para` es sobre TODOS los niveles; la clave
  es solo el nivel 0 (reproducible fuera del juego desde los archivos del ROM).
- **Archivo**: `<raíz>\texturas_hd\tex_<w>x<h>_f<fmt>_<CLAVE %08X>.png` (w,h y fmt PICA ORIGINALES; el PNG puede ser
  k veces mayor, k entero, o del mismo tamaño si es una edición a mano).
- API: `texhd_activo/fijar`, `texhd_buscar(clave,w,h,fmt,&W,&H,&niveles,&rgba)`, `texhd_volcando/volcar`,
  `texhd_estadisticas` (ver el .h).
- Anisotrópico: `void raster_aniso_fijar(int n)` / `int raster_aniso(void)` (n = 1 apagado, 2, 4, 8, 16), definidas por
  T1 NO-static en `raster_backend_gl.c` (que se incluye siempre al final de raster_gl.c) y usadas por ambos backends.
- Ajustes nuevos en `sm3dl_ajustes.ini` (los escribe/lee T7): `aniso=1|2|4|8|16`, `texturas_hd=0|1`.
- Variables: `SM3DL_TEX_HD=0` apaga; `SM3DL_TEX_HD_DIR=<carpeta>` otra carpeta; `SM3DL_TEX_VOLCAR=<carpeta>`;
  `SM3DL_ANISO=<n>` fuerza.

## REPARTO
| Id | Archivos exclusivos | Tarea |
|---|---|---|
| T1 | `recomp\render\raster_d3d12_mues.inc`, la parte de muestreadores de `recomp\render\raster_backend_gl.c` | Anisotrópico en D3D12 (`D3D12_FILTER_ANISOTROPIC`/`MaxAnisotropy`, solo si min/mag lineal; con mip punto: elegir el filtro que lo respete) y en GL (`GL_TEXTURE_MAX_ANISOTROPY`, core 4.6 / EXT). Define `raster_aniso_fijar/raster_aniso`. No aplicar a LUTs, a la unidad de giro ni a capas de interfaz. Prueba sobre un plano inclinado sintético (D3D12 y GL), ve que cambie con n y que n=1 = idéntico a hoy byte a byte; sabotaje. |
| T2 | `recomp\render\raster_gl.c` (SOLO `textura_para` y lo que necesite cerca) | Gancho: calcular la clave (nivel 0 crudo), `texhd_volcar` si se está volcando, `texhd_buscar` y si hay HD subir esos niveles con `rb->tex_cargar_mips(…, W, H, niveles, rgba)`. La caché `g_tex` debe distinguir HD de original (encender/apagar en caliente sin reiniciar). Revisa que nada asuma tamaño de textura = tamaño PICA (texelFetch, cálculos de LOD, `tex_niveles`); si algo lo asume, arréglalo o documéntalo. Línea de log con `texhd_estadisticas` cada N. Prueba sin juego con un .png falso + clave conocida (unidad de prueba propia). |
| T3 | `tools\texturas_hd_mapa.py` (nuevo) + `texturas_hd_fuente\` (nuevo) | Desde lo ya extraído del ROM (`extraido\romfs`, `extraido\texturas_png\` = 1.660 carpetas, `extraido\pica_materiales.tsv`, los extractores de `tools\`) reconstruir los bytes CRUDOS del nivel 0 de cada textura tal como los sube el juego, calcular la CLAVE y generar `texturas_hd_fuente\tex_<w>x<h>_f<fmt>_<CLAVE>.png` (el original decodificado con su nombre de reemplazo) + `texturas_hd_fuente\mapa.tsv` (clave, w, h, fmt, archivo del ROM, nombre de la textura, nivel/escena). Verifica decodificando y comparando con `extraido\texturas_png` (0 px distintos) y deja escrita la prueba con el juego (`SM3DL_TEX_VOLCAR`) que confirma que las claves coinciden con las de tiempo de ejecución. Riesgo a vigilar: formatos PICA (ETC1/ETC1A4/A8/LA4…) y swizzle: la clave es sobre el dato CRUDO. |
| T4 | `recomp\render\texturas_hd.c` (reemplaza el relleno; el .h es el contrato: si hace falta cambiarlo, PEDIDO a la sesión principal) | Carga de PNG (decodificador propio o stb_image de fuente oficial en el mismo .c), índice de la carpeta al primer uso (no tocar disco por cada búsqueda), recuerdo de claves ausentes, generación de mips por caja 2x2 en espacio lineal (alfa premultiplicado al reducir para que no salgan bordes oscuros), límite de memoria (LRU), tamaños no múltiplos, convención de filas igual que `texturas.c`, volcado (`texhd_volcar`, PNG propio), estadísticas. Precarga en un hilo aparte opcional (si la haces, sin carreras). Prueba unitaria propia (PNGs sintéticos, mips correctos, ausentes baratos) + sabotaje. |
| T5 | `agentes_tex\T5\` (+ `agentes_tex\T5\terceros\`) | Real-ESRGAN LOCAL: bajar el release oficial de `xinntao/Real-ESRGAN` (realesrgan-ncnn-vulkan, Windows) y probar 2 modelos (p. ej. `realesrgan-x4plus` y `realesrgan-x4plus-anime`/`realesr-animevideov3`) sobre una MUESTRA de ~20 texturas variadas de `extraido\texturas_png\` (suelo, pasto, ladrillo, bloques ?, árboles, agua, Mario/ropa, metal, cielo, una con alfa, un texto/HUD). Alfa: escalar RGB y alfa por separado. Repetibles (ojo con texturas que se repiten en mosaico: escalar con borde envuelto para que no salgan costuras). Entrega una HOJA de comparación (PNG grande: original ampliado vecino-más-cercano vs. modelo A vs. modelo B, con etiquetas) en `agentes_tex\T5\muestra\` + tiempos en la RTX 5050. Prioridad baja, lotes chicos. Deja el comando para el lote completo, sin correrlo. |
| T6 | `tools\clasificar_texturas.py` (nuevo) + `texturas_hd_reglas.tsv` (nuevo) | Clasificar las texturas extraídas para el escalado: `escalar` / `escalar_mosaico` (se repite: borde envuelto) / `alfa_aparte` / `excluir` (fuentes, texto, HUD, íconos, LUTs, ruido, gradientes de 1 px, < 16 px, normal maps si hay) / `nitido` (pixel art que debe escalar vecino-más-cercano). Usa nombres de archivo/archivo del ROM, tamaño, formato, alfa, n.º de colores, uso en `pica_materiales.tsv` (wrap repeat = mosaico). Entrega el TSV + resumen con cifras + 1 hoja con ejemplos de cada clase. |
| T7 | `recomp\render\ventana_ui.c` / `ventana.c` (solo el menú de ajustes y la lectura/escritura del ini) | Opciones en el menú (tuerca/Esc): "Filtro anisotrópico: no / 2x / 4x / 8x / 16x" → `raster_aniso_fijar`; "Texturas HD: no / sí" → `texhd_fijar` (+ forzar re-subida: si T2 expone una función, úsala; si no, PEDIDO T2). Ini `aniso=`, `texturas_hd=`, con valores por defecto si no están (aniso=8, texturas_hd=1). Mismo estilo visual que las opciones existentes. Prueba sin juego si el menú tiene arnés; si no, compila y deja la prueba escrita. |

## Entrega común
Bitácora completa (qué, cifras, sabotajes, archivos, pendientes, pedidos). Al final la sesión principal integra, enlaza
un exe con todo y, con OK del dueño, prueba en el juego: volcado → claves coinciden → reemplazo → muestra de HD.
