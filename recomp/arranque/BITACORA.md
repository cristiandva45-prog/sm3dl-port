# Primer arranque — bitácora (7 oct 2026, agente F)

## Cómo se arma y se corre
```
sh recomp/arranque/reconstruir.sh      # generar.py (copia del traductor + arreglos) → partir → compilar (≈35 s) → sm3dl.exe
recomp\arranque\sm3dl.exe > log.txt 2>&1   # desde la raíz del port; SM3DL_SIN_TRAZA=1 para no registrar cada svc
```
- `main.c`: carga `extraido\code.bin` en 0x00100000 (escribible), `.bss` en cero hasta 0x00431058, pila 0x20000 bajo 0x10000000, prio 0x30 (exheader), `sis_iniciar`, FTZ/DAZ, `sis_correr(0x00100000, …)`. Registra cada svc (`sis_traza`) e IPC.
- **Espejo de 4 GB**: las páginas sin mapear apuntan a una reserva sin memoria; un acceso fuera de mapa dice la dirección EXACTA del 3DS. El manejador también nombra la función recompilada (`f_XXXXXXXX`) con el PDB (dbghelp).
- El juego es una COPIA propia: `recomp_base.py` (traductor congelado) + `generar.py` (arreglos) + `parchear.py`. No depende de `recomp.py` ni de `gen\todo.c`.

## Obstáculos
1. **`rt_externo 0x001001A8`** (2ª instrucción del crt0). `mov pc, lr` (retorno estilo ARMv4) se traducía como salto indirecto `rt_llamar(lr)`. 55 casos (36 `mov pc, lr` + 19 condicionales). **Arreglo** (`parchear.py`): → `return;`. Hay que llevarlo a `recomp.py`.
2. **`rt_externo 0x0029348C`**. Ghidra tiene funciones SOLAPADAS (0x293474 y 0x293478) y su tamaño deja fuera la llamada de cola `b 0x1051F0`. `limite()` cortaba en la "siguiente" función, que estaba dentro del propio rango. **Arreglo** (`generar.py`): límite = primera función que empiece en o después de `a + tam_ghidra`. Hay que llevarlo a `recomp.py`. El juego sube a 17.038 funciones.
3. **ACTUAL: bucle infinito de `ArbitrateAddress` tipo 2 sobre 0x003FA700, valor 0, en 0x0028EC60** (log de 95 M líneas en 60 s). Es el lock del SDK (0x28EC20): `ldrex`; si el valor es > 0, lo toma negándolo; si es ≤ 0, entra en `DecrementAndWaitIfLessThan(addr, 0)` y reintenta. La capa de sistema no espera si `*addr >= 0`. Con 0 en memoria, el juego reintenta para siempre.
   - Hipótesis: el lock vale **0 = sin inicializar** (está en `.bss`). Falta el constructor que lo pone en 1, o está corrido por el orden del crt0. Otra posibilidad: un lock con 0 = "tomado sin contención" y otro hilo que lo debía soltar.
   - Siguiente paso: mirar quién escribe en 0x3FA700 (xrefs) y si algún `bl` del crt0 (0x100190, 0x293474, 0x1007B4, 0x3A0D9C, 0x10015C, 0x1001DC, 0x100108) lo inicializa. Revisar también que `code.bin` (3.096.576 bytes, hasta 0x3F4000) no pise el comienzo del `.bss` (0x3F39D4) con datos distintos de cero.

## Svc vistas hasta el bucle
`0x21 CreateAddressArbiter` (0x101B28), luego `0x22 ArbitrateAddress` en bucle.

## Obstáculo 3 (agente J, 7 oct): lock 0x003FA700 en bucle → RESUELTO
- **Causa:** el lock lo pone en 1 el constructor estático `0x380C20` (ldrex/strex). Los constructores los llama `__cpp_initialize__aeabi_` (0x3A0D9C) recorriendo `.init_array` [0x3A0DDC, 0x3A177C) — **entradas RELATIVAS a sí mismas** (armcc), ~616 — con `add lr, pc, #4 ; mov pc, r0`. El traductor tomaba `mov pc, r0` como salto de cola: corría UN constructor y retornaba. La capa de sistema estaba bien.
- **Arreglo 3 (generar.py):** `add lr, pc, #k` / `mov lr, pc` + `mov pc, rX` / `bx rX` con lr = instrucción siguiente = LLAMADA (`rt_llamar` y sigue). 25 sitios en el juego.
- **Arreglo 4 (generar.py):** los destinos de `.init_array` se agregan como funciones (no los ve ni Ghidra ni descubrir_funciones.py: no hay puntero absoluto). 17.038 → 17.652 funciones, 641.317 instrucciones.
- **Log:** `sis_svc_num` registra cada (svc, dirección) a lo sumo 20 veces.
- **Ojo:** el exe se corre desde la RAÍZ del proyecto (`recomp\arranque\sm3dl.exe`): la ruta de code.bin es relativa.
- **Nuevo punto de parada:** svc 0x21, 0x38, 0x3A, 0x23, 0x01 (ControlMemory) y luego `rt_externo: salto a 0x001ED5B4 sin traducir (lr=0x0028EAE0)` — otro destino indirecto que nadie ve como función (ver qué llama desde ~0x28EAD8: probablemente otra tabla relativa o un puntero calculado). Ninguna IPC todavía.
- **Llevar a recomp.py / descubrir_funciones.py:** arreglos 3 y 4 (y semillas de tablas relativas en general).

## Obstáculos 4-8 (agente B, 8 oct) — se llega al primer IPC y mucho más
Herramienta nueva: **`unicorn_arranque.py`** corre el código ARM ORIGINAL con el mismo mapa que main.c y svcs como sistema.c (un hilo) hasta el 1er `svc 0x32`, y **comprueba el traductor**: todo destino de un salto por registro (o de un sitio donde todo.c emite `rt_llamar(c, v)`) debe ser función de todo.c, y ningún salto directo debe caer en un `rt_externo(c, 0x…)` constante. Avisa ANTES de compilar. Sabotajes: `--quitar 1ED5B4` → avisa en 0x28EADC; todo.c sin el parche de `ldr pc,[sp],#k` → avisa 0x380444 desde 0x28E224 (= el fallo exacto del exe). Smart App Control bloqueó una vez el exe nuevo; la corrida siguiente pasó (no se esquivó nada).
4. **`rt_externo 0x1ED5B4`** (vec_ctor 0x28EAB4 `mov lr,pc; mov pc,r6`). Puntero a función en el literal pool del constructor 0x38A188. Los constructores (arreglo 4) no existían cuando corrió descubrir_funciones → sus literales nunca se sembraron. **Arreglo 5** (`generar.py: derivadas`): cierre de literales/saltos sobre las funciones nuevas, con la validación de descubrir.
5. **(lo vio Unicorn) 0x289EA0 / 0x10A470** (callbacks de `_scanf` 0x10AED4, `add lr,pc,#4; mov pc,r1`). Punteros **PC-relativos** de la biblioteca de armcc: `ldr rX,[pc,#k]; add rY,pc,rX` → literal+add+8. **Arreglo 6** (`punteros_relativos`): 6 en todo .text, entran como "forzadas" (se exige que decodifiquen y terminen).
6. **`rt_externo 0x288738`** (`__aeabi_uidiv` 0x28966C: `b 0x288738` al núcleo de división compartido; descubrir lo rechaza "no termina" porque cae por flujo en 0x288760). **Arreglo 7** (`generar.py main`): todo `rt_externo(c, 0xCONST)` del C generado = salto directo a código sin función → se agrega como función y se regenera (3 vueltas: 0x154A84, 0x288738, 0x28875C, 0x154C2C, 0x288920, 0x154C20). Queda 0 en todo.c.
7. **`rt_externo 0x380444`** (lr viejo 0x109254). `ldr pc, [sp], #0x14` = epílogo de función VARIÁDICA (0x28E1DC, vsnprintf) se traducía como `rt_llamar(v)` a la dirección de vuelta. **Arreglo** (`parchear.py` 2): → `return;` (conserva la carga y el ajuste de sp). 28 sitios.
8. **`rt_externo 0x1BD118`** (hilo 7, `blx r2` en 0x318910). Método de vtable DENTRO del rango de Ghidra 0x1BD0E4 (Ghidra fundió dos métodos). **Arreglo 8** (`punteros_internos`): punteros de .rodata/.data a .text que caen dentro de un rango de Ghidra justo tras un final incondicional → 21, validados.
- Total: 17.652 → **17.716 funciones**. `compilar.py` ya enlaza hid/gsp/pica/dsp/WASAPI (agente C); `--sin-servicios` = capa base.

### PRIMER IPC (Unicorn y exe coinciden)
`ConnectToPort("srv:")` (0x28DC3C) → **`svc 0x32` en 0x102B1C** (lr 0x293010, `SRV_RegisterClient` 0x102AF8): cabecera **0x00010002** = srv: comando 0x0001 **RegisterClient**, 0 normales, 2 traducidas: `00000020 00000000` (descriptor *calling PID*, valor 0). Coincide con `extraido\ipc_comandos.tsv`. Svcs previas: 0x21, 0x38, 0x3A, 0x23, 0x01 (ControlMemory 64 MB), 0x27, 0x13.

### Estado del exe (log6, 60 s): 417 IPC
srv: 17, APT:U 9, ndm:u 3, fs:USER 3 + **RomFS 202 lecturas**, cfg:u 2, **gsp::Gpu 138**, hid:USER 2, **dsp::DSP 40**; hasta 9 hilos. Un "SIN APT:U" en el log (revisar con C.md: despertar vs sin parámetros).
**ACTUAL: `rt_externo 0x2DDC24`** (hilo 1, `blx r1` en 0x2F226C, método 0x14 de una vtable). 0x2DDC24 = `bx lr` tras un literal pool dentro de 0x2DDAF8 (340 B de Ghidra); NO aparece como palabra en code.bin ni como PC-relativo → la vtable se arma en tiempo de ejecución o el puntero está en otra forma. Siguiente paso: buscar quién escribe esa vtable (o `0x2DDC24 - k` en .data).
