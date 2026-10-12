# Núcleo del motor de actores — reporte del agente "motor" (6 oct 2026)

Entregables: `extraido/propuestas_motor.txt` (132 nombres: 69 CONFIRMADOS, 63 HIPÓTESIS, ninguno choca con `simbolos.txt`) y `extraido/estados_actores.tsv` (241 llamadas a `addNerveState`). No se tocó `simbolos.txt` ni el proyecto Ghidra principal.

Todo el análisis se hizo sobre `code.bin` y la copia `ghidra/agentes/motor`. Se usaron unas 27 consultas a Ghidra; los barridos masivos se hicieron con un mini-decodificador ARM en Python.

## 1. La vtable de LiveActor (23 posiciones)

La vtable base de `LiveActor` está en `0x003D797C`: `LiveActor__ctor` la escribe con `DAT_0027ff2c`. La de `GameActor`, en `0x003C76FC`, tiene las mismas 23 entradas. Las posiciones vacías (null) **nunca** se sobrescriben en ninguna de las 220 clases. Lo más probable es que sea la *Virtual Function Elimination* de armlink: el enlazador pone a 0 las virtuales que nunca se llaman.

| pos | off | base | sobrescr. | nombre | evidencia |
|---|---|---|---|---|---|
| 0 | 0x00 | 0x3375EC | 0 | getNerveKeeper | ya conocido; devuelve +0x2C |
| 1 | 0x04 | 0x1EBF20 (bx lr) | 219 | **init** | CONFIRMADO: Kuribo_init está aquí y llama initActorWithArchiveName |
| 2 | 0x08 | 0x1EBE5C (bx lr) | 24 | initAfterPlacement | HIPÓTESIS: viene por el orden Petari/SMO; está vacía |
| 3 | 0x0C | 0x27FF68 | 24 | **appear** | CONFIRMADO: solo llama a vt+0x10 |
| 4 | 0x10 | 0x27EA38 | 16 | **makeActorAlive** | CONFIRMADO: muerto(+0x54)=0, sensores, listas de ejecución y subactores vt+0x10 |
| 5 | 0x14 | 0x27EBE8 | 30 | **kill** | CONFIRMADO: solo llama a vt+0x18 |
| 6 | 0x18 | 0x27D248 | 9 | **makeActorDead** | CONFIRMADO: muerto=1, invalida todo y subactores vt+0x18 |
| 7 | 0x1C | 0x26DF3C | 2 | **movement** | CONFIRMADO: NerveKeeper_update, luego control (vt+0x4C), luego updateCollider (vt+0x54); la llama ExecutorActorMovement |
| 8 | 0x20 | 0x25AA2C | 5 | **calcAnim** | CONFIRMADO: la llama ExecutorActorCalcAnim |
| 9 | 0x24 | null | – | (draw?) | HIPÓTESIS: eliminada; en Petari aquí va draw |
| 10 | 0x28 | 0x2795B8 | 15 | **startClipped** | CONFIRMADO: +0x55=1 y subactores vt+0x28 |
| 11 | 0x2C | 0x2797EC | 13 | **endClipped** | CONFIRMADO: +0x55=0 y subactores vt+0x2C |
| 12 | 0x30 | 0x1EBC58 (bx lr) | 78 | **attackSensor** | CONFIRMADO (Kuribo) |
| 13 | 0x34 | 0x1EBC50 (ret 0) | 147 | **receiveMsg** | CONFIRMADO: los sendMsg llaman host->vt+0x34(msg, sender, receiver) |
| 14 | 0x38 | 0x3375D4 | 4 | getBaseMtx | HIPÓTESIS: devuelve la matriz del ModelKeeper (+0x28) |
| 15 | 0x3C | 0x3375FC | 0 | **getEffectKeeper** | CONFIRMADO: +0x34, que es lo que escribe initEffectKeeper ("Effect") |
| 16 | 0x40 | 0x3375F4 | 0 | getAudioKeeper | HIPÓTESIS: +0x38; se arranca en alive/endClipped y se para en dead/startClipped |
| 17-18 | 0x44-0x48 | null | – | ¿getStageSwitchKeeper…? | eliminadas |
| 19 | 0x4C | 0x1EBF24 (bx lr) | 83 | **control** | CONFIRMADO: movement la llama después del nerve |
| 20 | 0x50 | null | – | ? | eliminada |
| 21 | 0x54 | 0x1EBCE4 | 0 | updateCollider | HIPÓTESIS fuerte: trans += velocidad, directo o vía el colisionador +0x20 |
| 22 | 0x58 | null | – | ? | eliminada |

**Bases secundarias** (herencia múltiple, con offset-to-top -4/-8/-0xC):
- `this+4`: IUseEffectKeeper, que devuelve actor+0x34.
- `this+8`: IUseAudioKeeper, que devuelve actor+0x38.
- `this+0xC`: IUseStageSwitch, con `[0]` get → +0x3C y `[1]` initStageSwitchKeeper.

### Mapa de campos de LiveActor (deducido)
| Offset | Campo |
|---|---|
| +0x00 | vtable |
| +0x04/+0x08/+0x0C | vtables secundarias |
| +0x10 | nombre |
| +0x14 | PoseKeeper (trans = pose+4) |
| +0x18 | ActorExecuteInfo |
| +0x1C | ¿ActionKeeper? |
| +0x20 | Collider |
| +0x24 | ? (calcula la matriz de la pose) |
| +0x28 | ModelKeeper |
| +0x2C | NerveKeeper |
| +0x30 | HitSensorKeeper |
| +0x34 | EffectKeeper |
| +0x38 | ¿AudioKeeper? |
| +0x3C | StageSwitchKeeper |
| +0x44 | ShadowKeeper |
| +0x48 | ¿LightCtrl? |
| +0x50 | SubActorKeeper (lista con flags bit0 = vive/muere junto, bit1 = clipping junto) |

**Flags del actor:**
| Offset | Flag |
|---|---|
| +0x54 | muerto |
| +0x55 | clippeado |
| +0x56 | clipping invalidado |
| +0x57 | ¿clipping solo de dibujo? (movement sigue corriendo) |
| +0x59 | ? |
| +0x5A | ? |
| +0x5B | ? |

## 2. El framework que usa Kuribo

- **Kuribo_init** sigue esta secuencia:
  - `initActorWithArchiveName("Kuribo")`, que lee `ObjectData/Kuribo` → `InitActor.byml`.
  - `initNerve(this, 0x3F21C8, 7)`.
  - Crea 7 estados con `operator_new` + su ctor (Attack 0x1861D8, Wander 0x26B9D0, Chase 0x259360, Fall 0x1675D4, FindPlayer 0x1A1608, PopOut 0x18B5C4, BlowDown 0x27B544) y los registra con `addNerveState`.
  - `initStageSwitchAppear`, y luego `trySyncStageSwitchAppear` (si aparece por switch, `setNerve(Fall)`).
  - `setColliderFilterSpecialPurpose("移動制限")`.
  - Si hay link "CoinCollect" hace un camino propio; si no, lee un bool del placement.
- **Tipos de sensor (CONFIRMADO, tabla 0x3F02B8):**

  | Tipo | Nombre | Tipo | Nombre |
  |---|---|---|---|
  | 0 | Eye | 9 | EnemySimple |
  | 1 | Player | 10 | MapObj |
  | 2 | Npc | 11 | MapObjSimple |
  | 3 | Ride | 12 | Bindable |
  | 4 | Enemy | 13 | CollisionParts |
  | 5 | EnemyBody | 14 | KickKoura |
  | 6 | EnemyAttack | 15 | PlayerFireBall |
  | 7 | KillerMagnum | 16 | WooGanSandBody |
  | 8 | Dossun | | |

  Predicados: isSensorPlayer (1|15), isSensorEnemyAttack (6), isSensorEnemy (4..8), isSensorMapObj (10).
- **Kuribo_attackSensor(self, other)** decide así:
  - Si `other` es jugador y `self` es EnemyAttack, y Kuribo no está en el nerve 0x3F21E4 (¿pisado?) ni en BlowDown: `sendMsgPush` (msg 0x29), y si `sendMsgEnemyAttack` (msg 0x2D) se acepta, pasa a `[state]攻撃`.
  - Si `other` es enemigo y Kuribo no está en `[state]飛び出し`: `sendMsgPushAndKillVelocityToTarget`.
  - Si `other` es MapObj: `sendMsgPush`.
- **Kuribo_receiveMsg(msg, sender, receiver)** actúa solo si el receptor es un sensor de enemigo, y prueba en orden:
  - `tryReceiveMsgPressDownAndSetNerve(…, 0x3F21E4)` → luego `invalidateClipping`.
  - `EnemyStateBlowDown_tryReceiveMsg`.
  - `receiveMsgPushAndAddVelocity` (se salta si Kuribo está en `[state]飛び出し` con `step <= 5`).
- **Los mensajes son enteros:** `sendMsg` llama `host(sensor+0x28)->receiveMsg(id, sender, receiver)`. 0x29 = push y 0x2D = ataque de enemigo. Los predicados `isMsgX` (0x27DB44, 0x27B178, 0x27DB90…) **no se nombraron**: hace falta mapear sus ids.
- **NerveKeeper** (0x18 bytes):

  | Offset | Campo |
  |---|---|
  | +4 | nerve actual |
  | +8 | nerve siguiente |
  | +0xC | step |
  | +0x10 | control de estados (lista de 12 bytes {state, nerve, nombre}, que llena addNerveState) |

  `NerveKeeper_update` cambia de nerve, llama `nerve->execute(keeper)` y hace `step++`.

## 3. El bucle por frame (CONFIRMADO en su mayor parte)

Usa el mismo esquema que el `al::ExecuteDirector` de SMO:

1. **`LiveActorKit_init` (0x1C0B40)** crea el ExecuteDirector y llama a **`ExecuteDirector_init` (0x1CCA8C)**, que hace dos cosas:
   - Crea la tabla de **update** a partir de `ExecuteOrderTable` (0x3A8FA4, 58 entradas de 16 bytes con la forma {grupo, lista, tipo, max}). Por ejemplo: `{"敵","敵[Movement]","ActorMovement",32}`, `{"地形","コリジョン地形[キャラ後]","ActorMovementCalcAnim",32}`, `{"プレイヤー","ゴーストプレイヤー記録","Functor",1}`.
   - Crea 10 tablas de **dibujo**: ３Ｄ（空）, ２Ｄエンドロールテキスト, ３Ｄ（固定地形）, ３Ｄ（上画面）, ２Ｄアイコン, ２Ｄベース(上/下), ２Ｄ(上/下), ３Ｄ（アイテムストック）.
2. **`ExecuteTableHolderUpdate_init` (0x1E37D0)** crea un ejecutor por cada entrada según su tipo: `ActorMovement`, `ActorCalcAnim`, `ActorMovementCalcAnim`, `LayoutUpdate`, `Execute` o `Functor`.
3. **Registro.** `initActor` lee `Executor/CategoryName` del InitActor.byml (por defecto "敵") y crea el `ActorExecuteInfo` (+0x18). Después busca la lista cuyo nombre coincide y llama `ExecutorListActor_registerActor`, que agrupa los actores **por nombre de actor** en sublistas (una sublista por clase).
4. **Ejecución por frame:**
   - Arriba de todo está la nerve de la escena (`StageScene_exePlay`?, 0x17C7F8).
   - Esa nerve llama **`SceneActorKit_updateAll` (0x258108)**, que a su vez hace pre (0x1DD9E0/0x1DD8F0), **`ExecuteTableHolderUpdate_executeAll` (0x336154)** y post (0x1DDA50).
   - `executeAll` recorre cada `ExecutorList` llamando vt+8 = **`ExecutorListActor_executeList` (0x336684)**.
   - `executeList` recorre cada sublista llamando vt0, que es uno de estos:
     - **0x335454**: `for actor: actor->movement()`.
     - **0x335414**: `actor->calcAnim()`.
     - **0x3368C0**: `actor->movement(); actor->calcAnim()`.
   - `movement()` hace: NerveKeeper_update → `nerve->execute` (los estados), luego `control()`, luego `updateCollider()`.
5. **Altas y bajas.** `makeActorAlive`/`endClipped` meten al actor en la lista activa de su sublista (0x24B930/0x250F74) y `makeActorDead`/`startClipped` lo sacan. Así el bucle **solo recorre actores vivos y no clippeados**.
6. **Actualizaciones parciales.** `executeUpdateList(kit, "nombre")` (0x33290C) ejecuta una sola lista por nombre. Se usa para demos y pausa: 0x277258 ejecuta クリッピング, 空, デモ…, プレイヤー…, フォグディレクター, エフェクト…; 0x1227B4 y 0x126010 son variantes.
7. **Dibujo.** No hay una virtual draw en el actor (pos 9 = null). El dibujo va por `ExecuteTableHolderDraw` con ejecutores "ActorModelDraw", que dibujan el modelo, no el actor.

Para el port, esto significa que se puede reimplementar el bucle en C con la `ExecuteOrderTable` como dato: por cada entrada, por cada sublista y por cada actor vivo, `movement()` y/o `calcAnim()`.

## 4. Estados (addNerveState)

`extraido/estados_actores.tsv`: **241 llamadas** con nerve, nombre japonés y traducción al español.
- **Detección:** se tomaron todos los BL a 0x1CACAC y se rastrearon r2/r3 de forma lineal desde el inicio de la función.
- **Verificación:** las 7 de Kuribo coinciden exactamente con la decompilación de Ghidra. Los 3 casos que el rastreo no resolvió se arreglaron a mano con Ghidra (GameOver, Punpun y BeatBlock con nombre dinámico).
- **Clase:** sale de la pos1 de `vtables_actores.tsv` o de `simbolos.txt`. Las que no estaban se etiquetaron así:
  - `ActorSinNombre_init_vtXXXX(cerca_de_Y)`: actores cuyo init está en una vtable de actor que no figura en la tabla.
  - `FUN_xxx(cerca_de_Y)`: estados creados fuera de un init.
- **Hallazgos:**
  - `GameSequence_init` usa el mismo mecanismo para la secuencia del juego: Title, Opening, CourseSelect, Stage, KinopioHouse, MysteryBox, Ending, GameOverRoom.
  - Los estados genéricos de enemigo más repetidos son `state:BlowDown` (23) y `state:HipDropDown` (12).

## 5. Dudas abiertas
- **Posiciones 2, 14, 16 y 21:** tienen nombre por analogía con SMO más un comportamiento coherente, pero no hay una cadena que lo pruebe. Las 17, 18, 20 y 22 son irrecuperables: el enlazador las eliminó.
- **Ids de mensaje:** solo 0x29 (push) y 0x2D (ataque de enemigo) tienen uso claro. Falta barrer los predicados `isMsgX` (funciones cortas `cmp msg,#id`) para armar la tabla id→nombre. El candidato más probable a `isMsgPlayerTrample` es 0x27DB44.
- **Nerves de Kuribo sin estado:**
  - 0x3F21C8 es el nerve inicial (¿Wait?).
  - 0x3F21E4 es el que pone `tryReceiveMsgPressDown` (¿pisado?).

  Los nerves de 3DL son objetos en .bss; para nombrarlos hay que leer su vtable `execute`.
- **ActorExecuteInfo:** el detalle de la estructura (activo/inactivo y offsets +4/+8 frente a +0xC/+0x10 de la sublista) no está del todo cuadrado.
- **0x258108:** Ghidra le asignó un bloque no contiguo (0x1DD96C). Conviene re-crear esa función en el proyecto principal.
- **Inicio de función por heurística:** el TSV lo calcula buscando `push {...,lr}` hacia atrás. Hay ~10 funciones (0x180144, 0x164284…) que agrupan muchos estados y no tienen referencias. Puede que sean constructores de estados compuestos o que la heurística haya caído en mitad de una función.
- **Fuera de alcance:** no se investigó la clase del jugador (los `PlayerState*` aparecen solo como "cerca_de") ni los servicios del sistema.
