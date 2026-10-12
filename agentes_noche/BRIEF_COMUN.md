# Brief común — tanda nocturna (3 agentes a la vez)

Proyecto: port nativo a PC de Super Mario 3D Land por RECOMPILACIÓN ESTÁTICA ARM11→C→x86-64.
Raíz: `C:\Users\usuario\Desktop\Decopilar\sm3dl-port\` (no es git). Uso personal; nunca distribuir ROM/assets.

## Dónde está el proyecto (no re-derivar)
- El exe ya corre el bucle principal del juego, dibuja texto con `nwfont_RectDrawerShader` (logo arriba, diálogo "Welcome to SUPER MARIO 3D LAND!" abajo) en una ventana GDI, y la tecla X (= A) avanza el diálogo.
- Lee de `ESTADO.md` SOLO las secciones desde "Tanda de 10 agentes (8 oct)" (línea ~160) hasta "PRÓXIMA SESIÓN — por dónde empezar (cierre del rasterizador)" (~213). Bitácoras de la tanda anterior: `agentes_8oct\<letra>.md` (léelas solo si tocan tu área).
- Arranque: `recomp\arranque\` (`main.c`, `compilar.py`, `BITACORA.md`, `cadena.py` para caídas). Capa de sistema: `recomp\sistema\`. GPU: `recomp\gpu\gsp.c`. Render: `recomp\render\` (`pica.c`, `pica_dibujar.c`, `raster_gl.c`, `texturas.c`, `ventana.c`). Audio: `recomp\audio\`. HID: `recomp\hid\`.
- Azahar (emulador 3DS) en `..\azahar-src` SOLO como lectura de referencia (GPLv2: no copiar código literal; reimplementar). El dueño decidió NO usar el emulador.
- Python: usar `py` (el `python` del PATH es otro venv). Compilador C: `py -m ziglang cc`. Unicorn/capstone instalados para `py`. Desensamblar sin Ghidra: `tools\dis.py`.

## Compilar y correr (OJO, cambió)
- Enlazar: desde la raíz, `py -I recomp\arranque\compilar.py -o sm3dl_<tu_id>.exe` (~12 s). **Nunca enlaces `sm3dl.exe` (es el de la sesión principal) ni el exe de otro agente.**
- `recomp\arranque\juego.a` (el juego recompilado) es COMPARTIDO y solo lo regenera la sesión principal. Si necesitas un cambio en `recomp.py`/el traductor, es un pedido de integración.
- Correr SIEMPRE con límite: `SM3DL_SEGUNDOS=N SM3DL_SIN_TRAZA=1 ./recomp/arranque/sm3dl_<tu_id>.exe 2> <tu_log>`. Se abre una ventana visible (está bien, el dueño duerme). Logs y capturas tuyas dentro de `agentes_noche\<tu_id>\`, no en la raíz.
- Si un exe tuyo queda colgado, mátalo por SU PID (nunca por nombre).

## Reglas duras
1. **Ghidra:** el `.gpr` principal está bloqueado por la sesión principal. No lo abras headless ni uses las herramientas MCP de Ghidra. Usa capstone/`tools\dis.py`, o una copia propia en `ghidra\agentes\<tu_id>\`.
2. **Solo escribes en TUS archivos** (listados en tu tarea) y en `agentes_noche\<tu_id>\` / `agentes_noche\<tu_id>.md`. Cambio en archivo ajeno → NO lo hagas: "pedido de integración" en tu bitácora (con el diff exacto propuesto).
3. **Antes de editar un archivo tuyo, copia de respaldo** `<archivo>.antes_<tu_id>` la primera vez.
4. **Bitácora temprana** en `agentes_noche\<tu_id>.md`, actualizada tras cada hito. Si ya existe al empezar, retoma desde ahí (pudiste ser interrumpido por límite de sesión).
5. **Verificación de verdad:** todo verde necesita un SABOTAJE que se vea fallar. Un verde entre dos versiones que comparten el error no prueba nada (caso FPSCR: el juego usa 0x03000000).
6. Nunca matar procesos por nombre. Si Smart App Control bloquea un .exe propio, NO esquivarlo: anótalo.
7. **Ahorra tokens:** no vuelques archivos grandes ni logs largos (grep/head/tail). `todo.c`/`partes\*.c` son de 2-74 MB: jamás los leas enteros.
8. Bash: heredocs con `\\0` escriben NUL de verdad; backticks dentro de `py -c "…"` los ejecuta bash. Scripts Python en archivo (Write) o heredoc `<<'PYEOF'`.

## Entrega
- Bitácora completa en `agentes_noche\<tu_id>.md` (qué hiciste, cifras medidas, sabotajes, archivos tocados, pendientes, pedidos de integración).
- Respuesta final: **máximo 15 líneas**: resultado medido, archivos tocados, lo que queda, pedidos de integración.
