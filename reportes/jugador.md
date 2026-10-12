# Clase del jugador (Mario/Luigi) — reporte

Agente "jugador", 6 oct 2026. Propuestas de nombres en `extraido/propuestas_jugador.txt`: 55 en total, 22 CONFIRMADAS y 33 HIPÓTESIS.

## 1. La clase `PlayerActor`
- **Constructor `0x002768A4`**: llama a `GameActor__ctor` con el nombre `"プレイヤー"` ("Jugador"). **Hereda de GameActor** (y por tanto de LiveActor).
- **Tamaño 0x15C**: en los 4 sitios que lo crean va `operator_new(0x15C)` seguido del ctor.
- **Vtable principal `0x003C6828`**, de 38 entradas (hasta 0x3C68BC). El ctor también instala vtables secundarias en los campos +4, +8, +0xC, +0x60, +0x64, +0x68, +0x6C y +0x70 (vtable + 0x98/0xA4/0xB8/0xC8/0xE0/0xF4/0x100/0x110).
- **Overrides frente a GameActor (0x3C76FC)**:
  | pos | dir | qué es |
  |---|---|---|
  | 1 | 0x001EBF20 | init **heredado sin cambios** (el jugador no usa init(ActorInitInfo&) normal) |
  | 7 | 0x00132A58 | movimiento por frame (llama al final a la base 0x0026DF3C) |
  | 12 | 0x00130430 | attackSensor |
  | 13 | 0x001302C4 | receiveMsg |
  | 19 / 21 / 27 | 0x001326FC / 0x001314AC / 0x0013029C | Ghidra no tiene función definida ahí (pendiente) |
  | 24 | **0x00131AB4** | **initPlayer(ActorInitInfo&, PlayerResourceTable&)**: es el init real |
- **Quién lo crea**, siempre con el mismo patrón: `new 0x15C → ctor → vt[+0x60](info, PlayerResourceTable_make()) → 0x00276868`:
  - `0x001233E0`: StageScene. Lee "StartInfo"/"MarioNo" de la colocación y guarda el jugador en escena+0x38.
  - `0x00125954`: TitleScene.
  - `0x0017EE18`: KinopioHouseScene. El inicio de la función se dedujo por escaneo; falta verificarlo.
  - `0x0031AFC8`: escena de demo.
- El jugador **no está en las fábricas `create_*`**: lo instancia directamente cada escena.

### Mapa de campos (índices de initPlayer y del ctor)
| off | contenido |
|---|---|
| +0x74 | **PlayerCore** (0xF8, ctor 0x00309334): núcleo con ~40 subobjetos y el grafo de acciones |
| +0x78 | PlayerInput (0x6C, ctor 0x00133D34, vtable 0x3C6978); su campo +0x58 apunta al jugador |
| +0x7C | obj 0x2C (0x0014F54C) |
| +0x80 | obj 0x14 (0x001330BC, vtable 0x3C6944) |
| +0x84 | 2.º parámetro del ctor (escena+0x20 → +8) |
| +0x88 / +0xA0 | objs del ctor (0x001B4700 / 0x001B4DE0) |
| +0x90 | 3.er HitSensor creado en initPlayer |
| +0x94 | obj 0x40 (0x0013E068) |
| +0x98 | obj 0x20 (0x00196CF0); movement consulta su vt[+0x14] |
| +0xA4 | **PlayerModelHolder** (0x50, 0x00182C10) |
| +0xA8 / +0xAC / +0xB0 / +0xB4 | 0x0019FBE0 / 0x0018A538 / 0x0018201C / 0x0013DE48 |
| +0xB8..+0xD8 | posiciones de los sensores (3×vec3) |
| +0xDC..+0x10C | más componentes (0x001A9500, 0x001A49D0, 0x001A7FF4, 0x0019FC18, 0x0015510C, 0x001A7138, 0x001B856C, 0x00198A7C, 0x001B4CC4) |
| +0x114 | obj 0x28 (0x001BB390); initPlayer le copia +0x7C/+0xB4/+0x80/+0xA4 |
| +0x118 / +0x11C | PlayerAnimSet "MarioAnimation" (normal / "%sRaccoonDog") |
| +0x120 | obj 0x001755BC |
| +0x124 | sensor del atacante más cercano (attackSensor) |
| +0x138 | bool: modo especial en movement (rama distinta, sin la base) |

Sensores (0x0026E5CC): "Foot", 2 más con nombre en literal (DAT_00131E98/EA4, sin leer), "TailAttack" y otro con 0x001CD4C4.

## 2. Máquina de estados: no son Nerves, es un grafo de acciones
- El jugador **no usa `setNerve`** para moverse. `PlayerCore__ctor` llama a **`0x001A956C`**, una función gigante (~24 KB, pila 0x8B0, Ghidra no la decompila en 60 s) que crea unos **60 objetos de estado**. A cada uno lo envuelve en un nodo de 0x14 bytes (`0x00252134`) y le agrega unas **170 transiciones** (`0x00252000`), que son objetos chicos de 8 a 0x14 bytes con vtables en 0x3D1xxx (condiciones).
- Sale del mismo patrón que el `PlayerActionGraph` de 3D World. **No hay textos japoneses `[state]`** para el jugador.
- Los nombres de estado son **HIPÓTESIS**, deducidos de las animaciones que referencian las funciones de cada vtable:

| ctor | tam | vtable | animaciones / textos | estado propuesto |
|---|---|---|---|---|
| 0x00173B54 | 0x70 | 0x3CC37C | Jump, Jump2, Jump3, LandTurn, Land | Salto (triple) |
| 0x00171D5C | 0x58 | 0x3CC344 | (mismas que Jump) | ¿Aterrizaje/caída? |
| 0x00174C10 | 0xC | 0x3CC450 | Wait, DashSign | Quieto/correr |
| 0x00197EE8 / 0x00197C5C / 0x00197B88 | — | 0x3CF2A8… | Fall, WallJump | Salto de pared |
| 0x0019E5CC | 0x34 | 0x3CFC64 | SquatWait, SquatWalk | Agachado |
| 0x0019DC40 | 0x64 | 0x3CFBE8 | JumpBack(High), SePvJumpSquat | Salto hacia atrás |
| 0x0018EB9C | 0x30 | 0x3CE8D0 | HipDropStart, HipDropLand | Sentón (hip drop) |
| 0x0018A388 | 0x20 | 0x3CE268 | DamageSmall | Daño |
| 0x00181284 | 0xC | 0x3CD8C8 | WallKeep, WallSlideR/L | Deslizarse por la pared |
| 0x0025211C (x3) | 0x10 | 0x3CD954 | SquatSlide, TailAttackSquat* | Barrida agachado |
| 0x0019EFAC / 0x00174838 / 0x001BA528 | — | — | SwimStandWait, SwimPaddle, SwimStandSurface | Nadar |
| 0x001A79B4 / 0x001A73AC | 0x38 / 8 | 0x3D0894 | WaitStatue, Transform | Estatua tanuki |
| 0x001BAE80 | 0x70 | 0x3D15AC | スカイアタック[着地] ("ataque aéreo, aterrizaje") | ¿Ataque en el aire? |
| 0x001B8B30 / 0x001B9040 | 0x5C / 0x60 | 0x3D10A4 | LuigiMove | Movimiento propio de Luigi |
| 0x001B71F8 | 0x28 | 0x3D0E90 | SwimDieOver | ¿Muerte? |

La lista completa (dir → ctor → tamaño → vtable) se puede regenerar escaneando los BL de 0x001A956C..0x001AF700.

## 3. Modelo según el power-up, y el hilo de carga
- **Tablas de archivos** en .rodata (CONFIRMADO). Cada personaje ocupa 0x70 bytes:
  - Mario en `0x003B94C4`, Luigi en `0x003B9534`.
  - Orden: Normal(+Silhouette, +SilhouetteCounterStop), Mini(×3), Fire(×2), RaccoonDog(+Silh, +Tail), Boomerang(×2), RaccoonDogSpecial(×3), RaccoonDogWhite(×3), MarioHandL/R, MarioMiniHandL/R y RaccoonDogStatue.
  - `0x002605F8` elige la tabla según `isPlayerLuigi` (0x00277CE4).
- **Tablas de animación** (stride 0x1C): Normal 0x3B95A4, Demo 0x3B95C0, CourseSelect 0x3B95DC, DemoKoopa 0x3B95F8 y DemoKoopaLast 0x3B9614. Cada una lleva {anim, animMini, animTail, nombre, nombre, grupo "Player:Normal"/"Player:Mini"…}. La demo elige la suya con el parámetro "ModelName" (0x0015A9D0).
- **`PlayerModelHolder` (0x00182C10)** crea **los 7 modelos a la vez** en el init, y el cambio de power-up solo alterna entre ellos. Slots: +0x10 Super, +0x14 Mini, +0x18 Fire, +0x1C Tanuki, +0x20 Boomerang, +0x24 Tanuki especial y +0x28 "お助け" (ayuda = tanuki blanco). Los nombres salen de los textos japoneses de cada creador (スーパーモデル, ちびモデル, ファイアモデル…).
- **Forma actual**: está en el objeto `core+0x40` (ctor 0x00198138), cuyo campo [0] es la forma. En el código se comparan los valores 1 y 6, pero falta el enum.
- **Hilo de carga** "プレイヤー読み込みスレッド": se crea en `0x00163318` (init de la secuencia: Title/Opening/CourseSelect/Stage/KinopioHouse/MysteryBox/Ending/GameOverRoom) con el callback `0x001A4D68`. Ese callback invierte el flag Mario↔Luigi y recarga los recursos con el nombre "マリオ"/"ルイージ".
- `0x0025AF54` devuelve "Mario"/"MarioGolden"/"Luigi"/"LuigiGolden". El dorado sale cuando un contador vale 100 (probablemente el ícono de la partida).

## 4. Entrada (control)
- `PlayerInput_update` **0x00133484** (método del objeto en jugador+0x78):
  - Lee botones del **puerto 0** con 0x0026DB90/0x0026DBBC/0x0026DBE8/0x0026DC14/0x002730C4/0x002CE9D0/0x002CEC68/0x002CEC94/0x002CF150/0x002CF418/0x002CF5F4/0x002CF620. Guarda cada uno en bytes +0x30..+0x45 y lleva contadores de pulsación en +0x34/+0x48.
  - Lee el **stick** con `0x0026DB44(0)`.
  - Lo convierte a un vector 3D relativo a la cámara (+0x10..+0x18), con un flag "moviéndose" en +0xC.
  - Aplica `0x00133A2C` (zonas "StickSnapOffArea" y "PlayerWidenStickXSnapArea").
- **Falta**: identificar qué botón es cada función 0x0026DBxx/0x002CExxx. Ese es el siguiente paso para mapear el control de PC.

## Dudas abiertas
- Las **vtables tienen muchos 0** (también la de GameActor). Puede ser un pure virtual que el compilador deja en 0, o algo de la extracción. Hay que confirmarlo antes de numerar más métodos.
- Pos 19, 21 y 27 de la vtable del jugador (0x001326FC, 0x001314AC, 0x0013029C): Ghidra no creó función ahí. Conviene crearlas en el proyecto principal.
- Los nombres de estado salen de los textos de las funciones cercanas. El escaneo de "fin de función" es aproximado, así que algunos textos pueden estar mal atribuidos.
- Falta el enum de forma: 1 parece Mini, por la rama aparte en PlayerCore_update, y 6 aparece en attackSensor.
- La función gigante 0x001A956C necesita más tiempo de decompilación (subir el timeout de 60 s en `consultar.py`) para leer las aristas del grafo (estado → condición → estado).
