# Brief común — paso a Direct3D 12 (8 oct 2026, 2 agentes a la vez: A y B)

Proyecto: port nativo a PC de Super Mario 3D Land por RECOMPILACIÓN ESTÁTICA ARM11→C→x86-64. Ya es jugable
(W1/W2, 30/60/Monitor 144 Hz con interpolación). Raíz: `C:\Users\usuario\Desktop\Decopilar\sm3dl-port\`
(no es git). Uso personal; nunca distribuir ROM/assets/código de Nintendo.

## Decisión del dueño
Pasar el renderizador de OpenGL 4.5 a **Direct3D 12**. OpenGL queda como backend de REFERENCIA (para comparar
píxel a píxel) y se elige con `SM3DL_BACKEND=gl|d3d12` (default `gl` hasta que D3D12 lo iguale).
Plan completo (9 pasos): 1 separar backend · 2 shaders GLSL→HLSL/DXIL · 3 base D3D12 + swap chain flip ·
4 recursos · 5 estados→PSO con caché en disco · 6 lecturas de vuelta · 7 presentación en hilo aparte ·
8 validación por píxel · 9 medir y cambiar default. **Esta tanda: A = paso 1, B = paso 2.**

## Dónde está el render (no re-derivar)
- `recomp\render\raster_gl.c` (2.723 líneas): todo el raster PICA200 en GL; funciones GL modernas por puntero
  (`X(PFNGL...PROC ...)`, ~75). `raster_uber.c`: shader general (TEV en enteros, luz por fragmento, niebla,
  tijera; usa geometry shader). `presentador_gl.inc` (incluido por raster_gl.c): presentación por GPU.
  Interfaz pública: `raster_gl.h` (7 funciones) + `raster_pres_*` (declaradas en `ventana_gpu.c`).
- Shaders de vértices PICA → GLSL en vivo: generación en `raster_gl.c` (~líneas 300-450) y referencia Python
  `tools\shader_glsl.py`, `tools\tev_glsl.py`, `tools\validar_glsl.py`, `tools\probar_shaders.py`.
- Caché de programas GL en disco (glProgramBinary). En una partida normal se usan ~150 programas.
- Lee de `ESTADO.md` SOLO: "Rasterizador — preparación", "Sesión del rasterizador", "Tanda nocturna" (resultado
  de R: raster reescrito), "Shaders PICA200 → GLSL" y "Sesión de velocidad del 3D". Usa grep, no lo leas entero.

## Compilar
- Desde la raíz: `py -I recomp\arranque\compilar.py -o sm3dl_<tu_id>.exe` (zig cc, ~30 s).
  **Nunca enlaces `sm3dl.exe`, `sm3dl_alineado*.exe` ni el exe del otro agente.** `juego.a` no se toca.
- Python: `py` (el `python` del PATH es otro venv). Compilador C: `py -m ziglang cc`.

## REGLAS DURAS
1. **NO correr el juego** (ni ventana visible ni oculta, ni guiones de medición). El dueño se quejó de que las
   pruebas le calientan la laptop. Solo compilar y pruebas unitarias LIVIANAS (segundos, un núcleo). Si
   necesitas correr el juego para validar, déjalo escrito como "prueba pendiente" con el comando exacto.
2. **Solo escribes en TUS archivos** (listados en tu tarea) y en `agentes_dx12\<tu_id>\` + `agentes_dx12\<tu_id>.md`.
   Cambio en archivo ajeno → "pedido de integración" en tu bitácora con el diff propuesto.
3. Antes de editar un archivo existente: respaldo `<archivo>.antes_dx12_<tu_id>` la primera vez.
4. Bitácora temprana en `agentes_dx12\<tu_id>.md`, actualizada en cada hito; si ya existe, retoma desde ahí.
5. Verificación de verdad: todo "verde" necesita un SABOTAJE que se vea fallar.
6. Nunca matar procesos por nombre. Si Smart App Control bloquea un .exe propio, no lo esquives: anótalo.
7. Ahorra tokens: grep/head/tail; `partes\*.c`/`todo.c` (2-74 MB) jamás enteros.
8. Descargas (herramientas como glslang/SPIRV-Cross/DXC): cada una en su propia carpeta NUEVA dentro de
   `agentes_dx12\<tu_id>\terceros\`, solo de fuentes oficiales (GitHub releases de KhronosGroup / microsoft),
   versión fija anotada en la bitácora. Ejecuta Python sobre ellas con `py -I`. Nada de instaladores globales.
9. Comentarios y bitácoras en español, con el estilo del código existente (comentarios densos, cifras medidas).

## Entrega
- Bitácora completa (qué hiciste, cifras, sabotajes, archivos tocados, pendientes, pedidos de integración).
- Respuesta final: **máximo 15 líneas**.
