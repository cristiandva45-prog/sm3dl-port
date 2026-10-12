# Grafo de estados de Mario — cómo se sacó y qué se sabe (7 oct 2026)

Detalle estado por estado: **`reportes\grafo_mario.md`** (generado). Graphviz: `extraido\grafo_mario.dot`.

## Método: emular en vez de leer
`PlayerActionGraph_build` (0x001A956C) mide más de 32 KB y el C de Ghidra reutiliza variables (`uVar110` es un componente y luego una condición), así que leerlo a mano es frágil. Se **emula con Unicorn** (`tools\emular_grafo.py`):
- Se le pasa un `PlayerCore` falso: el campo `k` vale `0x30000000 + k*0x1000`, así cada argumento se resuelve a `ctx[k]`.
- Cada llamada (`bl`/`blx`) se intercepta: `operator_new` reparte un montículo falso, el resto devuelve `this`. No corre nada más del juego.
- Resultado: 1.656 llamadas, 370 objetos, **60 nodos, 721 aristas** (619 únicas). Termina limpio (`ok`).
- `tools\analizar_grafo.py` vuelca las llamadas crudas (`extraido\grafo_mario.txt`); `tools\grafo_legible.py` traduce.
- **Verificado:** 3 aristas de muestra cotejadas contra el C decompilado coinciden argumento por argumento.

## Estructura (CONFIRMADO)
- `PlayerActionNode` (0x00252134) envuelve un estado. `PlayerActionNode_addEdge` (0x00251E20) = `(nodo, condición, destino)`.
- Las aristas se registran en orden; las 4 primeras de casi todo nodo son globales: **Morir, DeslizarPared, Nadar, NadarSuperficie**, y en ellas *el propio estado destino hace de condición* ("quiere entrar").
- Condiciones = objetos con vtable mínima; **`evaluar()` está en vptr+8**. Casi todas son reenvíos de una línea: `return componente->vf_k()`.
- **Prioridad CONFIRMADA:** `PlayerActionExecutor_selectNext` (0x0018144C) recorre las aristas en orden de registro (`LinkList_pushBack` 0x0028E940 agrega al final) y **gana la primera que se cumple**. Por eso las globales (Morir, DeslizarPared, Nadar) van primero.
- Combinadores: AND (0x0025204C, evalúa todas), OR (0x00251FB8), NOT (0x00252078), "N frames seguidos" (0x00251F4C).

## Componentes del contexto (`ctx[k]` = campo k de PlayerCore)
| ctx | Qué es | Evidencia |
|---|---|---|
| 0x0 | Física: pos, vel en +0x24, arriba +0x18, gravedad +0x60 | lecturas en las condiciones |
| 0x3 | **PlayerInput** (`player+0x78`) | argumento 1 de PlayerCore__ctor en initPlayer — CONFIRMADO |
| 0x5 | Colisionador (0xB8, 6 sub-chequeadores); `vf24` = **en el suelo** | 118 usos; Esperar→Caer si NO |
| 0x7 | Animación (`player+0x7c`): `vf18(nombre)`, `vf1c` = frame | "HipDropLand" |
| 0x8 | Banderas de petición externa (bits) | `ands r0, 1<<bit` |
| 0x10 | **Forma / power-up** (`== 5` → Estatua; 3 valores → tanuki) | HIPÓTESIS |
| 0x1a | `vf0` ≈ "es Mini" | HIPÓTESIS: bloquea agacharse |
| 0x2a | `vf0` ≈ "techo bajo, agacharse forzado" | HIPÓTESIS |

## Control (PlayerInput_update, máscaras lógicas del juego)
`1|2` = A/B (salto) · `8|0x10` = X/Y (correr/ataque) · `0x2000|0x4000` = L/R (agacharse). `0x24CA44` = pulsó, `0x250ED8` = mantiene (deducido: el "pulsó" reinicia el contador de frames).
**Buffer de salto: 5 frames** (`+0x34 < 5`) — y otro de 5 frames para X/Y (`+0x48`). Para el port: la ventana de entrada es parte de la sensación del juego, hay que copiarla tal cual.

## Lecturas que ya da el grafo (ejemplos)
- Triple salto: `Salto → Salto` si pulsó A/B ≤5 f **y** en suelo **y** no subiendo.
- Caída lenta tanuki: forma tanuki **y** cayendo **y** no en suelo **y** mantiene A/B.
- Estatua: forma == 5 **y** pulsó L/R. La Estatua no tiene la arista global de Daño.
- Frenar: stick contrario a la velocidad; Esperar: velocidad ≈ 0.

## Lo que queda abierto
- **0 condiciones crudas** desde el 7 oct (ronda 2).
- Quedan 5 nombres con `?`, cada uno con su hipótesis: InicioDeEscena, CaerInicio/CaerInicio2, NadarInicio (solo se llega desde el primer nodo), RebotePisotón ya CONFIRMADO: `ctx8.bit1` lo pone `PlayerActor_attackSensor` tras un pisotón aceptado, ver `reportes\mensajes.md` y EmpujarPared (15 frames de stick + pared al frente).
- Colisionador: `vf24` = en suelo · `vf28` (col[2c]) = **pared al frente** (lleva a ChoquePared desde salto largo/ataque de cola) · `vf2c` (col[30]) = **pared agarrable** (AgarrePared→SaltoPared) · `vf30` (col[28]) ¿techo? (1 uso) · `vf34/vf38` sin uso en el grafo.
- `toca Floor_code N?`: `FUN_00225498` compara el campo `+0xc` de cada contacto con N; N = 2/3 → Morir (cuadra con Floor_code 2 = lava de `reportes\colision.md`).
- Campos de contexto aún sin nombre: `ctx15, 16, 24, 30, 34, 35`. Con nombre por uso (HIPÓTESIS): `ctx1b` = tipo de entrada a la escena, `ctx2b` = caja hélice, `ctx14` = vida, `ctx25` = superficie del agua, `ctxc` = zonas (`vf4` = en agua).
- Nombres aplicados al `.gpr` por el MCP (7 oct). Faltan los 8 getters de PlayerInput (`0x00326Cxx`): Ghidra no los tiene como función; se aplican con `tools\aplicar_simbolos.py` en la próxima regeneración.
