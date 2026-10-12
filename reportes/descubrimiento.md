# Auditoría del descubrimiento de funciones (agente B, 7 oct 2026)

Herramientas: `tools\descubrir_funciones.py` (ajustado) y `tools\auditar_descubiertas.py` (nuevo).

## 1. Verificación en ejecución (muestra de 30 de `funciones_extra.tsv`)
`py -I tools\auditar_descubiertas.py -k 30 -n 200`: cada función se traduce SOLA (sus llamadas salientes = stubs con guion,
iguales en los dos lados) y se compara la original en Unicorn contra la recompilada nativa x86-64. Entradas genéricas:
64 objetos espía en el montículo, con campos que son punteros a objetos, enteros chicos o floats. Las entradas que hacen
fallar a la ORIGINAL se descartan (no eran válidas para esa función).

| Resultado | n | Detalle |
|---|---|---|
| OK | 29 | 200 pruebas iguales c/u (algunas con menos: 0x1D9D6C 20, 0x2E6CEC 34, 0x330754 55, porque casi todas las entradas genéricas tumban a la original) |
| SIN DATOS | 1 | 0x2ABBEC: las 800 entradas hacen fallar a la original (necesita un generador a medida) |
| FALLA real | 0 | |

Las 2 "fallas" que aparecieron eran del BANCO, no del traductor:
- **0x330754**: lee como dato la zona de espías (`obj->+0x28->vt->+0x24`). Unicorn la llena con `bx lr` y el anfitrión nativo con
  ceros. Arreglado en el auditor (se escribe igual en los dos lados) → OK.
- **0x12EDBC**: bucle con un contador al azar enorme. **`Maquina.correr` usa `emu_start(count=2_000_000)` y Unicorn se
  detiene SIN error al agotar el tope**: la original "terminaba bien" sin haber terminado, y la nativa seguía y se salía
  del montículo. El auditor ahora descarta corridas que no vuelven a la trampa. ⚠️ **El mismo hueco está en
  `decomp\verificar.py` (lo usan `verificar_recomp*.py` y la batería):** conviene marcar como error cuando PC ≠ TRAMPA.
  Repetida con el arreglo: 0x12EDBC y 0x330754 → OK.
- 4 funciones "no compilaban" en la primera pasada porque otro agente tenía `recomp.py` a medio editar
  (`EXTENSIONES` sin definir); repetidas: 0x1041D4, 0x11B750, 0x142620 OK.

**Sabotaje del auditor** (`AUDITAR_SABOTEAR=1`: XOR en la primera escritura de r0 de la función): detectado en 5/6.
El que pasa, 0x2D1064, solo escribe r0 en la rama `cmp r0,#5; beq`, que las entradas al azar casi nunca toman: es un
punto ciego de las entradas genéricas, no del comparador.

## 2. Rechazos del validador: eran funciones reales
Los 397 "rodata: no termina" + ~80 de saltos/literales eran casi todos **funciones que caen por flujo en la siguiente**:
- thunks de herencia múltiple: `0x149750 sub r0,r0,#0x60 ; nop` → método de al lado; `ldr r0,[r1]; nop`; `ldrd r0,r1,[r0,#4]; nop`.
- `0x1051F0 push; bl; bl; pop {r4,lr}; nop` → sigue en 0x105204 (inicio del FPSCR).
- `bl 0x28E9D4; nop` (llamada que no vuelve).
- entradas a mitad de la división desenrollada del runtime (`rsbs/subhs/adcs`, 0x288760…).

El traductor ya resuelve la caída (`rt_llamar(fin)`), así que `valida()` las acepta si el corte cae EXACTO en el inicio de
una función conocida o aceptada (con espera si es una semilla aún sin decidir). Para semillas de punteros, guarda
estricta: ninguna palabra en 0 y primera/última instrucción incondicionales.

| | antes | después |
|---|---|---|
| aceptadas | 4.280 (70.310 instr.) | **4.755 (72.123 instr.)**, 466 de ellas caen en la siguiente |
| rechazadas | 479 | **14** (texto ASCII, ceros, decodificaciones raras: datos) |

Revisadas a mano las 475 nuevas con primera instrucción poco común: todas son código. Volcado de rechazos:
`extraido\funciones_rechazadas.tsv`. Respaldo previo: `recomp\build\funciones_extra.antes-auditoria.tsv`.
⚠️ `todo.c` NO se regeneró con esta lista (lo lleva otro agente): hay que regenerarlo.

## 3. Los 6 saltos huérfanos
Ninguno es un salto: son la "caída fuera de la función" (`rt_llamar(fin)`) que llega a la mitad de otra función.
- **Causa de 5 (0x13A7FC, 0x1FB2C4, 0x293474, 0x1F5F58, 0x256384): Ghidra tiene 416 funciones que se solapan con la
  siguiente** (su "tamaño" abarca otra función metida dentro). `recomp.limite()` toma `max(siguiente inicio, a+tam)`,
  o sea corta el flujo en el final de Ghidra, a mitad de código.
  **Propuesta para `recomp.py` (no lo toqué):** límite = primer inicio ≥ `a + tam[a]` (o > a si no hay tamaño).
  Probado sobre los 5: todos cierran (`b` de salida, `pop pc` o, en 0x1F5F58, caída en una función conocida).
- **0x3A8FA4**: Ghidra creó una "función" de 1 byte sobre `ExecuteOrderTable` en `.rodata` (fuera de `.text`, que acaba
  en 0x3A177C). **Propuesta:** que `tamanos()` descarte las entradas fuera de `.text`.

## Notas
- 🪛 `tools\dis.py` tapa el módulo estándar `dis` si `tools\` entra al `sys.path` (capstone importa `inspect` → falla).
  Cargar los scripts de `tools\` por ruta (`importlib`) o renombrarlo.
