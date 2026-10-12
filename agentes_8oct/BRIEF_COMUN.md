# Brief común — tanda de 10 agentes (8 oct 2026)

Proyecto: port nativo a PC de Super Mario 3D Land por RECOMPILACIÓN ESTÁTICA ARM11→C→x86-64.
Raíz: `C:\Users\usuario\Desktop\Decopilar\sm3dl-port\` (no es git). Uso personal; nunca distribuir ROM/assets.

## Contexto mínimo (no re-derivar)
- Lee SOLO lo que tu tarea necesita de `ESTADO.md` (secciones "Próximo paso" en adelante, líneas ~121-165). No leas el archivo entero si no hace falta.
- Recompilador: `recomp\recomp.py` (+ `recomp\runtime\`, `recomp.h`). Batería por instrucción: `recomp\bateria.py` (hoy 460/460). Compilar todo: `recomp\compilar_todo.py` (~29 s).
- Arranque: `recomp\arranque\` (copia propia del generador `generar.py`, `main.c`, `BITACORA.md`). Capa de sistema: `recomp\sistema\` (svc, fibras, planificador; `DISENO.md`, `svcs.md`).
- Azahar (emulador 3DS) en `..\azahar-src` SOLO como lectura de referencia (GPLv2: no copiar código literal; reimplementar). El dueño decidió NO usar el emulador.
- Python: usar `py` (el `python` del PATH es otro venv). Compilador C: `py -m ziglang cc`. Unicorn/capstone ya instalados para `py`.
- Desensamblar sin Ghidra: `tools\dis.py` (ojo: tapa el módulo `dis` estándar si `tools\` está en sys.path).

## Reglas duras
1. **Ghidra:** el `.gpr` principal (`ghidra\SM3DL.gpr`) está BLOQUEADO por el MCP de la sesión principal. NO lo abras con scripts headless. Si necesitas Ghidra: copia propia en `ghidra\agentes\<tu_area>\` o usa capstone/`tools\dis.py`. NO uses las herramientas MCP `ghidra-sm3dl`/`pyghidra-mcp` salvo que tu tarea lo diga.
2. **Solo escribes en TUS archivos** (listados en tu tarea). Si necesitas un cambio en un archivo ajeno, NO lo hagas: descríbelo en tu informe como "pedido de integración".
3. **Guarda trabajo parcial temprano** en `agentes_8oct\<tu_id>.md` (bitácora) y continúa desde ahí si ya existe. Si te detienen, lo hecho no se pierde.
4. **Verificación de verdad:** todo verde debe tener un SABOTAJE que se vea fallar. Un verde entre dos versiones que comparten el error no prueba nada (caso FPSCR: el juego usa 0x03000000, no 0x03C00000).
5. Nunca matar procesos por nombre (solo el PID propio). Si Smart App Control bloquea un .exe/.dll propio, NO esquivarlo: anótalo y usa la verificación en Unicorn.
6. **Ahorra tokens:** no vuelques archivos grandes ni logs largos a tu contexto (usa grep/head/tail, filtra). No re-leas lo que ya leíste.

## Entrega
- Bitácora completa en `agentes_8oct\<tu_id>.md` (qué hiciste, cifras, sabotajes, archivos tocados, pendientes, pedidos de integración).
- Tu respuesta final: **máximo 15 líneas**: resultado medido, archivos tocados, lo que queda, pedidos de integración. Sin relleno.
