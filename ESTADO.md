# Port nativo de Super Mario 3D Land a PC — ESTADO

> Punto de entrada. Si retomas el proyecto, lee esto primero.
> Uso personal con el volcado propio del dueño. **Nunca distribuir la ROM ni nada con código o arte de Nintendo.**

## La ROM
- `..\Super Mario 3D Land USA.3ds` — 512 MB, **descifrada** (NoCrypto), `CTR-P-AREE`, title ID `0004000000054000`.
- No se modifica nunca: todo sale de ella con los scripts de `tools/`.

## Lo que hay (6 oct 2026)
| Archivo | Qué es |
|---|---|
| `tools/extraer_code.py` | Saca `.code` del ExeFS, lo descomprime (BLZ) y arma `code.elf` (ARM, segmentos + secciones + nombres de `simbolos.txt`) |
| `tools/listar_romfs.py` | Lista y extrae los archivos del RomFS |
| `extraido/code.bin` | Ejecutable plano, 3 MB |
| `extraido/code.elf` | El mismo ejecutable listo para Ghidra, **con los nombres ya puestos** |
| `extraido/simbolos.txt` | **Fuente de verdad de los nombres** (`0xDIRECCION nombre`). Cada descubrimiento se agrega aquí |
| `extraido/tabla_actores.tsv` | Las 5 tablas nombre → función de creación (305 entradas) |
| `extraido/romfs/` + `romfs_lista.txt` | 1.756 archivos del juego (298 MB) |

### Mapa de memoria
| Segmento | Dirección | Tamaño |
|---|---|---|
| .text | 0x00100000 | 2.758.524 |
| .rodata | 0x003A2000 | 257.616 |
| .data | 0x003E1000 | 76.244 |
| .bss | 0x003F39D4 | 251.524 |

### Lo que se sabe del ejecutable
- **Sin RTTI y sin rutas de fuente**: Nintendo no dejó nombres de clases. Solo ~5.400 cadenas.
- **Tablas de fábrica** (nombre → `create_X`): actores (225, en 0x003B99F0), áreas (36), eventos de inicio (15), escenas demo (14), cámaras (15).
- Cada `create_X` = `operator_new` (0x002932A8) + constructor → **221 constructores identificados** (`X__ctor`). 74 clases pequeñas tienen el constructor inline.
- 2.336 identificadores legibles (estados tipo `AirDieFall`, parámetros `ActorParamJump`…): anclas para nombrar funciones.

### Assets (RomFS)
- `ObjectData/` 1.138 · `StageData/` 418 · `LayoutData/` 95 · `SoundData/` 92 · `LocalizedData/` 10.
- Casi todo es `.szs` (Yaz0 + SARC) adentro van modelos BCH/CGFX, texturas y datos BYML. Música `.bcstm`, banco de sonido `.bcsar`.

### Niveles (`tools\byml.py`, `tools\censo_niveles.py`)
- 147 niveles, cada uno partido en `StageMap` (objetos, cámaras, rieles), `StageDesign` (luces) y `StageSound`. **1.449 BYML convertidos a JSON** en `extraido\niveles_json\`, 0 errores. Textos en Shift-JIS (capas: シナリオ1 escenario 1, 共通 común).
- Cada objeto: `name`, `pos_*`, `dir_*`, `scale_*`, `Arg0..9`, `LayerName`, switches, `Rail`.
- **`SystemData\CreatorClassNameTable`** traduce nombre de objeto → clase del código: 1.423 objetos → 310 clases (`extraido\CreatorClassNameTable.json`).
- Cruce (`extraido\clases_prioridad.tsv`): 22.794 objetos en los niveles, **100 % con clase**; 254 clases usadas, **241 con `create_` ya ubicado (95 % de los objetos)**. Faltan 13 creadas por otro camino: `Mario`, `Demo*` (cinemáticas), `PoleGoal`, `GoalDoor`, `AreaObj`, `MysteryBoxRuleObj`, `DokanWorldWarp`.
- → **Orden de trabajo del port**: las ~25 clases de arriba de `clases_prioridad.tsv` cubren la mayor parte de lo que se ve en pantalla.

### Ronda de agentes (6 oct) — detalle en `reportes\*.md`
`simbolos.txt` pasó de 497 a **872 nombres** (respaldo previo: `simbolos.antes-agentes.txt`). Cada propuesta trae `# CONFIRMADO|HIPOTESIS: evidencia`.
- **Jugador** (`reportes\jugador.md`): Mario y Luigi = una clase `PlayerActor` (ctor 0x002768A4, 0x15C bytes, vtable 0x003C6828, hereda de GameActor). La crean las escenas directo (Stage, Title, casa de Kinopio, demo), no la fábrica. Los 7 modelos de power-up se crean todos al inicio (`PlayerModelHolder` 0x00182C10). No usa Nerves: grafo de acciones (~60 estados, ~170 transiciones) armado en `PlayerActionGraph_build` 0x001A956C (24 KB; Ghidra no lo decompila en 60 s → subir el timeout). Entrada del control: `PlayerInput_update` 0x00133484.
- **Servicios** (`reportes\servicios.md`): 9 servicios (gsp::Gpu, hid:USER, fs:USER, dsp::DSP, APT:U, cecd:u, cfg:u, ndm:u, mic:u), los 139 SendSyncRequest clasificados por comando. Sonido solo por DSP (no CSND). GPU: 5 comandos GX identificados; el swap de framebuffers NO usa SetBufferSwap (hipótesis: escritura directa en memoria compartida GSP) — falta ubicarlo. Un servicio sin identificar (handle 0x003E3190).
- **Motor** (`reportes\motor.md`): vtable de actor nombrada (1 init, 3 appear, 4 makeActorAlive, 5 kill, 6 makeActorDead, 7 movement, 8 calcAnim, 10/11 start/endClipped, 12 attackSensor, 13 receiveMsg, 19 control…; 9/17/18/20/22 vacías en todas). Bucle por frame = esquema ExecuteDirector (tabla de orden 0x003A8FA4 con grupos en japonés; el formato exacto de cada entrada no está verificado). `initActor` lee `InitActor.byml`. **241 estados** de todos los actores con nombre japonés + traducción en `extraido\estados_actores.tsv`.

### Assets
- **Texturas: las 5.693 del juego en PNG** (`extraido\texturas_png\<szs>\`, 58 MB, 0 errores) con `tools\texturas.py` (14 formatos PICA, Morton, ETC1/ETC1A4). Verificadas a ojo con Mario.
- `tools\cgfx.py`: 1.079 CGFX leídos sin error → 1.066 modelos, 5.693 texturas, 1.931 anim. esqueléticas, 1.182 anim. de material.
- **Modelos → glTF 2.0** (`tools\cgfx_gltf.py`, `reportes\modelos.md`): **los 1.066 modelos convertidos** (1,9 M triángulos, 49 s, 0 errores) a `extraido\modelos_gltf\` (179 MB). Geometría, normales, UV, colores, materiales con su PNG, esqueleto y skinning. Verificado a ojo: Mario, Goomba, bloque ?, moneda (previas en `_previas\`). La V de las UV **no** se invierte (los PNG ya vienen volteados). Falta: combinadores TEV / colores constantes (por eso Toad sale gris), animaciones, mapas de reflejo, `.glb`.
- **Colisión → OBJ** (`tools\kcl.py`, `tools\nivel_colision.py`, `tools\colision_previa.py`, `reportes\colision.md`): 577 piezas (158.970 triángulos, 0 errores) en `extraido\colision\piezas\`. El `.pa` es una tabla tipo BCSV con `Sound_code, Floor_code, Floor2_code, Wall_code, Camera_through` (campos confirmados en `code.bin`; el significado de cada número es deducido). Nivel completo `AquariumSwimStageMap1.obj` armado y verificado a ojo: piezas apoyadas, sin huecos. Transformación: pos + Rz·Ry·Rx·escala en grados, 1 bloque = 100 — **el orden ZYX no está confirmado en el código** (ganó 5 de 6 pruebas de encaje). Falta: colisión que genera el código, objetos con varios KCL según estado, piezas móviles.

## Cómo regenerar todo
```
py -I tools\extraer_code.py "..\Super Mario 3D Land USA.3ds" extraido
py -I tools\listar_romfs.py "..\Super Mario 3D Land USA.3ds" extraido\romfs_lista.txt extraido\romfs
```
Luego en Claude: importar `extraido\code.elf` con el MCP `pyghidra-mcp`. Al agregar nombres a `simbolos.txt`, regenerar el ELF y reimportar (el análisis tarda ~20 min).

## Ruta del port (de largo plazo)
1. **Mapa** ← *estamos aquí*. Identificar el SDK de Nintendo (`nn::`), el motor gráfico (NW4C/PICA200), el sonido, el bucle principal, la escena y la clase del jugador.
2. **Formatos**: convertir SZS/SARC/BCH/BYML/BCSTM a formatos de PC (glTF, PNG, OGG, JSON).
3. **Estrategia de código** (decidir cuando el mapa esté maduro):
   - **Recompilación estática** ARM → C (como N64Recomp) + capa que reemplace los servicios del 3DS y la GPU PICA200 por Windows/OpenGL. Es lo más corto hacia algo jugable.
   - **Decompilación a mano** función por función. Lo más limpio, pero son años.
4. **Plataforma**: ventana, control, una sola pantalla (la táctil como overlay), 60 fps, alta resolución.

### Ghidra — proyecto propio `ghidra\SM3DL.gpr` (el bueno)
- Se crea con `tools\analizar_ghidra.py` (3 min): procesador **ARM:LE:32:v6** y **sin** el analizador *Non-Returning Functions - Discovered*. Ese analizador, con la config por defecto, marcó como "no regresa" a getters triviales (0x00277248) y dejó sin desensamblar el código tras ~90 llamadas. Resultado ahora: 12.216 funciones, 0 marcadas noreturn.
- `tools\aplicar_simbolos.py` aplica `simbolos.txt` (nombres + comentarios `#` como plate) en segundos, sin reanalizar.
- `tools\consultar.py` decompila/xrefs/asm/buscar sin MCP (~10 s por llamada). Desventaja conocida: algunas constantes del literal pool salen como `DAT_xxxx` en vez del puntero.
- MCP dedicado: `ghidra-sm3dl` (scope user) apunta a este `.gpr`; carga al reiniciar Claude Code. **Un solo proceso a la vez puede abrir el proyecto**: si el MCP lo tiene abierto, los scripts fallan por el lock (y viceversa).
- `ghidra\agentes\<area>\` = copias para agentes en paralelo (se pueden borrar al terminar).

### Textos de depuración en japonés
- `extraido\textos_japones.tsv`: 1.262 textos Shift-JIS reales (estados `[state]…`, parámetros de ajuste, nombres de capas gráficas). Cada uno está junto a la función que lo usa → nombrar funciones casi gratis.
- Ej. estados del Goomba: 攻撃 atacar · 徘徊 deambular · 追いかけ perseguir · 落下 caer · プレイヤー発見 detectar al jugador · 飛び出し salir disparado · 吹っ飛び salir volando.

### Framework (confirmado)
- Nerve (máquina de estados, linaje Galaxy): `setNerve` 0x00280608, `isNerve` 0x002806A0, `addNerveState` 0x001CACAC, vtable pos 0 = `getNerveKeeper`.
- Vtable de actor: pos 1 `init`, pos 12 `attackSensor`, pos 13 `receiveMsg`.
- Carga de actor: `initActorWithArchiveName` arma `"ObjectData/%s"` → `ObjectData/<Nombre>.szs`.

### Formatos dentro de los .szs (`tools\szs.py`, censo en `extraido\censo_szs.tsv`)
- Los `.szs` son **Yaz0 + NARC** (heredado del DS), no SARC. 0 errores al leer los 1.666.
- `.byml` 6.492 (config/niveles) · `.bcmdl` 1.078 (modelos CGFX) · `.kcl`+`.pa` 577+577 (colisión) · `.bclyt/.bclan/.bclim` (menús 2D) · `.msbt` 147 (textos) · `.shbin` **4** (shaders PICA200) · `.bcfnt` 15.

### Jerarquía de actores (hipótesis con evidencia)
- `LiveActor__ctor` (0x0027FE94): raíz. Nombre en +0x10, 4 vtables, subobjeto en +0x54 (ctor 0x001C70F4).
- `GameActor__ctor` (0x00280420): hereda de LiveActor; **base directa de 211 de 221 clases**.
- Otras bases: 0x00262738 (5 `StartEvent*`), 0x00279C04 (`Killer`, `KillerMagnum`).
- Ejemplo: `Kuribo` (Goomba) mide 0x84 bytes, 4 vtables desde 0x003D2CE8.

### SDK / servicios del 3DS
- 328 `svc` repartidas por todo `.text` (el SDK está mezclado con el juego, no en un bloque). 139 son `SendSyncRequest` = IPC a servicios (GSP gráficos, HID controles, FS archivos, DSP sonido): **es la frontera que el port debe reemplazar**.

### Grafo de estados de Mario (7 oct) — `reportes\grafo.md` + `reportes\grafo_mario.md`
- Sacado **emulando** `PlayerActionGraph_build` con Unicorn (`tools\emular_grafo.py` → `analizar_grafo.py` → `grafo_legible.py`): 60 nodos, 721 aristas (619 únicas), verificado contra el C en 3 aristas.
- Arista = `PlayerActionNode_addEdge(nodo, cond, destino)` (0x00251E20). Condiciones: `evaluar()` en vptr+8; AND/OR/NOT/N-frames.
- Contexto: `ctx[0x3]` = PlayerInput (confirmado), `ctx[0x5]` = colisionador (`vf24` = en suelo), `ctx[0x0]` = física, `ctx[0x7]` = animación, `ctx[0x10]` = forma.
- Control: A/B salto, X/Y correr/ataque, L/R agacharse; **buffer de 5 frames** para salto y para X/Y.
- `simbolos.txt` 920 nombres (respaldo `simbolos.antes-grafo.txt`). Herramientas nuevas: `tools\dis.py` (desensamblador capstone sin Ghidra), `tools\cadenas_de.py`, `tools\condiciones_grafo.py` (vtable → métodos decompilados).

### Recompilación estática — prototipo (7 oct) — `recomp\README.md`
- Traductor ARM11→C (`recomp\recomp.py`) + CPU virtual (`recomp\runtime\recomp.h`). Lote piloto: 27 funciones / 515 instrucciones, 0 sin soporte; **17/17 verificadas** contra la original con el banco de `decomp\`.
- Sabotaje del traductor 5/9: LS y sxth no aparecen en el lote (falta batería por instrucción); NaN y `lsl` 32 solo fallan en x86 (falta correr nativo).
- **Smart App Control activo bloquea el .exe/DLL propios** → la ejecución nativa x86 queda pendiente de una decisión del dueño.
- 6 funciones del lote no las conoce Ghidra (solo por vtable): el recompilador debe descubrir funciones solo.

### Atajo Azahar (7 oct) — código en `..\azahar-src` (GPLv2, clon superficial sin submódulos)
- **Idea central:** Azahar separa la CPU (`src\core\arm\arm_interface.h`: Run/Step/registros/SaveContext/LoadContext) del resto. Implementaciones: dynarmic (JIT), dyncom (intérprete), fastinterp. Plan: una 4ª implementación **ARM_Recomp** que ejecute nuestro código recompilado y caiga al intérprete donde falte; Azahar pone servicios, archivos y GPU.
- Las svc se atienden en el momento (`svc_context.CallSVC`). El reto: cambiar de hilo a mitad de una función recompilada → **una fibra por hilo del juego** (Windows `CreateFiber/SwitchToFiber`).
- **Swap confirmado en `hle\service\gsp\gsp_gpu.cpp`:** `FrameBufferUpdate` en `shm+0x200+(2*hilo+pantalla)*0x40` {índice, dirty, 2×FrameBufferInfo 0x1C}; el GSP lo aplica en el VBlank si dirty. `SetBufferSwap` existe pero el juego no lo usa.
- Para compilarlo faltan: Visual Studio Build Tools (o MinGW/clang), CMake, Ninja y los 35 submódulos. Disco libre: 43 GB.

## Próximo paso
Hechos el 6 oct: noreturn, vtables, clase del jugador, servicios, motor, texturas, modelos glTF, colisión OBJ. Hecho el 7 oct: grafo de estados de Mario. Pendiente (en este orden):
0. **Recompilación estática (en curso, cierre 7 oct):** el traductor procesa el juego ENTERO (12.283 funciones, 552.738 instrucciones, 1 sola sin soporte: un `cdplo` que es dato). **Batería por instrucción: 444/444 formas OK** (1.210 ejemplares reales × 80 pruebas, nativo x86 contra Unicorn; `recomp\bateria.py`). Lote piloto 17/17 nativo. Tablas de saltos (141 `switch`) soportadas. **Siguiente:** (a) ~~compila entero~~ **COMPILA: todo.o de 137 MB en 39 min, 0 errores** (pero se generó ANTES de las 4 correcciones de la batería: regenerar con `recomp.py --todo` y recompilar); (b) descubrir funciones por vtables; (c) capa de sistema (svc + 9 servicios) y fibras por hilo; (d) primer arranque registrando servicios. Decisión del dueño: **NO usar el emulador** (Azahar solo como lectura de referencia).
1. ~~Aplicar simbolos al .gpr~~ **hecho 7 oct por el MCP** (42 renombres + save). Faltan 8 getters de PlayerInput (0x00326Cxx): Ghidra no los tiene como funcion y el MCP no crea funciones -> quedan para tools\aplicar_simbolos.py en la proxima regeneracion. Nota: el MCP `ghidra-sm3dl` abre el .gpr al arrancar la sesion y guarda el lock; para scripts headless usar una copia (ghidra\agentes\<area>) o renombrar POR el MCP.
2. ~~Cerrar el grafo~~ **hecho 7 oct (ronda 2)**: 0 condiciones crudas, prioridad confirmada, sensores de colisión con nombre (suelo, pared al frente, pared agarrable, toca Floor_code N). Quedan 6 estados con `?` (hipótesis escritas en `reportes\grafo.md`) y los campos `ctx15, 16, 24, 30, 34, 35`. `simbolos.txt` en 927. Corregido: 0x001A7FCC NO es HipDropStart, es rebote (PlayerStateBounce).
3. Swap de framebuffers: **avanzado 7 oct** (ver `reportes\servicios.md`, Capa gráfica). Se sabe dónde vive la info y cómo arrancan las pantallas; NO quién la escribe cada frame, y el port no lo necesita (GSP falso lee shm en el VBlank). Mensajes entre actores: **hechos 7 oct** (`reportes\mensajes.md`, `extraido\mensajes.tsv`): 48 números con su envoltorio; con nombre seguro Pisotón(1), Cabezazo(3), Coletazo(0x12), Patada(0x13), Empujar(0x29), AtaqueEnemigo(0x2D); el resto con hipótesis por emisor (caparazón, roca, bala Bill). Abierto: el 17 (el más consultado) y el sub-actor de Mario 0x161B6C (¿boomerang?).
4. **Estrategia de código (7 oct):** el dueño pidió probar primero decompilación a mano. Hecho: banco de pruebas en `decomp\` (ver `decomp\README.md`): C a mano + compilado con Zig para ARM11 + verificador diferencial en Unicorn + sabotaje. 17 funciones verificadas (hasta 126 instrucciones), sabotaje 20/20. **Conclusión: funciona y es fiable, pero no escala al juego entero** (573.517 instrucciones en 12.283 funciones; 66% en funciones de 30-300 instr., que piden un generador de pruebas a medida cada una). Propuesta: recompilación estática para todo + este mismo verificador para validar el recompilador + decompilación a mano solo de los subsistemas que se quieran cambiar (cámara, render, jugador).

## Sesión 7 oct (tarde) — descubrimiento de funciones
- **`tools\descubrir_funciones.py`** → `extraido\funciones_extra.tsv` (recomp.py lo fusiona solo; `--sin-extra` para no usarlo). Semillas: punteros de .rodata/.data (vtables) y literales que caen fuera de todo código alcanzado + saltos que salen del rango de su función; cada una se valida recorriéndola (decodifica, sin instrucciones de "dato", termina). **4.280 funciones nuevas** (3.525 de vtables).
- **El tamaño de Ghidra cortaba funciones**: mide el primer tramo contiguo y deja fuera los bloques que el compilador pone detrás del literal pool (casos de switch, epílogos; 0x100C7C = 164 bytes con sus casos en 0x100D24+). `limite()` ahora llega hasta la siguiente función conocida; el recorrido sigue el flujo y no traduce el pool.
- **Bug de switch corregido:** los 146 `switch` del juego son `ldrlo` (índices 0..N−1), no `ldrls`: todos tenían un caso de más que leía la instrucción siguiente como dirección (inalcanzable, pero ensuciaba).
- Resultado: 16.563 funciones, **627.941 instrucciones** (antes 552.738), saltos huérfanos **532 → 6**. Aparecieron 162 instrucciones SIMD sin soporte (`uxtb16`, `uhadd8`, `sxtab` con rotación…) en código de píxeles escrito a mano (~0x236BD0–0x238B8C, por vtable).
- En curso (4 agentes): A soporte SIMD + batería · B auditoría del descubrimiento (`reportes\descubrimiento.md`) · C compilación partida y en paralelo (`recomp\partir.py`, `compilar_todo.py`) · D capa de sistema y fibras (`recomp\sistema\`).
- **Hecho (agentes, 7 oct tarde):** A — SIMD (`uxtb16`, `uhadd8`, `sxtab`/`uxtab` con rotación, `ldrb` con `ror`) en recomp.py/recomp.h: **batería 461/461**, sabotaje detectado en las 5 formas nuevas. C — `recomp\partir.py` + `recomp\compilar_todo.py`: el juego entero compila en **28 s** (antes 39 min), 32 partes en paralelo, -O2. D — capa de sistema `recomp\sistema\` (svcs.md: 333 svc de 28 tipos; DISENO.md; fibras + planificador + memoria; prueba_fibras pasa y detecta 2 sabotajes). Pendiente marcado por A: `0x3A0B68` es noreturn.

## Shaders PICA200 → GLSL (7 oct tarde)
- `tools\shbin.py extraer` → `extraido\shaders\`: 4 shbin de interfaz (`nwlyt_*`, `nwfont_*`) + 3 DVLB 3D dentro de `ObjectData\Shader.szs` (shader genérico de NintendoWare: skinning con `UnivReg` c25–c84, cuaterniones de normal/tangente, luz por vértice y hemisférica, generación de UV). Las etiquetas traen nombre (`l_transform_matrix`, `l_calc_hemisphere_lighting`…). Listado legible en `*.txt`.
- Semántica leída de Azahar: `jmpu` salta si `b == !(num&1)`; índice relativo en el operando de 7 bits (mad → src2, madi → src3); `0*inf = 0`; los ámbitos call/if/loop se cierran por `pc_viejo+1` (un salto al final de un ámbito NO lo cierra).
- `tools\shader_glsl.py` → `extraido\shaders\glsl\*.vert` (16 programas): árbol estructurado; saltos hacia adelante = banderas + guardas (los del shader 3D se cruzan: 248→256 y 255→294).
- `tools\probar_shaders.py`: árbol vs máquina de pilas (`tools\shader_ref.py`), todas las combinaciones de bools + valores especiales: **4.800/4.800**; sabotajes 1/2/3 detectados (salto invertido, loop corto, guarda ignorada). Comparten solo la aritmética (`tools\pica_ops.py`): un error de semántica aritmética NO lo vería esta prueba.
- **Los 16 GLSL compilan y enlazan sin avisos** en NVIDIA RTX 5050 (617.14) e Intel UHD 770 (agente H): `tools\.venv_gl\Scripts\python.exe tools\validar_glsl.py`. Por defecto abre la Intel; para la NVIDIA, preferencia de GPU de Windows para ese python (`GpuPreference=2`).
- Falta: shaders de fragmentos = TEV (agente E), y la conversión float24 → float32 (precisión).
- **Primer arranque (agente F, `recomp\arranque\`, bitácora en `BITACORA.md`):** `sm3dl.exe` carga code.bin, arma el hilo principal (pila 0x20000, prioridad 0x30, FTZ/DAZ) y corre la entrada recompilada. Pasa el crt0 y `CreateAddressArbiter`; **se traba** en un bucle de `ArbitrateAddress` tipo 2 sobre `0x003FA700` (valor 0) desde `0x0028EC60` (lock del SDK en 0x28EC20). Hipótesis: (a) DESCARTADA 7 oct: la capa hace el decremento igual que Azahar y con mem=0, valor=0 no hay espera, es correcto; (b, la más probable) el lock está en .bss y lo debía inicializar un constructor que no corrió; (c) revisar que code.bin (hasta 0x3F4000) no pise el inicio de .bss (0x3F39D4). Arreglos del traductor que encontró (pasados al agente I): `mov pc, lr` = retorno; `limite()` con funciones solapadas de Ghidra. Pendiente: limitar el log de svc repetidas (un bucle llenó 95 M de líneas en 60 s).
- **Auditoría del descubrimiento (agente B, `reportes\descubrimiento.md`):** 29/30 funciones nuevas verificadas en ejecución (nativo vs Unicorn), 0 fallas del traductor; 0x2ABBEC sin datos (necesita generador propio). `valida()` acepta funciones que caen por flujo en el inicio de otra → **4.755 descubiertas**, 14 rechazos (todos datos, en `extraido\funciones_rechazadas.tsv`). Ghidra tiene 416 funciones solapadas. 🩹 **`emu_start(count=…)` de Unicorn se detiene SIN error al agotar el tope**: `decomp\verificar.py` debe marcar error si el PC final no es la trampa (puede haber verdes falsos). 🪛 `tools\dis.py` tapa el módulo estándar `dis` si `tools\` está en sys.path.
- **Etapa de fragmentos (agente E, `reportes\pica_registros.md`, `tools\pica_cmd.py`, `extraido\pica_materiales.tsv`):** cada material CGFX trae una PLANTILLA de comandos PICA (culling, depth, blend, stencil, texturas 0–2, 6 etapas TEV, alpha test…) que el runtime completa al dibujar. 4.579 materiales, **337 recetas TEV** distintas (5 cubren 1.957), **el juego depende del fragment lighting** (~90 %), ningún material usa niebla/tex3/procedural. El código escribe con 302 cabeceras: framebuffer, 8 luces y LUTs, niebla, shaders. Orden para el renderer: TEV 6 etapas + buffer → fragment lighting → blend/alpha/depth/culling → texturas → niebla → raros. Faltó: campos del material que no son comandos (colores, LUTs, bump, coordenadas).
- **Audio (agente G, `reportes\audio.md`, `tools\audio_*.py`):** firmware DSP EMBEBIDO en code.bin (.data 0x3E31B0, 0xBE44 bytes; lo carga 0x1F2D8C): el port no lo ejecuta, responde "cargado". Driver nn::snd: 0x1F8310 evento del pipe 2 (= tick de audio), 0x1F8BD0 init (24 fuentes, mismo layout que Azahar), 0x1F9444 apagar/dormir. `tools\audio_bcstm.py` decodifica bcstm a WAV (BEACH 6 canales ADPCM 32 kHz; ATHLETIC 4 canales), verificado por medida, no escuchado. Diseño: dsp::DSP falso + 512 KB en 0x1FF00000 + tick de 160 muestras a 32.728 Hz → SDL2/WASAPI 48 kHz. Falta: bucle por frame de nn::snd, censo del .bcsar, implementar en `recomp\audio\`.
- **Recompilación con arreglos (agente I):** `recomp.py` ahora: noreturn (`extraido\noreturn.txt`, 9, por `tools\noreturn.py`; el recorrido se corta tras `bl` a ellas y tras `svc 0x03/0x3C`), `mov pc, lr` = `return;`, `limite()` con funciones solapadas, `tamanos()` sin lo de fuera de .text. **17.037 funciones, 629.742 instrucciones; batería 460/460** (antes 461: falta confirmar que la forma que salió es `mov pc, lr`); compila en 29 s, 0 avisos → `recomp\build\juego_todo.a`.
- 🔴 **PENDIENTE IMPORTANTE — retorno calculado en 0x3A0B68:** NO es noreturn: es el despachador de comparaciones float de la librería de ARM. Lee una palabra de DATOS detrás del `bl` (`ldr r4, [lr], #4`) y vuelve a `lr + r4*4` (`add ip, lr, r4, lsl #2; bx ip`). Hoy el traducido sigue en `bl+4` (= el dato): **todo llamador de esta función corre mal**. Arreglo: reconocer en el traductor los `bl` a funciones de retorno calculado, saltarse la palabra de datos y continuar con un `switch`/`rt_llamar` sobre el pc que devuelve. Contar llamadores primero. El `(no decodifica)` de 0x3A0D80 es esa palabra.
- **Fragment shaders TEV (agente L):** `tools\tev_glsl.py` → `extraido\shaders\frag\R0..R331.frag` (son **332** recetas, no 337); las 332 compilan y enlazan (Intel UHD 770, GL 3.3). Uniforms por material: `tev_const[6]`, `tev_buffer_color`, `tev_update`. ⚠️ Solo está probado que COMPILA: la semántica (buffer de la etapa N-1, previo inicial = 0, DOT3_RGBA) no se comparó contra nada → falta un verificador diferencial como el de los vertex shaders. Fuera: fragment lighting real (hoy uniforms `frag_primario/secundario`), alpha test, niebla, LUTs, unión con las salidas `pica_oN` del vertex shader.
- **Hueco del verificador TAPADO (agente K):** tras cada `emu_start`, si el PC no está en `TRAMPA` la corrida es "no terminó" (ni OK ni falla) en `decomp\verificar.py`, `recomp\verificar_recomp.py` y `verificar_recomp_arm.py`. Sabotaje `b .` ahora se marca. Re-verificación: decomp a mano 17/17 y lote piloto nativo 17/17, **ningún verde anterior era falso**. `verificar_recomp_arm.py` cambiado pero sin correr. 🪛 Unicorn reusa el bloque ya traducido si reescribes código en la misma dirección: cada programa sembrado en su propia dirección.
- **Controles (agente M, `recomp\hid\`, `reportes\hid.md`):** layout de la shm de hid:USER (0x238 bytes, offsets con `_Static_assert`): pad + anillo de 8 en 0x000, touch 0x0A8, acelerómetro 0x108, giroscopio 0x158; circle pad ±0x9A, pad/touch a 234 Hz. `hid.c` llena el anillo desde teclado/XInput (`-lxinput1_4`); prueba OK y sabotaje detectado. `PlayerInput_update` (0x133484) NO lee la shm: recibe el mando ya procesado. El juego activa acelerómetro y giroscopio (hay que llenarlos aunque sea en reposo). Falta: quién lee el anillo (seguir 0x1F3890 desde `HID_Initialize` 0x1F3AC4, estado en 0x424FC8), y conectarlo a `recomp\sistema` (`GetIPCHandles` con la shm + 5 eventos; hilo a 234 Hz).
  - **Análisis 0x3A0B68 (agente O, 7 oct cierre) — SIN arreglar todavía; recomp.py intacto (460/460):**
    - **Contrato:** el llamador hace `push {r4, lr}; bl F` y detrás del `bl` va UNA palabra de datos con 9 códigos de 3 bits (uno por clase de los operandos: NaN, ±inf, cero…; bit 31 = comparar solo r0). F lee el código: si es <4 vuelve DENTRO del llamador a `X+8+4·código` (X = dirección del `bl`) tras `pop {r4, lr}` (deshace el push del llamador); si es ≥4 salta por `add pc, pc, ip, lsl #2` (0x3A0BD4, 4 casos 0x3A0BDC..0x3A0BE8) a un resultado especial (r0 = r1, NaN 0x7FC00000…) y termina con `pop {r4, pc}` = **retorna POR el llamador**.
    - **Censo:** es la ÚNICA función de .text con `ldr rX, [lr], #4` y el ÚNICO `add pc, pc, …`. **Solo 2 llamadores**, ambos con `push {r4, lr}` antes: 0x3A0D08 (dato 0x3EFFFFED: códigos 5,5,7,7,7,7,7,7,6 → nunca vuelve adentro, siempre retorna por el llamador) y 0x3A0D7C (dato 0x806DB6DB: códigos 3 y 0 → destinos 0x3A0D90 y 0x3A0D84). Las dos palabras de datos son justo el `cdplo` x1 y el `(no decodifica)` x1 del "sin soporte". Impacto real: los caminos de casos especiales (NaN/inf) de 2 rutinas de float de la librería, no todo float.
    - **Diseño del arreglo (para aplicar y verificar):** (1) `RETCALC = {0x3A0B68}`; en `recorrer()`, tras un `bl` a ella NO seguir en X+4 y encolar los destinos X+8+4k con código k<4 sacados de la palabra de datos. (2) En `traducir()` del `bl`: `c->r[14] = X+4; f_F(c); switch (c->r[15]) { case destino: goto L_destino; … default: return; }` (default = F ya retornó por el llamador). (3) Al traducir F misma: `bx ip` → `c->r[15] = c->r[12]; return;` y `pop {…, pc}` → `c->r[15] = npc; return;`. (4) `add pc, pc, ip, lsl #2` en 0x3A0BD4 → `switch (c->r[12])` con 4 casos. `c->r[15]` hoy es "solo informativo" (solo lo escribe `rt_svc`), sirve de canal. (5) Verificar: diferencial de 0x3A0D30 y de la función que contiene 0x3A0D08 (nativo vs Unicorn) con NaN, ±inf, 0, iguales; sabotaje = no saltarse la palabra de datos; batería 460/460; "sin soporte" debe quedar en 0.
- **Texturas en C (agente N, `recomp\render\texturas.c/.h`, `tools\verificar_texturas_c.py`):** decodifica los 14 formatos PICA a RGBA8 lineal; **30/30 texturas reales idénticas byte a byte** al Python en los 8 formatos que usa el juego (RGBA5551, RGB565, RGBA4, LA8, HILO8, L8, ETC1, ETC1A4); 2 sabotajes detectados (Morton 12/30, subbloques ETC 25/30). RGBA8/RGB8/A8/LA4/L4/A4 sin datos reales. Falta: mipmaps, `.bclim` de la interfaz.
- **Lock del arranque DESTRABADO (agente J, obstáculo 3 en `recomp\arranque\BITACORA.md`):** el lock lo pone en 1 el constructor estático 0x380C20; `__cpp_initialize__aeabi_` (0x3A0D9C) recorre `.init_array` [0x3A0DDC, 0x3A177C) (~616 entradas RELATIVAS, estilo armcc) llamando con `add lr, pc, #4 ; mov pc, r0`, que el traductor tomaba como salto de cola → solo corría 1 constructor. Arreglos (SOLO en la copia del arranque: `recomp\arranque\generar.py`; **falta llevarlos a `recomp.py` y `descubrir_funciones.py`**): (1) `add lr, pc, #k`/`mov lr, pc` + `mov pc, rX`/`bx rX` = LLAMADA (25 sitios); (2) los destinos de .init_array son funciones (→ 17.652 funciones, 641.317 instr.); (3) log de svc acotado a 20 por (svc, dirección). **Nuevo punto de parada:** pasa svc 0x21/0x38/0x3A/0x23/0x01 y se detiene en `rt_externo` a 0x001ED5B4 sin traducir (lr=0x0028EAE0): otro destino indirecto; mirar quién salta desde ~0x28EAD8. Aún sin IPC. Correr desde la raíz del proyecto (ruta relativa de code.bin).

## Tanda de 10 agentes (8 oct) — bitácoras en `agentes_8oct\<letra>.md`
- **A recompilador:** arreglos de J en `recomp.py` (616 destinos `.init_array`, 25 llamadas `add/mov lr,pc`) + retorno calculado 0x3A0B68 aplicado (diferencial 3000/3000 en 0x3A0C08 y 0x3A0D30, sabotaje detectado). 17.685 funciones, 641.532 instr., **0 sin soporte**, batería **463/463** (3 formas `vstmia` nuevas), compila en 55 s. La forma perdida 461→460 NO era `mov pc, lr`: era basura de la función falsa 0x3A8FA4 (.rodata).
- **B arranque:** obstáculos 4-8 resueltos (BITACORA.md). Primer IPC = `srv:` RegisterClient (0x00010002) en 0x102B1C. El exe con servicios corre 60 s, 9 hilos, **417 IPC** (srv 17, APT 9, ndm 3, fs 3, RomFS 202, cfg 2, gsp 138, hid 2, dsp 40). **Se para en `rt_externo 0x2DDC24`** (blx r1 en 0x2F226C, método 0x14 de una vtable que no está en code.bin: ¿armada en ejecución?). Log dice "SIN APT:U". Herramienta `recomp\arranque\unicorn_arranque.py`.
- **C capa IPC** (`recomp\sistema\`): despachador + srv + fs (RomFS desde la ROM descifrada, var `SM3DL_ROM`) + stubs + `enchufes.c`; 99/99 con hid/gsp/pica/dsp; 3 sabotajes. VBlank/HID/DSP corren en `sis_periodico` (solo avanzan si algún hilo hace svc).
- **D hid:** `recomp\hid\servicio_hid.c`; cadena del mando en `reportes\hid.md`.
- **E gsp:** `recomp\gpu\` 438/438, 6 sabotajes. Falta ventana (callback `presentar` en NULL).
- **F PICA:** `recomp\render\pica.c` = Python en 830/830. Modo inmediato (FIXEDATTRIB 15) sin hacer.
- **G TEV:** 332/332 iguales a `tools\tev_ref.py` en GPU (antes 59/332; 5 errores arreglados en `tev_glsl.py`).
- **H audio:** `recomp\audio\dsp.c` 0 diferencias en 70.400 muestras; WASAPI en vivo. Compilar con `-ffp-contract=off`. Sin escuchar.
- **I luz por fragmento:** 105/105 configuraciones (90,5 % de materiales), `extraido\shaders\luz\`.
- **J censo IPC:** `extraido\ipc_comandos.tsv` (139), solo 9 servicios; `reportes\ipc_censo.md`.
- Yo: `tools\shbin.py f24()` con exponente 0 = denormal (m·2^-78, como Azahar); probar_shaders 3.648/3.648 (por defecto; ayer se anotó 4.800, causa de la diferencia no confirmada).

## Sesión 8 oct (tarde, sin agentes) — EL JUEGO CORRE SU BUCLE PRINCIPAL
- **Pedidos de B integrados en `recomp.py`** (batería 463/463, retcalc 3000/3000, 0 sin soporte): `ldr pc,[sp],#k` = retorno; `derivadas()` + `punteros_relativos()` + `punteros_internos()` dentro de `tamanos()`; saltos directos a código sin función (`SUELTOS`, `main --todo` regenera hasta 4 vueltas); `es_literal()` (palabras de literal pool nunca son función: quitó la falsa 0x1187E4). `recomp\arranque\generar.py` ahora solo llama a `recomp.py --todo` (copia vieja en `generar_copia_8oct.py`/`parchear_copia_8oct.py`).
- **Obstáculos del arranque resueltos (todos en el traductor salvo el último):**
  1. 0x2DDC24: método vacío (`bx lr`) detrás de un literal pool, dentro de 0x2DDAF8 de Ghidra. B se equivocó: el puntero SÍ está (vtables 0x3D70B0/0x3D96A0). `punteros_internos` acepta destinos tras un literal pool.
  2. printf colgado: `__vfprintf` (0x10AED4) fija `lr` 4-5 instrucciones antes del `mov pc, r1` al callback; `llamadas_manuales` miraba 3 → ahora 8, cortando en saltos (y `bl` ya no se salta). Diferencial `recomp\prueba_printf.py` 60/60 con sabotaje detectado (la nativa se cae).
  3. 0x1EB918: ctor detrás de pool cargado como LITERAL de .text (0x1E9820) → `punteros_internos` también mira literales de .text, solo si caen tras un pool; `valida()` rechaza saltos fuera de .text (una versión laxa metía ~9.000 instr. de datos con `bl` negativos).
  4. 0x36DC24: `switch` `ldrlo` con el `cmp` 8 instrucciones antes → `tabla_saltos` busca hasta 12, cortando en saltos/banderas/escrituras del índice (161 switch).
  5. Lectura en 0x02F37100: el juego abre los **datos de Mii** (archive NCCH 0x2345678A, título 0x0004009B_00010202) y, si falla, parsea un buffer vacío. `fs.c` sirve ahora títulos de sistema desde `extraido\sistema\<HIGH>_<LOW>_*.romfs` = reemplazos de código abierto de Azahar (`externals\open_source_archives`: Mii, fuente compartida, países, palabras), crudos como Azahar.
- **Resultado: 70 s sin caerse, bucle de frames real** (`[gsp-est]` cada 2 s): ~60 vblanks/s, ~90 listas PICA/s, ~180 fills/s, ~90 DisplayTransfer/s, ~120 swaps/s. Capturas (`recomp\arranque\capturas\*.ppm`, mosaico con `capturas_png.py`): pantallas en **azul liso** = el color de limpieza del juego (MemoryFill RGBA8 `0x0000FFFF` = R0 G0 B255 A255; profundidad `0x00FFFFFF`), porque `pica_dibujar` está vacío. NO es error de canales (verificado con los valores crudos).
- Herramientas nuevas: `recomp\arranque\cadena.py` (pila del anfitrión = cadena de llamadas del juego, resuelta con el PDB; el manejador de `main.c` imprime registros del juego, palabras de pila y la pila del anfitrión), `recomp\trazar_prueba.py` (C instrumentado: traza de entradas a funciones), `recomp\prueba_printf.py`.
- 🪛 `timeout N py ...` mata a Python pero NO al exe hijo del arnés (`Nativa`): queda vivo y bloquea el .exe para el enlazador ("Permission denied"). Matar por PID los `prueba_*.exe` propios.
- 🪛 Un arnés diferencial incompleto (faltaba el callback de LECTURA 0x289EA0) simula un cuelgue que no existe: antes de culpar al traductor, confirmar que el destino está en el exe de prueba.

## Rasterizador — preparación (8 oct, final de la tarde; el backend NO está escrito)
- **Censo de dibujos** (`SM3DL_CENSO_DIBUJOS=1`, en `recomp\render\pica_dibujar.c`): ~40 dibujos por lista, **un solo programa**: `nwfont_RectDrawerShader` (texto de NintendoWare; la memoria de programa tiene sus 104 palabras + restos de 008F2C detrás), 1 atributo `vec4` float, ≤78 vértices, listas de triángulos, al RT de arriba `0x18000080` 240x400. Es una pantalla de texto (aviso/carga): primer objetivo ideal. Vuelca `recomp\arranque\vs_<hash>.bin` por programa nuevo.
- **Hecho y compilando:** `tools\tabla_programas.py` → `extraido\shaders\glsl\programas.tsv` (vert, main, palabras, FNV-1a32 del código: se compara el PREFIJO de n palabras, porque quedan restos detrás); ganchos en `gsp.h/.c` `gsp_antes_de_leer(fis, tam)` (antes de DisplayTransfer/TextureCopy/presentar) y `gsp_tras_fill(ini, fin, valor, control)` (después de MemoryFill), en NULL hasta que exista el backend; `PicaIndices.es_elements` (DRAWELEMENTS vs DRAWARRAYS). Build verificado: corre igual que antes.
- **Diseño del backend (`recomp\render\raster_gl.c`, a escribir):**
  1. Contexto WGL oculto creado en el primer dibujo (todas las fibras corren en el mismo hilo del SO), 3.3 core o 4.5; `glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE)` (los .vert ya hacen `gl_Position = (x, y, -z, w)`). Funciones por `wglGetProcAddress` con una lista X-macro; enlazar `-lopengl32 -lgdi32`.
  2. Un FBO por render target (clave color_dir; RGBA8 + D24S8), en coordenadas PICA (240x400). Al crearlo, subir la memoria (desembaldosar con `gsp_offset_morton`, bytes RGBA8 en memoria = A,B,G,R). `gsp_tras_fill` sobre color_dir → `glClear` con r=v>>24, g=v>>16, b=v>>8, a=v (0x0000FFFF = azul); sobre depth_dir → clear de profundidad (v & 0xFFFFFF)/0xFFFFFF y stencil v>>24. `gsp_antes_de_leer` que solapa un RT con dibujo pendiente → `glReadPixels` + embaldosar a memoria. Orientación memoria(x,y) = GL(x,y) de arranque; si el texto sale invertido, voltear.
  3. Vértices en CPU: por loader, offsets con alineación al tamaño del elemento (byte/ubyte 1, short 2, float 4; comp 12-15 = relleno de 4·(c-11) bytes); valores SIN normalizar; fijos de `atr_fijo`; `v_k` ← atributo `permutacion[k]`; índices u8/u16 en `base + idx.offset`; expandir a `glDrawArrays` (0 triángulos, 1 tira, 2 abanico).
  4. Programa = `.vert` de `programas.tsv` + salidas por semántica (de los comentarios `// color.xyzw`, `// texcoord0.xy`…) a `vtx_color`/`texcoord0..2`, las entradas de los `.frag` TEV. Uniforms `pica_c[96]`, `pica_i[4]` (y,z con signo), `pica_b[16]`.
  5. Fragmentos: 1ª pasada color de vértice × tex0 (ver geometría); luego TEV como uber-shader por uniforms con la semántica q8 de G (verificarlo contra `tools\tev_ref.py`), luego luz (I). Texturas con `tex_decodificar` (fila 0 ARRIBA) y caché por dirección + hash.
  6. Estado: blend (factores PICA 0-14, ecuaciones 0-4; `blend_activo=0` = logic op), depth (func PICA 0-7), color_mask; culling y scissor apagados en la 1ª pasada.

## Sesión del rasterizador (tras el cierre del 8 oct) — PRIMER FRAME + VENTANA + CONTROLES
- **`recomp\render\raster_gl.c` escrito y andando** (diseño de arriba, pasos 1-4 + fragmento simple): contexto WGL 4.5 core oculto (Intel UHD 770), `glClipControl(LOWER_LEFT, ZERO_TO_ONE)`, un FBO por render target (RGBA8 + D24S8), vértices armados en CPU (16 registros de entrada intercalados), programa elegido por `programas.tsv`, fragmento = `min(abs(color),1)` × tex0 + alpha test + `gl_FragDepth = z·escala + offset`; blend / logic op / depth / color mask. Sincronización: `gsp_antes_de_leer` → `glReadPixels` + embaldosar; `gsp_tras_fill` → `glClear` (o resubir la memoria si el fill es parcial). Texturas: `tex_decodificar` + caché por dirección/forma/hash, y antes de leer una textura se vuelca el RT que la solape (render a textura).
- **Resultado:** ~75.000 dibujos en 25 s, 0 errores GL, sigue a ~60 vblanks/s. **Pantalla de arriba = logo de SUPER MARIO 3D LAND; abajo = diálogo "Welcome to SUPER MARIO 3D LAND! Ⓐ OK"** (`recomp\arranque\capturas\mosaico.png`). Orientación, colores, texturas y fuente correctos a la primera.
- **Orientación (leída en Azahar, no supuesta):** framebuffer `fila_mem = alto-1-y` (`sw_framebuffer.cpp DrawPixel`); texturas SIN voltear (`texturas.c` ya invierte y `sw_rasterizer.cpp` invierte `t` otra vez).
- 🩹 **Corrección del diseño:** la permutación de entradas es `v[permutacion[a]] ← atributo a` (Azahar `ShaderUnit::LoadInput`), NO `v_k ← atributo permutacion[k]` como decía el paso 3 de arriba y el comentario de `pica.h` (ya corregido).
- **Ventana (`recomp\render\ventana.c`):** GDI `StretchDIBits`, las dos pantallas apiladas como la 3DS (abajo centrada), `SM3DL_ESCALA` (1-4, por defecto 2), DPI-aware, cerrar = salir. `hid.c` lee el teclado SOLO con la ventana activa (`hid_teclado_activo`; antes `GetAsyncKeyState` leía teclas de otras ventanas).
- **Controles verificados de punta a punta:** tecla X (= botón A) avanza el diálogo a "Before you get started... StreetPass!" (`capturas\ventana_antes.png` / `ventana_despues.png`). Teclas: X=A Z=B S=X A=Y Q=L W=R Enter=Start Retroceso=Select, flechas = cruceta, IJKL = circle pad; o mando XInput.
- `main.c`: `SM3DL_SEGUNDOS=N` sale limpio a los N s vaciando stderr (con `_IOLBF` el CRT de Windows usa búfer completo: matar el proceso dejaba el log en 0 bytes).
- Cómo correrlo (desde la raíz): `SM3DL_SIN_TRAZA=1 ./recomp/arranque/sm3dl.exe 2> log.txt`. `SM3DL_SIN_RASTER=1` apaga el rasterizador.
- Hoy solo se usa `nwfont_RectDrawerShader`; los otros 15 programas compilarán al aparecer (si alguno falla, sale en el log `[raster] ... no compila`).

## Tanda nocturna (3 agentes a la vez) — bitácoras en `agentes_noche\<id>.md`, reglas en `agentes_noche\BRIEF_COMUN.md`
- **P (progreso):** entrada por guion `SM3DL_GUION`, capturas configurables, avanzar diálogos sin humano, censo de programas por pantalla, diagnóstico de obstáculos. Dueño de `hid\*`, `main.c`, `enchufes.c`, `ventana.c`.
- **R (rasterizador):** uber-shader TEV, luz por fragmento, stencil/culling/scissor, modo inmediato. Dueño de `render\*` (menos `ventana.c`).
- **S (servicios):** SaveData/ExtSaveData/SharedExtSaveData (`OpenArchive 0x7` sin soporte), APT:U, cecd/mic/ptm/frd… Dueño de `sistema\*` (menos `enchufes.c`).
- `compilar.py -o <exe>`: cada agente enlaza SU exe; `juego.a` y `recomp.py` solo los toca la sesión principal.
- **Audio (sesión principal):** el backend WASAPI **nunca se abría** (nadie llamaba a `audio_salida_iniciar`): toda la cola se descartaba. Ahora se abre con el primer frame del DSP (`SM3DL_SIN_AUDIO=1` lo apaga). Diagnóstico nuevo: `[audio] muestras pico rms vacia descartes` cada ~2 s y `SM3DL_WAV=<x.pcm>` + `tools\pcm_a_wav.py`. Medido: sonido real los primeros 2 s (pico 12.493) y luego silencio en la bienvenida. **El DSP corre a la MITAD** (~16.800 muestras/s): `Sleep(4)` dura 15,6 ms sin `timeBeginPeriod` y `correr_periodicos` tira los ticks atrasados → pedido a S.
- `tools\respaldar.py <etiqueta>` = el zip de respaldo de cada cierre (sin `.venv_gl`, generados ni assets).

### Resultados de la tanda nocturna (cierre pedido por el dueño a los ~35 min)
- **P: NIVEL 1-1 ALCANZADO sin humano** (`agentes_noche\P\hitos\nivel_1_1_v5659.png`: HUD "W1-1", reloj 493, monedas, pantalla de abajo "NO ITEM"; también mapa del Mundo 1, título, selección de archivo, "file has been created"). OJO: el 1-1 se vio con el build de diagnóstico de P (`agentes_noche\P\compilar_diag.py --estable --topo3` = raster de ANTES de R + topología 3). Falta: Mario no se ve, todo el 3D en gris (sin TEV/luz), 4 programas fuera de `programas.tsv` (fnv512 9FCCAA64, 088F5431, 07A0E153, E29EC423). Guiones en `agentes_noche\P\guiones\` (g2 = cancelar StreetPass hasta título; g3 = hasta Mundo 1; g6 = mapa → entrar al 1-1). Su sabotaje del guion NO fue concluyente (el control tampoco avanzó en esa corrida de 13 s): repetirlo.
- **S: guardado real** (SaveData/ExtSaveData/SharedExtSaveData/SystemSaveData bajo `SM3DL_GUARDADO`, códigos de error exactos; tabla en `sistema\svcs.md`), APT applets sin pantalla (EULA aceptada, selector de Mii → Mii estándar; "cancelado" hace que el juego lo relance en bucle), cecd en carpeta, ptm/ac/frd/gsp::Lcd/… registrados. `prueba_guardado.c` 126/126 (3 sabotajes vistos), `prueba_ipc` 97/97. Reloj de periódicos: temporizador de alta resolución + recuperar 8 ticks → audio 99 % (32.400/s; sabotaje 15.700/s). Corrida final: 0 "sin soporte"/"SIN IMPLEMENTAR".
- **R: raster reescrito** (`raster_gl.c` + nuevo `raster_uber.c`): TEV en enteros u8 **332/332 recetas reales = tev_ref.py con 0 LSB** en GPU, luz por fragmento por registros, OUTMAP real, profundidad corregida (signo), scissor/culling/stencil/clip/niebla, texturas 0-2 con mipmaps y wraps, modo inmediato, topología 3 = lista. Shader especializado por clave (`SM3DL_RASTER_UBER=1` = versión por uniforms). Título 2D más fiel que antes. **PROBLEMAS ABIERTOS:** (a) **3D con luz muy lento**: `dibujar` 56 s de 75 s (sospecha: re-subir la textura de LUTs en cada dibujo y/o compilar por clave de luz); (b) P vio que con el raster de las 14:22 el texto de los diálogos no se dibuja (`P\cap11`) — no re-verificado con la versión final; (c) aleatorias 247/300 antes de arreglar la caché llena: NO re-corridas; 10 sabotajes preparados SIN correr; luz/stencil/culling/scissor/niebla/mipmaps/inmediato sin verificar. Respaldos `recomp\render\*.antes_R` (los 7 archivos) para volver al raster viejo.
- **Sesión principal:** backend de audio abierto (antes nunca), `[audio]` en el log, `SM3DL_WAV` + `tools\pcm_a_wav.py`, `compilar.py -o`, `tools\respaldar.py`. Con todo junto, `compilar.py` enlaza sin errores.
- ⚠️ `guardado\` compartido tiene el archivo A = WORLD 1 (lo escribió P): el juego arranca en el título. Para ver la bienvenida, usar `SM3DL_GUARDADO=<carpeta vacía>`.

## Sesión de velocidad del 3D (solo, sin agentes) — NIVEL 1-1 A COLOR CON MARIO, exe normal
- **Medición por tramos en `dibujar`** (`raster_gl.c`, línea `[raster]   tramos:` cada 3000 dibujos: programa / vértices / texturas / LUTs / uniforms / envío, + subidas de LUT y de texturas) y tiempo de cada `compilar`/`enlazar`/"programa listo".
- 🩹 **El "3D muy lento" de R NO era la luz ni las LUTs: era compilar shaders la PRIMERA vez.** 83 s de `programa` en la 1ª corrida (69 fragment shaders nuevos, ~1,2 s c/u); en la 2ª corrida 0,7 s. El driver de Intel difiere la compilación real (nuestro `compilar`/`enlazar` mide 2-5 ms) y **guarda los binarios en su caché de disco**: un shader cuesta solo la primera vez que aparece en la máquina. Para comparar velocidad, correr DOS veces y medir la segunda.
- LUTs: `pica.c` sube `luz_lut_ver`/`niebla_lut_ver` solo si la escritura CAMBIA el valor; `preparar_luts` sube solo las tablas (filas) que cambiaron con `glTexSubImage2D`. Igual hay ~1.500 subidas de tabla/s reales (el juego cambia LUTs por material): 7,5 s de 150.
- **Resultado (`sesion_vel\hitos\`, guion g6 + `guardado_w1_base`, exe normal `sm3dl.exe`):** título → cinemática 3D **a color con luz** (castillo, Mario, Toads, Peach/Bowser) → mapa del Mundo 1 **con Mario visible** → "WORLD 1-1" → **nivel 1-1 con Mario, escenario, HUD, reloj 500→485** → menú PAUSE. 7.796 vblanks en 150 s (~52/s). Respuesta al punto 3 viejo ("¿por qué no se ve Mario?"): era el raster viejo sin TEV/luz; con el de R se ve.
- Tiempos en 150 s (caché caliente): bajar (glReadPixels = espera a la GPU) 64 s, dibujar 55 s (programa 19 = shaders nuevos del 1-1, vértices 17, LUTs 7,5, envío 5,6, texturas 2,8).
- Respaldos de esta sesión: `recomp\render\raster_gl.c.antes_vel`, `raster_uber.c.antes_vel`, `pica.c.antes_vel`, `recomp\gpu\gsp.c.antes_vel`, `gsp.h.antes_vel`.

### Segunda parte de la sesión de velocidad — tres arreglos medidos (110-125 s del guion g6, caché del driver caliente)
| | antes | después |
|---|---|---|
| espera de `glReadPixels` (bajar) | 64 s / 150 s | **0,05 s** |
| armar vértices + envío | 14,3 + 4,9 s | **5,7 + 2,4 s** |
| LUTs de luz | 6,4 s (200.000 subidas) | **1,0 s (18 subidas)** |
- **DisplayTransfer diferido** (`raster_gl.c` "DisplayTransfer diferido", ganchos nuevos en `gsp.h`: `gsp_transfer_diferido`, `gsp_antes_de_escribir`, `gsp_presentando`): el transfer de un RT se lee a un PBO con fence y se completa después, en orden FIFO (cola de 4). La presentación del vblank solo completa lo que la GPU YA terminó (si no, muestra el cuadro anterior: **1 cuadro de retraso**, visto como desfase de cámara en `hitos\dif_616.png`, no error de dibujo). Lo que lee o escribe la memoria del RT o de la salida completa antes. `SM3DL_SIN_DIFERIDO=1` = camino viejo.
  - 🩹 **El juego dibuja las DOS pantallas en el MISMO RT** `0x18000080` (240x400); el transfer de la de abajo lee desde la fila 80 (`0x18012C80`, entrada 240x400 recortada a 320, **se sale 80 filas del RT**). Por eso el diferido acepta una entrada que EMPIEZA dentro de un RT, aunque se pase del final (lo de afuera se lee de memoria).
- **Vértices con índices → rango único + `glDrawElements`** (cada vértice de imin..imax se decodifica una vez; 99 % de los vértices van por ahí) y solo las `num_entradas` que usa el shader. `SM3DL_SIN_ELEMENTOS=1` = camino viejo. Verificado: **0 píxeles distintos** en 4 cuadros de la cinemática contra la corrida anterior.
- **Caché de LUTs por contenido**: textura 256x1024 filas, tabla→fila por hash + memcmp, el shader lee `luz_fila[t]` (`raster_uber.c`). Verificado igual: 0 píxeles distintos en 4 cuadros. Cambió el texto del fragment shader → la 1ª corrida recompila todo (~2 min una vez).
- 🪛 **Las corridas NO son deterministas** (mismo exe, cap7 vs cap8, difieren en la cinemática): una comparación de capturas solo prueba algo donde da 0; si da distinto, comparar contra una 2ª corrida del MISMO exe antes de culpar al cambio.
- Ritmo: ~59 vblanks/s en estado estable (el juego ya iba a velocidad real; lo ganado es margen de CPU: el raster pasó de ~85 s a ~20 s por 110 s de juego). Con shaders nuevos (1ª vez) baja a ~50.

### Tercera parte — caché de programas en disco + MARIO JUGABLE
- 🩹 **La caché de shaders del driver Intel es POR NOMBRE DE EXE**: `sm3dl_vel.exe` estaba caliente y `sm3dl.exe` recompiló todo (81 s). Cada exe nuevo (cada agente con `-o`) pagaba lo mismo.
- **Caché propia con `GL_ARB_get_program_binary`** (`raster_gl.c` "cache de programas enlazados en disco"): cada programa enlazado va a `extraido\shaders\cache_gl\<hash vert>_<hash frag>_<gs>_<hash driver>.bin` (113 programas = 19 MB; no entran al respaldo). Los textos de los shaders se guardan y **se compilan solo si no hay binario**. Verificado: exe con nombre nuevo → 113 del disco, 0 compilados, `programa` **81 s → 1,1 s**, 59 vblanks/s. Si el driver cambia de versión, el hash cambia y se recompila solo. `SM3DL_SIN_CACHE_GL=1` la apaga. Intel NO tiene `parallel_shader_compile` (sí `get_program_binary`).
- **Mario se juega** (guion `sesion_vel\guiones\g7_jugar_1_1.txt`, hoja `hitos\hoja_jugando_1_1.png`, resumen `hitos\resumen_sesion.png`): camina con el circle pad, la cámara lo sigue, salta, golpea un bloque "?" y salen monedas, el bloque queda usado, colisiones con plataformas OK. ~58 vblanks/s.

- **El dueño lo jugó en vivo** (ventana + teclado, ~2,5 min): 0 errores en el log, audio con señal real (pico 32768: revisar si satura), 18 shaders nuevos compilados y ya guardados en la caché en disco. Para abrirlo: desde la raíz, `SM3DL_SIN_TRAZA=1 SM3DL_GUARDADO=sesion_vel/jugar ./recomp/arranque/sm3dl.exe` (copia de `agentes_noche/P/guardado_w1_base` en `sesion_vel/jugar`).

## GPU dedicada (7 oct, tarde) — `sm3dl.exe` = NVIDIA, `sm3dl_intel.exe` = "PC mínimo"
- Antes TODO corrió en la Intel UHD 770 (el exe no pedía la dedicada). `main.c` exporta `NvOptimusEnablement`/`AmdPowerXpressRequestHighPerformance`; `compilar.py --gpu-integrada -o sm3dl_intel.exe` las quita. Respaldo del exe viejo: `sm3dl.exe.antes_gpu`.
- `SM3DL_VENTANA_OCULTA=1` (`ventana.c`): pruebas en segundo plano sin aparecer encima del dueño. Corredor: `sh sesion_gpu/correr.sh <exe> <etiqueta>` (g7, 125 s) + `py -I sesion_gpu\comparar.py <etiquetas>`.
- **Medido (g7, 125 s, caché caliente):** NVIDIA 59,1 vblanks/s, dibujar 18,7 s · Intel 59,2/s, 17,4 s. **Iguales**: el raster ya está limitado por CPU (decodificar vértices ~5-6 s, texturas ~3 s), no por la GPU. Única ganancia real: **compilar un shader nuevo ~0,46 s en NVIDIA vs ~1,2 s en Intel**. Caché `cache_gl\` separada por driver (la 1ª corrida en NVIDIA compiló todo: 99 en 46 s).
- Regla: desarrollar con `sm3dl.exe`; al cerrar sesión, una corrida con `sm3dl_intel.exe` como control de "PC mínimo".

## 5 shaders recuperados + TURBO para pruebas (7 oct, tarde)
- 🩹 **Los 5 "programa desconocido" se SALTABAN sus dibujos**: eran sombras y efectos (sombra redonda del árbol, silueta/sombra sobre muros, polvo). Origen: **4 DVLB dentro de `code.bin`** (0x2AC800, 0x2ACC00, 0x2ACE80, 0x2E2B50) + `SystemData\primitive_renderer_ctr.bsm`; `shbin.py extraer` solo miraba 2 SZS. Arreglo: `todos_los_dvlb()` también recorre code.bin y SystemData; `programas.tsv` 16 → 21 (filas viejas intactas, respaldo `.antes_7oct`). Quedan sin traducir 2 entradas geometry (`setemit`), no usadas aún. Buscador: `tools\buscar_shader_rom.py` (lee los volcados que el raster deja en `extraido\shaders\desconocidos\` cuando ve uno nuevo).
- **Turbo**: `SM3DL_TURBO=1` = reloj virtual en `sistema.c` (si nadie puede correr, el reloj salta al próximo evento en vez de dormir); `SM3DL_HASTA_VBLANK=N` sale limpio; `SM3DL_RASTER_DESDE=N` engancha el raster recién en el vblank N (la intro corre a velocidad de CPU: sin raster ~360 vblanks/s = 6× real). Corredor: `sh sesion_gpu/correr_turbo.sh <etiqueta> [guion] [hasta] [captura_cada]` (+ `SM3DL_RASTER_DESDE=…` delante). **g8 completo: 190 s → 52 s.**
- Con raster, el turbo solo daba ~1,25×: el freno era el raster en CPU (decodificar vértices, texturas, diferidos). Vértices ya resuelto (abajo); quedan texturas (~5,5 s) y LUTs (~3 s).
- **HECHO (misma tarde): camino NATIVO de vértices** (`armar_crudo` en `raster_gl.c`): los bloques de cada loader se suben crudos y la GPU convierte byte/ubyte/short/float (`glVertexAttribFormat` + `glVertexAttribBinding` + `glBindVertexBuffer`, **un VAO por layout**, cacheado; constantes con `glVertexAttrib4f`). 🩹 La 1ª versión con `glVertexAttribPointer` por dibujo NO ganaba nada: el hilo del driver NVIDIA revalidaba el formato en cada dibujo y se comía la CPU (todos los tramos subían). Con VAO por layout: **dibujar 33,8 → 15,5 s (NVIDIA)** y **29,3 → 15,3 s (Intel, 2ª corrida; la 1ª compila variantes del shader por formato, una vez)**; vértices 15,5 → 2,8 s, envío 3,5 → 0,5 s. Verificación exacta en proceso `SM3DL_VTX_VERIFICAR=1` (simula lo que leerá la GPU y compara bit a bit con `armar_vertices`): **17.500 dibujos, 0 distintos** en NVIDIA e Intel; sabotaje `SM3DL_VTX_SABOTAJE=1` → 4.500/4.500 distintos. `SM3DL_VTX_CPU=1` = camino viejo. Modo inmediato y stride 0 siguen por CPU.
- 🪛 **Comparar capturas entre corridas NO verifica nada aquí**: CPU vs CPU ya difiere en ~35/37 capturas (fase de animación). Para verificar un cambio del raster, comparar DENTRO del mismo proceso.
- `correr_turbo.sh` acepta `SM3DL_EXE=sm3dl_intel.exe`.
- Variantes `sesion_gpu\g9_{va,vb,vc}.txt` desde v7300 (hoja `sesion_gpu\hoja_g9.png`): **vb (CABAJO+CDERECHA)** llega a una zona nueva (cerca, bloque azul al fondo, caja, hueco en el muro de tierra) pero desde ~v7811 Mario ya no se ve y la cámara queda quieta; va/vc se atascan en el muro naranja. **Siguiente para no navegar a ciegas:** loguear la POSICIÓN de Mario (del actor jugador en memoria; ver `estados_actores.tsv`/`simbolos.txt`) cada N vblanks y cruzarla con `niveles_json\` del 1-1, para armar el guion con coordenadas y saber si cayó, murió o está detrás de algo.
- **Sonda de posición** `SM3DL_POS=N` (`recomp\arranque\sonda.c`): `[pos] v<vblank> actor x y z` cada N vblanks. **Confirmado:** el jugador es el `r0` de `PlayerActor_movement` (0x00132A58, por vtable) y la posición = `getTrans` = `*(actor+0x14)+4`. Gancho genérico `rt_sonda_llamar` al inicio de `rt_llamar` (lo emite `partir.py`; lld COFF NO acepta `--wrap`). `tabla.c` y `juego.a` parcheados a mano igual que el generador (respaldos `.antes_sonda`).
- Ejes del 1-1: stick derecha = +x, arriba = -z; piso bajo y=-1100/-700. **La pared que atasca es x≈3959** (en z -5200 y -6916). El nivel sigue ARRIBA y al FONDO: y≈-200, z -7250..-9600 (StartInfo 3 en (2975,-200,-7250), FirstStepB, ladrillos en x 4575); la subida probable es el `LiftKeyMove3x3` (2725,-425,-6818) o la `Rope` (2425,-900,-6100). Bandera `PoleGoal` (10425, 200, -14850). Datos: `extraido\niveles_json\FirstStageMap1__StageData.json`.
- **Grabar partidas** `SM3DL_GRABAR=<archivo>` (`hid.c` `hid_grabar`): guarda lo que juega una persona en formato de guion (botones + `STICK x y`), para repetir su recorrido en turbo.
- **Turbo con límite** `SM3DL_TURBO=N` (N≥2 = máx N× tiempo real; 1 = sin límite). `correr_turbo.sh` usa 3 y `nice`: el dueño notó el procesador caliente con el turbo sin límite.
## Sesión jugada por el dueño (7 oct, tarde) — W1-1, W1-2, W1-3 y casa misteriosa SIN caídas (13 min)
- Audio: el dueño lo calificó "10 de 10" (el pico 32768 no se nota). Efectos (tinta, brillos), power-ups y "Save complete!" OK.
- 🩹 **A8/A4 se decodificaban BLANCOS**; la PICA da **(0,0,0,a)** (Azahar `texture_decode.cpp`). Síntomas: globos-guía vacíos (ícono `MyGuideLButton`/`MyGuideAButton` = A4 blanco sobre globo blanco) y **menú de archivos con paneles negros** (degradados y sombras A8: `MyPhotoGradation`, `MyItemShadow`…). Arreglado en `texturas.c` y en la referencia `tools\texturas.py` (`SOLO_ALFA_RGB = 0`; poner 255 solo para exportar PNG visibles). **Verificado por el dueño jugando** (globo muestra "L"; menú amarillo correcto).
- 🩹 La verificación C-vs-Python daba 18/18 con LOS DOS mal: compartían el blanco y solo muestreaba modelos CGFX (**6 de 14 formatos**, sin A4/A8). Ahora `verificar_texturas_c.py` también toma los BCLIM de `LayoutData` (numeración de formato BCLIM ≠ PICA, tabla `BCLIM_A_PICA`): **47/47, 13 de 14 formatos**; con el blanco a propósito → A8 0/4 y A4 falla (sabotaje visto).
- **Signo de "prohibido" en el archivo A** del menú: lo dibuja el propio juego en un RT 64x64 RGB565 (0x23507500); al lado dibuja un RT 32x64 RGB5A1 **color piel liso** = cara de Mii sin rasgos. Hipótesis (sin confirmar en el código): el Mii no se puede armar con los datos de Mii de código abierto de Azahar (`extraido\sistema\0004009B_00010202_mii.romfs`). Opciones: volcar el archivo de Mii de un 3DS propio, u ocultar/poner cara genérica.
- **Las partidas grabadas NO se repiten igual** desde el arranque (el juego no es determinista: los menús duran distinto y todo se corre; en la repetición Mario murió en otro lado). Hace falta un **modo determinista** (reloj puramente virtual) — base también de los savestates.
- Herramientas nuevas: `SM3DL_VOLCAR_RT=<dir>` (RT chicos leídos como textura → `.rgba`). Sesiones del dueño en `sesion_juego\j1..j3` (j1/guardado = su progreso hasta W1-3).
- Guion `sesion_gpu\g8_1_1_lejos.txt`: el 1-1 va a la DERECHA (flecha del cartel); con solo CDERECHA Mario pasa canal, Goomba, bloques, árbol y se atasca contra el muro naranja (~v7600). Falta rodearlo.

## Resolución interna injugable → arreglada (7 oct noche)
- Síntoma (el dueño, sesión `sesion_juego\j8`): al subir la resolución en el menú el juego "se congela". El log lo delata: **vblanks y presentaciones siguen, listas/swaps se quedan quietos** = el juego no recibe tiempo (un solo hilo del SO, fibras).
- Causa: `raster_alta` leía el RT grande y lo **giraba píxel a píxel en la CPU en CADA vblank** (a 4x: 3 ms leer + 10 ms girar, más la conversión RGBA→BGRA de `ventana.c`), aunque el cuadro no hubiera cambiado. Medido con la misma partida (25 s): 1x ~4.600 listas, 2x ~2.200, 3x ~730, 4x **8**.
- Arreglo (`raster_gl.c`, `ventana.c`; copias `.antes_alta`): el giro lo hace un shader (misma afín, `texelFetch`, unidad 5) y se lee ya en BGRA; `Alta.gen` evita rehacer un cuadro que no cambió; la ventana solo hace `memcpy`. `SM3DL_ALTA_CPU=1` = camino viejo.
- Verificación EN EL MISMO PROCESO: `SM3DL_ALTA_VERIFICAR=1` compara GPU vs CPU: **0 bytes distintos** (840 cuadros a 2x, 420 a 4x); `=2` sabotea 1 byte → lo detecta en todos. 🩹 La primera versión daba la pantalla **negra**: la textura de `copiar_alta` se crea sin `MIN_FILTER` → incompleta → `texelFetch` = 0. La medición de velocidad de esa versión era falsa (medía negro); solo la verificación lo destapó.
- ⚠️ CORREGIDO más tarde: el juego corre **nativo a 30 FPS** (un cuadro cada 2 vblanks, 4 swaps por cuadro). "57/25 cuadros/s" eran swaps mal leídos. Métrica correcta: **swaps/vblank ≈ 2,0 = velocidad completa**.
- Respaldo `sm3dl-port-codigo-resolucion-gpu.zip`.

## 4x a velocidad completa — tanda de 2 agentes (7 oct noche, `agentes_7oct\A.md`, `B.md`, `BRIEF_COMUN.md`)
- **A (raster_gl.c):** lectura del giro en alta ASÍNCRONA (PBO + fence, anillo persistente, cero copia; `SM3DL_ALTA_ASINC=0` = síncrona); cronómetros `SM3DL_A_CRONO=1`; API para presentar por GL en `raster_gl.h` (`raster_alta_textura`, `raster_gl_hacer_actual`, `raster_alta_a_ventana`). La GPU NO es el cuello a 4x.
- **B (ventana.c, ventana_hud.c):** el cuello real era **`DwmFlush`** (vsync por DWM: 7-10 ms de espera del único hilo por vblank) → quitado (`SM3DL_VENTANA_DWMFLUSH=1` lo devuelve); pintar solo con imagen nueva (`SM3DL_VENTANA_SALTAR`, verificador `SM3DL_VENTANA_VERIFICAR`, 1.800/1.800 iguales, sabotaje visto); oscurecido del menú una vez; resolución aplicada al cerrar el menú. Presentar por GL: diseñado en B.md paso 3, NO implementado.
- Resultado: 4x a 2,00 swaps/vblank. **El dueño lo jugó: "ahora anda muy bien en x4".**

## Interpolación de cuadros: 60 FPS (7 oct noche) — `recomp\render\interp.c`, `recomp\gpu\gsp_interp.inc`
- **Estudio** (`SM3DL_ESTUDIO_INTERP`, `tools\estudio_interp.py`, `tools\estudio_punto_medio.py`): 344 dibujos/cuadro; 99,4 % se emparejan con el cuadro siguiente por HUELLA (programa, buffers, texturas, RT); el 100 % de los emparejados usa los MISMOS vértices → toda la animación va en los uniforms del VS.
- **Método:** se graban las operaciones de GPU de cada cuadro (listas copiadas, fills, transfers). Al cerrar el cuadro C se RE-EJECUTA con los uniforms de cada dibujo mezclados al 50 % con su pareja de B → el intermedio queda en el framebuffer de C; el primer vblank que muestra C muestra el intermedio y justo después se restaura C POR COPIA (memoria + copia en alta con `raster_alta_instantanea`, sin re-dibujar: no pisa el cuadro siguiente). Resultado: intermedio, real, … = 60 FPS con 1 vblank de retraso.
- **Frontera de cuadro:** el juego usa TRIPLE búfer y dibuja en ESTÉREO aunque el 3D esté en 0: cada cuadro = [ojo izq → transfer] [ojo der → transfer] [abajo → transfer]; la transfer de ABAJO cierra el cuadro. En tiempo real a veces se funden 2 cuadros (4 transfers de arriba): esos no llevan intermedio.
- **Reglas de mezcla:** HUD/2D (sin prueba de profundidad) NO se mezcla (íconos del atlas se cruzaban: reloj → cabeza de Luigi); pareja = la de uniforms MÁS CERCANA (`SM3DL_INTERP_CERCANO`, por defecto en el código: ver interp.c) — medido en 300 cuadros: intermedio a ~1.600 px del real vs ~1.950 por orden (sin interpolar ~4.100); grupos repetidos con distinta cantidad de copias no se mezclan (`SM3DL_INTERP_REPETIDOS`).
- **Verificadores** (todos con sabotaje visto fallar): prueba de laboratorio `SM3DL_REPETIR=<vblank>` (EXACTA 0 px, SABOTAJE 96.000 px, ORO 747 px visibles vs 11.312 sin interpolar); `SM3DL_INTERP_VERIFICAR=1` restauraciones de memoria y de copia en alta exactas (1.200/1.200; `=2` → 1.200/1.200 fallan); detector de destellos de laboratorio `SM3DL_REPETIR_CADA=N` y en vivo `SM3DL_INTERP_DESTELLOS=<dir>` (+ `SM3DL_INTERP_SECUENCIA=<vblank>` vuelca 12 vblanks seguidos de lo mostrado).
- 🩹 Bug cazado: la transfer de abajo de una RE-EJECUCIÓN volvía a entrar a `quizas_cerrar_cuadro` y liberaba las operaciones del cuadro en medio de su propia re-ejecución.
- 🩹 Métrica: comparar bytes de RGB565 exagera (un nivel de verde = 32 en el byte bajo); se compara por PÍXEL en RGB (`comparar`, "VISIBLES" = >16 niveles).
- **Menú:** "Cuadros por segundo: 30 (original) / 60 (interpolados)" (`fps=` en `sm3dl_ajustes.ini`; `SM3DL_INTERP` manda en pruebas). Lanzador **`JUGAR.bat`** (partida en `sesion_juego\jugar\`).
- **El dueño lo probó:** parpadeos SUTILES en **partículas y cosas pequeñas** (no reproducidos por los detectores, que cuentan >300 px). Causa probable: objetos repetidos (misma huella) emparejados con otro. Mitigaciones aplicadas: pareja por cercanía + regla de cantidades + **UN SOLO OJO** (abajo). Pendiente: que lo vuelva a probar.

## Un solo ojo (7 oct noche, idea del dueño) — `gsp.c` (`gsp_ojo_derecho`), `pica_dibujar.c`
- El ojo derecho es la mitad del trabajo 3D y nunca se ve. Se aprenden los fb derechos de lo que el juego configura (`info[2]` del swap); tras la transfer del ojo izquierdo, los dibujos de arriba (viewport 400) no se rasterizan ni se graban para interpolar, y la transfer del derecho no se hace. Salvaguarda: si tras el izquierdo llega una transfer que no es al derecho → aviso `[un-ojo] AVISO` y salto apagado 120 cuadros. `SM3DL_UN_OJO=0` lo apaga.
- Estado: compila; en menús/arranque 0 avisos. **Falta medirlo en el 1-1** (las corridas mientras el dueño usaba el PC no llegaron al nivel: el guion por vblanks se desfasa si las cargas tardan).
- **Prueba del dueño (con un ojo):** "ya no está parpadeando" (partículas OK). Notó: audio "un poco extraño" y el **pozo de veneno morado** fallando un poco.
- Log de esa sesión: **44 % de intermedios no llegaron a verse** (con un ojo el juego se adelanta y había UN solo pendiente) → **varios pendientes** (uno por framebuffer, hasta 4; si el fb se reusa, el viejo se descarta sin restaurar; si el cuadro ya está en pantalla al cerrar, no hay intermedio). Tiempo real a 4x: 1.499/1.500 mostrados, restauraciones exactas (memoria y alta, por ranura).
- **Veneno:** regla de SALTOS en interp.c: componente en [-1,5; 1,5] que cambia ~1 (0,6..1,4) = coordenada de textura que da la vuelta o interruptor 0↔1 → valor real, no mezcla. La regla amplia (|d|>0,25 y >m/2) congelaba 12 % de los valores y empeoraba: descartada. Sin escena de veneno en las pruebas: falta que el dueño lo confirme.
- **Audio:** los huecos (`vacia=`) solo crecen al abrir el menú (pausa); durante el juego, 0. Falta que el dueño describa qué suena raro.
- 🩹 **Métrica de velocidad correcta: cuadros/vblank = transfers/3 por vblank (0,50 = 30 FPS completos).** "swaps/vblank" varía por otras razones. La sesión real del dueño: 0,50 constante.
- 🪛 Guion robusto que llega al 1-1 aunque las cargas tarden: A cada 40 vblanks de 900 a 2300 y movimiento desde 2400 (en el scratchpad de la sesión; rehacer así).
- 🪛 Las pruebas llevan **`SM3DL_SIN_AUDIO=1`** (el dueño escuchaba el audio de las pruebas mientras usaba el PC).
- Pendiente (auditoría de un agente, sin medir): `StretchDIBits` con HALFTONE (filtro suave) de 1600x960 cada vblank; `DwmFlush` bloquea el hilo con vsync; `componer_unica` y el oscurecido del menú se rehacen cada vblank/16 ms aunque nada cambie; `raster_escala` se aplica en cada pulsación del menú (aplicar al cerrar). Solución de fondo: **presentar por GL** (`SwapBuffers`) en vez de GDI — la imagen ya está en la GPU.

## PRÓXIMA SESIÓN — por dónde empezar (cierre 7 oct noche: 4x + 60 FPS interpolados)
1. **Preguntar al dueño** por su última prueba (exe 21:00, con varios pendientes + regla de saltos): ¿sigue fallando el **pozo de veneno morado**? ¿Cómo suena raro el **audio** (rápido/lento, chasquidos, desfasado)? ¿Pasa también con "30 (original)"? Revisar `sesion_juego\jugar\log.txt`.
2. Si el veneno sigue: llegar a esa escena (preguntar en qué nivel), volcar vblanks seguidos (`SM3DL_INTERP_SECUENCIA`) y MIRARLOS; identificar el dibujo (programa/huella) y su uniform de textura.
3. Presentar por GL (diseño en `agentes_7oct\B.md`, paso 3; API de A en `raster_gl.h`): base para >60 FPS (120/200 = varios intermedios por cuadro con t=0,25/0,5/0,75 y ritmo propio, sin atarse al vblank).
4. Quitar el diagnóstico temporal de `pica_dibujar.c` (`SM3DL_ORDEN_DIBUJOS`) cuando ya no haga falta.

## (anterior) PRÓXIMA SESIÓN — por dónde empezar (cierre de la sesión de velocidad)
1. **Jugar más lejos**: guion más largo por el 1-1 (enemigos, tubos, bandera) y ver qué se rompe (efectos, partículas, programas fuera de `programas.tsv`, audio). Probar con la ventana y el teclado en vivo.
2. Lo que R dejó sin correr: aleatorias 300/300, 10 sabotajes, luz contra `luz_frag_ref` (ojo: el arnés de R incluye `raster_gl.c` real, que ahora tiene `luz_fila`, la caché de binarios y los textos sin compilar hasta el programa).
3. Sabotaje del guion de P con corrida larga. Agregar los 4 programas que faltan a `programas.tsv` (9FCCAA64, 088F5431, 07A0E153, E29EC423).
4. Tirón de un shader NUNCA visto (~1,2 s la 1ª vez en la máquina): segundo contexto GL compartido en otro hilo que compile mientras se dibuja con el uber (`SM3DL_RASTER_UBER`). Bajo valor ahora que hay caché en disco.
5. Audio: escuchar con `SM3DL_WAV` en el 1-1.

## (anterior) PRÓXIMA SESIÓN — por dónde empezar (cierre de la tanda nocturna)
1. **Velocidad del 3D en el raster de R** (LUTs subidas una vez por cambio de registro, caché de programas por clave) y confirmar que el texto de los diálogos sale. Meta: el guion g6 llega al 1-1 con el exe NORMAL (no el diag de P) a ~60 vblanks/s.
2. Correr lo que R dejó sin correr: aleatorias 300/300, los 10 sabotajes, luz contra `luz_frag_ref`.
3. ¿Por qué no se ve Mario en el 1-1? (programa fuera de `programas.tsv`, atributo, o dibujo saltado: mirar el censo `SM3DL_CENSO_DIBUJOS=1` en el 1-1). Agregar los 4 programas que faltan a `programas.tsv`.
4. Repetir el sabotaje del guion de P con una corrida larga.

## (anterior) PRÓXIMA SESIÓN — por dónde empezar (cierre del rasterizador)
1. Avanzar por los diálogos con la ventana (X) y ver la siguiente pantalla: el menú/selección de archivo y el primer nivel van a pedir los programas 3D (`Shader_*`), TEV real (G, 332/332), luz por fragmento (I) y OUTMAP. Correr con `SM3DL_CENSO_DIBUJOS=1` para ver qué programas aparecen.
2. Uber-shader TEV por uniforms en `raster_gl.c` (verificado contra `tools\tev_ref.py`), luego luz, stencil, culling, scissor.
3. Guardado (los diálogos de StreetPass/archivo pueden pedir SharedExtSaveData: OpenArchive 0x7 sin soporte) y "SIN APT:U".
4. Audio: `dsp.c` ya sale por WASAPI; confirmar que se oye.

## (anterior) PRÓXIMA SESIÓN — por dónde empezar (cierre 8 oct noche)
1. Escribir `raster_gl.c` según el diseño de arriba (pasos 1-4 + fragmento simple) y ver la primera captura con forma (texto). Luego TEV y texturas.
2. Ventana (Win32 + WGL) para `presentar`.
3. Pendientes viejos: "SIN APT:U"; OpenArchive 0x7 (SharedExtSaveData) sin soporte; modo inmediato de PICA.

## (anterior) PRÓXIMA SESIÓN — por dónde empezar (cierre 8 oct tarde)
1. **Rasterizar:** `pica_dibujar` (vacío) → OpenGL: vertex shaders GLSL (extraido\shaders\glsl), TEV (G, 332/332) + luz por fragmento (I, 105/105), texturas (`texturas.c`), estado de `pica.c` (blend/depth/stencil/culling). Leer el render target de vuelta a la memoria física (0x18000080…) para que DisplayTransfer lo copie. Contar dibujos por frame primero.
2. Ventana (SDL2 no está instalado; Win32 + WGL o GLFW) para `presentar`.
3. Pendientes viejos: "SIN APT:U"; OpenArchive 0x7 (SharedExtSaveData) sin soporte; modo inmediato de PICA.

## (anterior) PRÓXIMA SESIÓN — por dónde empezar (cierre 8 oct)
1. Llevar a `recomp.py`/`descubrir_funciones.py` los pedidos de B: (a) `ldr pc, [sp], #k` = retorno; (b) sembrar literales de constructores; (c) punteros relativos al PC (`ldr`+`add pc`); (d) destinos de salto rechazados por "no termina" = función; (e) punteros de vtable tras final incondicional dentro de rangos de Ghidra. Luego generar el arranque desde `recomp.py` y retirar la copia.
2. Arranque: quién escribe la vtable con 0x2DDC24 (0x2F226C, método 0x14) y el "SIN APT:U" (despertar vs. sin parámetros, C.md).
3. Ventana + `presentar` de gsp; unir luz (I) al TEV (G): 382 pares; `flip_quat.geom`; LUTs a textura.
4. `pica_dibujar`: primer dibujo con vertex shader + TEV + texturas → primer frame.

## (anterior) PRÓXIMA SESIÓN — cierre 7 oct noche
1. Llevar a `recomp.py`/`descubrir_funciones.py` los 2 arreglos del agente J (llamada `add lr,pc` + `mov pc,rX`; funciones de `.init_array`) y regenerar; batería en 460/460.
2. Aplicar el arreglo DISEÑADO del retorno calculado de 0x3A0B68 (agente O, arriba) con su diferencial y sabotaje; debe quedar 0 "sin soporte".
3. Seguir el arranque: 0x001ED5B4 desde ~0x28EAD8 → hasta el primer comando IPC → servir el RomFS por fs.
4. Conectar hid (`recomp\hid\`) y el VBlank de GSP a `recomp\sistema`.
5. Render: ejecutar las listas de comandos PICA (vertex shaders + TEV + texturas ya existen) → primer frame.

## Prueba del dueño (8 oct, mañana) — la interpolación por uniforms es la causa del veneno
- A **60 (interpolados)** en W2-2 el pozo de veneno morado se ve plano, con bordes duros, y "no parece ir a 60". A **30 (original)**: pozo correcto y fluido → el fallo es de la interpolación, no del raster.
- Decisión propuesta (pendiente del OK del dueño): dejar la interpolación por uniforms solo como respaldo y pasar a **interpolación a nivel de juego** (cámara, matrices de actores, huesos), con identidad por objeto, al estilo de los ports de la comunidad. Empezar por cámara + Mario y medir.
- `sm3dl_ajustes.ini` quedó en `fps=30` para que el dueño juegue sin el fallo.
- Ojo: el Control inteligente de aplicaciones se había vuelto a encender (bloqueó `sm3dl.exe` por "Device Guard"); el dueño lo apagó otra vez el 8 oct.

## Interpolación con SEMÁNTICA (8 oct, mañana) — `interp.c` + `interp_programas.h` (generado por `tools\gen_interp_programas.py`)
- Los DVLB del juego traen el NOMBRE de cada uniform. Programa principal (Shader_*.shbin, 12 entradas, mismo mapa): WrldMtx c0-2, NormMtx c3-5, PosOffs c6, IrScale c7-8, TexcMap c10, TexMtx0-2 c11-18, TexTran c19, MatAmbi/MatDiff c20-21, Hsl c22-24, **UnivReg c25-84 (huesos)**, **ProjMtx c86-89, ViewMtx c90-92** (proj/view en los mismos registros también en los shaders de efectos code_2AC800/2ACC00/2ACE80). Partículas (code_2ACE80): user, time, emitterVel, gravity...
- Clases por registro: OBJETO (mezcla con pareja), CÁMARA (mezcla SIEMPRE, también en dibujos sin pareja/vetados → lo 3D sigue a la cámara a 60), REAL (TexMtx/TexTran/UV: nunca se mezcla — causa probable del veneno), TIEMPO (mezcla si avanza), sin nombre (mezcla ciega + regla de saltos, lo de antes). `SM3DL_INTERP_SEMANTICA=0` = camino viejo.
- Medido (1-1, guion g7): 21/21 programas reconocidos (0 desconocidos); 60 valores/cuadro de textura animada ahora con valor real; ~10 dibujos/cuadro solo con cámara mezclada; controles: EXACTA 0 px, SABOTAJE 96.000, ORO 977 visibles vs ~22.000 sin interpolar.
- 🩹 El detector de destellos (`SM3DL_REPETIR_CADA`) marca "peor que no interpolar" ~1 de cada 6 cuadros, pero mirados (d06, vblank 5728) son movimiento NO uniforme (A≈B y C se movió): el intermedio está bien. No es un destello visible.
- **Ritmo** nuevo (`[ritmo]` en el log cada 600 vblanks, solo con 60 activo): % de vblanks con imagen nueva (60 reales = 100 %, 30 = 50 %). Medido oculto + nice, 1-1: ~90 % en el nivel; los intermedios llegan casi todos (2.699/2.700): el 10 % restante son cuadros que el juego tarda 3 vblanks en entregar.
- `sm3dl.exe` = esta versión (antes: `sm3dl.exe.antes_semantica`). Respaldo `respaldos\sm3dl-port-codigo-interp-semantica.zip`. `tools\medir_interp.sh <exe> <etiqueta> [vblank] [cuadros]` = medición repetible.
- **Falta:** que el dueño confirme el veneno en W2-2 a 60 y mirar `[ritmo]` de SU partida a 4x (`sesion_juego\jugar\log.txt`). Si el ritmo real es bajo, el siguiente paso es el ritmo de presentación (y presentar por GL).

## Hojas y nubes del veneno = PARTÍCULAS mal emparejadas (8 oct, mediodía)
- Video del dueño (W2-2, 11 s): las nubes y burbujas dentro del veneno SALTAN de lugar cuadro a cuadro; en W2-1 las hojas salían como rayas. El dueño: "arreglas esto y se arreglan las hojas".
- Diagnóstico F9 (`tools\aplicar_interp_diag.py`; F9 en vivo o `SM3DL_INTERP_DIAG=<vblank>`; vuelca en `sesion_juego\diag\NN\` mid/B/C + `dibujos.txt` con huella en pantalla y uniforms de cada dibujo). Visto en el 1-1: **`code_2AC800` dibuja VARIAS partículas por dibujo, una matriz 3x4 por partícula en c28-c84**, más parámetros del emisor sin nombre (c9 salta 6,84 → 0). Se mezclaban por casilla y a ciegas.
- 🩹 En objetos SIN esqueleto `UnivReg` no son huesos: hay posiciones de luz (c44/c53/c62). El nombre del DVLE es la unión de las variantes; cada entrada lo usa distinto.
- Medido: las partículas se mueven por cuadro casi lo mismo que la distancia entre ellas (5-12 u) → la pareja por cercanía es AMBIGUA. Decisión: por defecto las partículas y los parámetros de efectos van REALES, solo la cámara se mezcla (`SM3DL_INTERP_PARTICULAS=1` prueba la cercanía mutua). code_2ACC00/2ACE80: solo cámara.
- Matrices 3x4 (`aplicar_interp_matrices.py`): traslación mezclada; 3x3 mezclada + largo de columnas restaurado; giro > ~43° → rotación real. Neutro en el 1-1 (1.381 vs 1.369 px, mismo exe y misma corrida).
- Parejas AMBIGUAS entre dibujos repetidos (mejor > 0,5 × segunda): no se mezcla el objeto, solo la cámara (~13 por cuadro en el 1-1).
- Controles en cada paso: EXACTA 0 px, SABOTAJE 96.000. Detector 1-1: ~1.400 px vs ~11.300 sin interpolar (las reglas nuevas no lo empeoran ni lo mejoran: ahí no hay partículas grandes).
- `sm3dl.exe` = esta versión. Respaldos: `sm3dl.exe.antes_semantica`, `interp.c.antes_{semantica,diag,matrices,particulas}`, zip `sm3dl-port-codigo-interp-particulas.zip`.
- ✅ Confirmado por el dueño (8 oct): pozo y hojas bien a 60.

## Sombra de Mario rara solo a 60 (8 oct, tarde) — STENCIL
- Dueño (video W2-1, salto sobre el borde de la baranda): mancha cortada + franja en la cara vertical; a 30 se ve bien → interpolación.
- F9 con stencil en el 1-1 (salto, vblank 5712): las sombras son volúmenes de stencil por pares (op zpass 3 = suma, 4 = resta, varias copias por volumen) + una pasada que LEE el stencil (primitive_renderer, `wvp` combinado, sin cámara aparte). En un mismo grupo de 7 copias, 6 salían "vetadas" (solo cámara) y 1 mezclada → las pasadas no se cancelaban.
- Arreglo: **todo dibujo con stencil_test va COMPLETO real** (32 por cuadro en el 1-1). Forma idéntica al cuadro real; costo: la sombra va medio paso de cámara atrás en el intermedio (ORO 1.488 → 2.395 px). Mejora posible: mezclar todas las pasadas IGUAL (las copias de un grupo tienen uniforms idénticos: la regla de ambiguas no debería vetar candidatas idénticas entre sí) — pendiente, solo si el dueño nota la sombra temblando.
- `sm3dl.exe` = esta versión. Respaldo `sm3dl-port-codigo-interp-sombras.zip`.
- ✅ Confirmado por el dueño (8 oct): sombra bien a 60.

## >60 FPS: presentación por GPU + modo "Monitor" (8 oct, tarde) — `ventana_gpu.c`, `presentador_gl.inc`, `gsp_interp.inc` (alto_*)
- Decisión con el dueño: NO migrar a Vulkan/D3D12 todavía (el techo de 60 era el ritmo atado al vblank emulado + GDI, no la API). Ports de referencia: Zelda64Recompiled (RT64: Vulkan/D3D12, interpolación por matrices marcadas), Ship of Harkinian (D3D11/OpenGL, 120+). Si el driver resulta el cuello, Vulkan (acepta nuestro GLSL).
- **Presentación por GPU** (`SM3DL_PRESENTAR=gpu` o `presentar=gpu`; el modo Monitor la activa): la de arriba en alta va de `raster_alta_textura` al framebuffer de la ventana (blit), HUD integrado y UI como capas BGRA PREMULTIPLICADAS (mezclar/ui_mezclar acumulan alfa y anotan la zona sucia; se sube solo eso), `SwapBuffers` + `wglSwapIntervalEXT(vsync)`. Clase de ventana `CS_OWNDC`. 🩹 La textura girada guarda la fila 0 ARRIBA (el comentario de la API decía lo contrario: salía de cabeza).
  - Verificación `SM3DL_PRES_VERIFICAR=1` (vs camino GDI del MISMO cuadro): legítimo ≤ 0,5 % muy distintos (solo bordes, muestreo distinto al reducir 1600→1200; 80 % coincide con un vecino a 1 px); sabotaje `=2` (3 px corrido) ≥ 1,5 %. Umbral 1 %. Volcados `SM3DL_PRES_VOLCAR` + `tools\raw_a_png.py`.
- **Modo "Monitor"** (menú: 30 → 60 → Monitor; `fps=monitor`; `SM3DL_FPS_ALTO=1`): al cerrar cada cuadro, tanda de N-1 intermedios (t=k/N) + el real en ranuras GPU (`raster_pres_guardar`, DOS juegos de 8), N = refresco × duración del cuadro (144 Hz → 5). Tramo anclado al CIERRE + L (L = tanda máx. que decae + 2 ms ≈ 16-21 ms de latencia extra). Tic de 2 ms (`ventana_presentador`, sis_periodico) presenta UNA vez por refresco (DWM qpcVBlank) y también DENTRO de la tanda (`gsp_interp_tic`).
  - Medido (1-1, oculta, velocidad real): 5 por cuadro a 144 Hz, tanda ~14 ms (re-ejecución 2,8 ms CPU / 4,1 con GPU), juego a velocidad completa (2,0 swaps/vblank), refrescos con imagen repetida 36 % (v1) → **~9 %** (v2, incluye menús/cargas). Orden de ranuras verificado con `SM3DL_ALTO_TRAZA` y secuencia volcada (`SM3DL_PRES_SECUENCIA` + `tools\secuencia_a_png.py`): monótono, movimiento parejo.
  - 🩹 Una tanda que bloquea el único hilo sin presentar dentro = refrescos perdidos (36 %); el tramo anclado al FIN de la tanda se cortaba antes del cuadro real (saltos).
- `sm3dl.exe` = esta versión (antes: `sm3dl.exe.antes_alto`). Respaldo `sm3dl-port-codigo-fps-monitor.zip`. Ajustes del dueño: `fps=monitor`.
- **Falta:** que el dueño lo juegue visible a pantalla completa (allí DWM/flip independiente puede cambiar el bloqueo de SwapBuffers); medir `[alto-pres]` de SU partida; menú/título sin probar en GPU con persona.
- **8 oct, prueba del dueño a pantalla completa:** la 1ª versión se veía a ~2 FPS (el juego por dentro a velocidad completa): el presentador esperaba que `qpcVBlank` de DWM cambiara y a pantalla completa (flip independiente) se queda quieto. Arreglo (`tools\aplicar_fps_alto3.py`): refresco en curso = (QPC − fase)/periodo; DWM solo da la fase. Oculto: ~137 presentaciones/s de 144, 12 % repetidas. Log del fallo en `sesion_juego\jugar\log_congelado_2fps.txt`.
- Dueño tras el arreglo: "funcionó mucho mejor"; 60 y Monitor "muy buenos"; quedan parpadeos/artefactos MUY pequeños (casi invisibles) y el modo 30 "anda a menos" (sin medir aún). Pendiente: medir el 30 con presentación GPU (log de su partida) y video de los artefactos. F9 no existe en modo Monitor (solo en `vivo_cerrar` del 60).

## PRÓXIMA SESIÓN — por dónde empezar (cierre 8 oct tarde: modo Monitor funcionando)
Estado: 30 / 60 / **Monitor** (144 Hz, 5 imágenes por cuadro) andando con presentación por GPU; el dueño: "60 y Monitor muy buenos". Veneno, hojas y sombra arreglados y confirmados.
1. **Micro-parpadeos/artefactos "casi invisibles"** (Monitor y quizá 60): pedir VIDEO al dueño (lo que destrabó veneno y sombra). F9 solo existe en el 60 (`vivo_cerrar`): portar el diagnóstico al modo Monitor (`alto_cerrar`) si hace falta.
2. **Modo 30 "anda a menos"**: medido en su partida: el juego va a 30 parejo; la sensación es el ritmo 144/30 = 4,8 refrescos (4 y 5 alternados). Propuesta: que el 30 también presente por `ventana_presentador` (imagen real por refresco). Preguntar por G-Sync (Panel NVIDIA) o 120 Hz. Agregar log al cambiar de modo de FPS (hoy no se anota).
3. Audio "raro": sigue sin descripción del dueño.
4. Después: costo de la tanda (~14-20 ms de cada 33; latencia extra 15-20 ms); Vulkan solo si el driver resulta el cuello.
Respaldo: `respaldos\sm3dl-port-codigo-cierre-8oct-monitor.zip`.

## Modo Monitor: intermedios ALINEADOS al refresco + fin de la espiral (8 oct, noche) — `gsp_interp.inc` (alto_*), `ventana_gpu.c`, `main.c`
- Respuesta a "¿limitar a 120 Hz?": el panel solo ofrece 144 y 60 Hz; limitar por software en panel fijo da más tirones. No se tocó nada del monitor. G-SYNC sigue apagado (choca con Frame Generation, ver memoria).
- **Alineado** (`SM3DL_ALTO_ALINEADO=0` = lo de antes): un intermedio POR REFRESCO del tramo, con t = (inicio del refresco − t0)/dt (rejilla fase/periodo compartida con `ventana_presentador` vía `gsp_interp_vb`). Antes, t = k/5 fijos para 4,8 refrescos → una imagen sin ver en 4 de cada 5 cuadros. Ancla suavizada asimétrica (cierre temprano: se espera a lo previsto y se corrige 10 %; tardío: se sigue al tiro).
- **Espiral arreglada**: un tirón subía delta a ~100 ms → 8 intermedios → tanda de 50 ms → el juego se quedaba a ~9 FPS para siempre. Ahora el tramo dura a lo sumo 33,4 ms y la tanda tiene presupuesto: fijo + (n−1)·costo ≤ 55 % del tramo (`c_int`, `c_fijo` medias móviles). Log `[alto]` con intermedio/fijo/tope y `[alto-desglose]` (re-ejecutar/guardar/presentar por intermedio).
- **EcoQoS apagado** en `main.c` (`SetProcessInformation(ProcessPowerThrottling)`; `SM3DL_CON_ECOQOS=1` lo deja): con ventana oculta Windows 11 mandaba el proceso a núcleos E → re-ejecutar 7 ms → 3,8 ms.
- Métrica `[alto-paso]` (ventanas de 1440 refrescos): error medio del paso vs ideal (periodo/delta), repetidas, dobles. Partida del dueño (1-1): en el nivel 1-3 % de error, 0-11 repetidas; antes (t=k/N, oculto) 28-34 %.
- Probado "reusar el real anterior para t≈0" (`SM3DL_ALTO_REUSAR=1`, versión 2): el dueño la sintió PEOR (micro tirones al faltar presupuesto) → apagado por defecto; el plan queda igual que la versión 1.
- Exes: `sm3dl.exe` SIN CAMBIOS (= `sm3dl.exe.antes_alineado`). `sm3dl_alineado.exe` = versión 1 (la buena, "camino excelente" según el dueño). `sm3dl_alineado2.exe` = con reusar. `sm3dl_alineado3.exe` = código actual (reusar apagado ≈ v1). Respaldos `.antes_alineado` de gsp_interp.inc y ventana_gpu.c.
- Pendiente: **fantasma** (objeto duplicado por un instante a 144 = pareja mala en la interpolación; portar F9 a `alto_cerrar`). Nahimic (`NahimicSvc64`) se come un núcleo entero sin parar.
- Investigación: RT64/Zelda64Recomp = dos renderizadores en hilos + transformaciones diferidas en GPU; TriAevum (OoT3D, recomp 3DS→PC, Vulkan vía NVIDIA NRI, 60/90 FPS = múltiplos de 30). Dolphin: 144 no es múltiplo de 30.

## Paso a Direct3D 12 (decisión del dueño, 8 oct noche) — `agentes_dx12\BRIEF_COMUN.md`
- Plan de 9 pasos: 1 separar backend (agente A) · 2 shaders GLSL→SPIR-V→HLSL→DXIL (agente B) · 3 base D3D12 + swap chain flip · 4 recursos · 5 PSO + caché · 6 lecturas de vuelta · 7 presentación en hilo aparte (lo que ataca los tirones) · 8 validación por píxel vs GL · 9 medir y cambiar default. OpenGL queda de referencia (`SM3DL_BACKEND=gl|d3d12`).
- Regla nueva: los agentes NO corren el juego (el dueño se quejó del calor); las pruebas pesadas se piden con OK.

## PRÓXIMA SESIÓN — por dónde empezar (cierre 8 oct noche: paso a D3D12 en marcha)
Estado: para JUGAR, `JUGAR.bat` → `sm3dl.exe` (sin cambios hoy). Mejor versión del modo Monitor: `sm3dl_alineado.exe`
("camino excelente" según el dueño). `sm3dl_fantasma.exe` = esa + F9 en modo Monitor (volcado en `sesion_juego\diag\NN`).
D3D12 (bitácora `agentes_dx12\principal.md`):
- Hecho y probado con sabotaje: paso 1 (A: backend separado, 69/110 capturas idénticas + arnés 21/21), paso 2 (B: 741/741
  shaders a DXIL, TEV 0 LSB en WARP, caché `agentes_dx12\B\cache_d3d12\`), base D3D12 con lista continua, recursos,
  caché de PSO, presentador (0 px vs CPU) y prototipo del hilo de presentación (2,9 % de error de paso a 144 Hz).
- `compilar.py --d3d12` arma el exe con el backend D3D12 (`raster_backend_d3d12.c` + partes `.inc`).
- Agentes C (recursos) y D (dibujo) DETENIDOS a pedido del dueño antes de escribir nada: los `.inc` siguen con el
  relleno de la sesión principal y no hay `C.md`/`D.md`. Retomar = relanzarlos con `agentes_dx12\BRIEF_BACKEND.md`.
- Luego: primer cuadro del juego en D3D12 (prueba con el juego: pedir OK al dueño, calienta la laptop).
Pendientes aparte: fantasma (pedir que juegue `sm3dl_fantasma.exe` y apriete F9), línea de tiempo por nº de cuadro en
el modo Monitor GL (quita el temblor de ±3 ms), audio "raro", Nahimic se come un núcleo.

## Tanda de 15 agentes Opus (9 oct noche) — backend D3D12 COMPLETO (sin probar con el juego) — `agentes_dx12\BRIEF_15.md`
- Las 2 partes se partieron en 12 `.inc` (C1 init/ventana/presentar, C2 texturas+mips, C3 muestreadores, C4 RT, C5
  copiar/reducir/girar, C6 lecturas, C7 crono, D1 firma raíz+programas, D2 constantes+destino, D3 estado→PSO,
  D4 vértices, D5 dibujar) + E1 caché DXIL (`tools\precompilar_d3d12.py`, instalada en `extraido\shaders\cache_d3d12\`,
  732 DXIL) + E2 arnés por píxel GL vs D3D12 (`agentes_dx12\E2\tools\e2.py`, ~30 s, sin el juego) + E3 línea de tiempo
  por nº de cuadro en el modo Monitor GL (`SM3DL_ALTO_LINEA=1`, apagada por defecto; exe `agentes_dx12\E3\sm3dl_E3.exe`).
- Cada parte con prueba liviana propia + sabotaje visto fallar (bitácoras `agentes_dx12\<id>.md`). Ningún relleno queda.
  Exe integrado: `agentes_dx12\principal\sm3dl_d3d12_todo.exe` (`compilar.py --d3d12`, 0 warnings).
- E2: **23/29 escenarios IGUALES byte a byte** (tev, luz, vértices, memoria 5 formatos, alta x2/x3, profundidad/stencil/
  cull/tijera, mips, viewport). Esperadas: logic op no emulables en RT UNORM (CLEAR/NOOP/SET/COPY exactos). A arreglar
  (agentes C5b/C1b/D3b, ver abajo): muestreo PUNTO escalado en empates (copiar a ventana, pres_capa) y blend mixto
  CONST_COLOR+CONST_ALPHA (3/150).
- Arreglos de la sesión principal: 🩹 `subir_color`/`bajar_color` (raster_gl.c) leían/escribían FUERA del buffer con w/h
  no múltiplo de 8 (offset morton de la última fila de tiles) → buffer con tamaño redondeado a tiles (`rt_bytes_tiles`,
  calloc); afecta también al GL. `d3d_cerrar` cierra el HANDLE de latencia. Pendiente cosmético: exportar
  `d3d_swap_chain_crear/soltar` de d3d12_base.c y borrar la copia local de C1.
- 🪛 `zig cc -fsyntax-only` da un "FileNotFound" FALSO: chequear con `-c -o <propio>.o`. `rb` es macro en raster_gl.c.
  La capa de depuración D3D12 NO está instalada (falta "Herramientas de gráficos" de Windows; `SM3DL_D3D_DEBUG=1` da
  0x887A0001). 1ª corrida en D3D12: ~16 s extra compilando PSO (después ~2 s; caché `extraido\shaders\pso_d3d12.bin`).
- Riesgos que solo el juego destapa (D5): reuso de tablas de descriptores con el anillo dando la vuelta; constantes de D2
  si un anillo se llena a mitad de las reservas de un dibujo.

## PRÓXIMA SESIÓN — por dónde empezar (cierre 9 oct: D3D12 completo, falta el juego)
1. **Primera corrida del juego en D3D12** (con OK del dueño: calienta): `set SM3DL_BACKEND=d3d12` + exe integrado, guion
   corto hasta el 1-1; comandos de cada parte en las bitácoras ("Prueba pendiente con el juego") y comparación
   automática con `agentes_dx12\E2\prueba_pendiente_juego.ps1`.
2. Repetir `py -I agentes_dx12\E2\tools\e2.py` tras cualquier cambio del backend.
3. Pendientes de antes: fantasma del modo Monitor (F9), audio "raro", Nahimic.

## 10 oct madrugada — D3D12 jugado por el dueño + texturas + rendimiento (bitácoras en agentes_dx12\ y agentes_tex\)
- El dueño jugó con `JUGAR_D3D12.bat`: 60 FPS "impecable"; tras esta tanda, "se ve y funciona mucho mejor".
- Arreglado: Monitor congelado (G1: no esperar el objeto de latencia), shaders faltantes (F1/S1: caché 2.117 DXIL,
  conversión automática al cerrar por S2), caché de PSO guardada a los 2 s (F1), vértices enteros en GPU (D4b),
  audio con retraso de 200 ms y crujidos (AU, `recomp\audio\audio_salida.c`; `SM3DL_AUDIO_VIEJO=1` = antes; FALTA que
  el dueño lo confirme oyendo).
- Rendimiento (medido 144 Hz 4x): cinta de H1 (`SM3DL_D3D12_REPETIR_RAPIDO=1`, encendida SOLO en JUGAR_D3D12.bat) +
  P1 hash de texturas −71 % + P2 clave de shader −66 % + P3 vértices −16 % → intermedio 3,0→1,8 ms, peor cuadro 31→18 ms.
  E2 sigue 24/29. Hallazgo H1: la re-ejecución vieja empareja con registros rancios (posible "fantasma").
- Sombras a 144 (H2): `SM3DL_INTERP_SOMBRA_CAMARA` 0 (default) / 1 / 2 — elegir con `agentes_dx12\H2\PROBAR_H2.bat 1|2`.
- Texturas (T1..T7): anisotrópico + reemplazo HD por clave (`texturas_hd\tex_<w>x<h>_f<fmt>_<CLAVE>.png`) + menú.
  Muestra Real-ESRGAN en `agentes_tex\T5\muestra\`; reglas `texturas_hd_reglas.tsv`; fuentes `texturas_hd_fuente\`.

## PRÓXIMA SESIÓN — por dónde empezar (cierre 10 oct)
1. Texturas HD: dueño elige estilo (recomendado A = realesrgan-x4plus), correr lote (~990 texturas, ~80 min GPU,
   cuando no use la laptop), confirmar claves con `SM3DL_TEX_VOLCAR` en una corrida corta.
2. Sombras: que el dueño pruebe H2 modo 1 y 2 a 144 Hz y fijar el default.
3. Audio: que el dueño pruebe `agentes_audio\sm3dl_AU.exe` (o el exe integrado) y diga si se fue el retraso/crujido.
4. Velocidad: LUTs de luz (P2: el costo está en subir_luz/b3/tex_enlazar, no en comparar), índices u16 (P3), espera de
   CPU en `completar_dif` (H3), timestamps de GPU por cuadro.
5. Agentes que corren el juego: turno estricto (tasklist vacío + CORRIENDO/LIBRE en bitácoras) y NUNCA tocar el ini.
Respaldo: `respaldos\sm3dl-port-codigo-texturas-perf-10oct.zip`.
0. **PRIORIDAD 1 (dato del dueño, 10 oct):** a 144 Hz "la GPU iba casi al 50 % y aun así había bajones" → el cuello es
   el HILO ÚNICO (juego + raster + intermedios + presentar), no la GPU. Hacer el **paso 7 de D3D12: presentación e
   intermedios en un hilo aparte**, al ritmo del monitor (prototipo `recomp\render\prueba_d3d12_hilo.c`: 2,9 % de error
   de paso vs 11-13 % de hoy; línea de tiempo = nº de cuadro × 33,367 ms + desfase, ver agentes_dx12\principal.md).
   Medir antes con uso de CPU por núcleo y timestamps de GPU por cuadro para confirmarlo.

## 10 oct ~01:45 — tanda final de la noche (M1, K1, V1, R1)
- M1 (medición): la GPU NO es el cuello (34 % con el hilo del juego al 100 % en turbo); a ritmo real el hilo del juego
  va al 31 % medio con picos: los bajones a 144 son PICOS que no caben en el cuadro.
- K1 (paso 7, FASE 1): presentación en HILO APARTE (`raster_d3d12_hilo.inc`, `SM3DL_PRES_HILO=1`, apagado por defecto;
  lanzador de prueba `JUGAR_D3D12_HILO.bat`). Medido oculto a 144 Hz: hilo presenta a 143,6-144 Hz, peor racha 1;
  error del paso con hilo + cinta 11,6 % (sin hilo 23-51 %, varía mucho). FASE 2 pendiente: re-emitir la cinta desde
  el hilo (bloqueos en agentes_dx12\K1.md: RT del juego, fills/transfers, candados en d3d_tex_estado y anillos) y cola
  propia de prioridad alta. FALTA la prueba del dueño a pantalla completa visible.
- V1: claves HD confirmadas en el juego (196/243 = 81 % coinciden, idénticas píxel a píxel; las 47 restantes = fuente
  BCFNT en LocalizedData, efectos en EffectData y texturas generadas → PEDIDO T3/T6). Reemplazo visto en pantalla.
- R1: "luts" 1,85 → 0,35 µs por dibujo (−81 %): el atajo de P2 excluía el sello 0. Verificación en juego 0 errores;
  sabotaje NO visto fallar (E2 no cubre el caso) → pendiente un escenario de E2 con varios dibujos que re-escriban tablas.
Respaldo: `respaldos\sm3dl-port-codigo-hilo-10oct.zip`.
