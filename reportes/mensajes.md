# Mensajes entre actores (7 oct 2026)

Tabla cruda: `extraido\mensajes.tsv`. Cómo se sacó: ver "Método" al final.

## Cómo funciona (CONFIRMADO)
- Un mensaje es un **número**. Cada número tiene **un envoltorio de envío propio** (48 encontrados) con la misma forma:
  `mov r3,r0 ; ldr r0,[sensor,#0x28] ; mov r2,r1 ; mov r1,#N ; ... ; bx [vtable+0x34]`
  → `actor->receiveMsg(N, sensorA, sensorB)` (receiveMsg = entrada 13 de la vtable). No hay un `sendMsg` común.
- Del lado receptor hay funciones `isMsgN(msg)` = `return msg == N` (unas 45, entre 0x277C80 y 0x27F328).
- Los actores agrupan mensajes por efecto. En el Goomba: `tryReceiveMsgPressDownAndSetNerve` (aplastar) y `EnemyStateBlowDown_tryReceiveMsg` (salir volando).

## Tabla
| N | Hex | Nombre | Quién lo envía | Evidencia |
|---|---|---|---|---|
| 1 | 0x01 | **Pisotón** | Mario, sensor "Foot" | Mario encima (ángulo < 70°) y sin anim de sentón; luego `ctx8 |= 1<<1` → estado RebotePisotón — CONFIRMADO |
| 3 | 0x03 | **Cabezazo** | Mario, sensor "Head" | si se acepta: `ctx8 |= 1<<2` y anula la velocidad hacia arriba — CONFIRMADO |
| 6, 7 | | variante de pisotón | Mario | rama `FUN_00326b68(jugador)` (¿por forma?) — HIPÓTESIS |
| 9, 10 | | ¿sentón sobre enemigo? | Mario | pisotón con `ctx98.vf2c` y cayendo rápido — HIPÓTESIS |
| 11 | 0x0B | pisotón cayendo | Mario, sensor "Foot" | enemigo + `ctx98.vf2c` + velocidad vertical — HIPÓTESIS |
| 12 | 0x0C | ? | Mario (cuerpo) | con `ctx98.vf2c` |
| 15 | 0x0F | ? | Mario | con `jugador+0x140 vf0` y el otro delante |
| 16 | 0x10 | **¿contacto invencible?** | Mario | forma == 6 o `core+0x54`; está en la lista de "salir volando" — HIPÓTESIS |
| 17 | 0x11 | ? (el más consultado: 92 `isMsg`) | objeto `0x31F668` (GameActor, lo crea `FUN_0025a838`) | también manda AtaqueEnemigo al jugador → daña a todos; en "salir volando" |
| 18 | 0x12 | **Coletazo** | Mario, sensor "TailAttack" | CONFIRMADO; en "salir volando" |
| 19 | 0x13 | **Patada** | Mario | si se acepta arranca anim "Kick" — CONFIRMADO |
| 20, 22, 23, 35 | | ataque de un sub-actor de Mario | objeto `0x161B6C`, creado por `PlayerActor_initPlayer` (`jugador+0xE4`), sensor "Attack", sonido `SeSyBeatEnemySequentially` | ¿boomerang? — HIPÓTESIS |
| 26 | 0x1A | ? | Mario, con MapObj y `jugador+0x13A` | |
| 33, 35, 36, 37 | | golpe de caparazón | **KickKoura** (caparazón pateado) | 33 está en "salir volando" |
| 38, 42, 53 | | golpe de bala Bill | **Killer / KillerMagnum** | 42 y 53 los usan muchos actores (14 y ~12 sitios) |
| 41 | 0x29 | **Empujar** | 39 sitios (enemigos y objetos) | `sendMsgPush` — confirmado por un agente anterior |
| 45 | 0x2D | **AtaqueEnemigo** | 33 sitios | `sendMsgEnemyAttack`; el enemigo daña a Mario |
| 46–49 | | golpe de roca | **Gorori** (roca rodante) | 46 y 47 en "salir volando" |
| 50 | 0x32 | ? | Bubble (Podoboo) y 9 más | en "salir volando" |
| 62 | 0x3E | ? | `PlayerActor_movement` | |

**"Salir volando" (EnemyStateBlowDown) acepta:** 16, 17, 18, 20, 33, 40, 46, 47, 50.

## Para el port
La lógica del juego no necesita conocer los nombres: los números viajan de actor a actor tal cual. Los nombres sirven para **depurar** y para verificar que un comportamiento ("el caparazón no mata al Goomba") falla donde creemos.

## Método
1. `isMsgN`: funciones de 4 instrucciones `cmp r0,#N / moveq / movne / bx lr`.
2. Envíos: patrón exacto `ldr ip,[ip,#0x34]; bx ip` con `mov r1,#N` delante → 48 envoltorios, uno por número.
3. Nombres: dónde se llama cada envoltorio (xrefs) + qué clase es dueña de esa función (vtable en `extraido\vtables_actores.tsv`, o el ctor que escribe la vtable) + qué hace el emisor justo después (bits de `ctx8`, anims).
