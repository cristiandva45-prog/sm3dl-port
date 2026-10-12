# Recompilación estática ARM11 → C (prototipo, 7 oct 2026)

Traduce funciones del juego a C que corre sobre un procesador virtual (`runtime\recomp.h`). Es el camino elegido para el port tras probar la decompilación a mano (`decomp\`), que funciona pero no escala.

## Piezas
- `recomp.py`: traductor. Recorre cada función desde su entrada siguiendo saltos (no traduce literal pools); una instrucción = sentencias C; saltos internos = `goto`; `bl` = llamada; indirectos = `rt_llamar` (tabla al final del C generado). `--cierre` agrega las funciones llamadas; `--excluir` deja fuera las que una prueba stubea.
- `runtime\recomp.h`: CPU virtual (r0–r15, NZCV, s0–s31, banderas FPSCR), desplazador con acarreo, `add_f/sub_f` con banderas, `vcmp`, `vcvt` saturante, NaN por defecto (`FB`).
- `runtime\runtime.c` + `anfitrion_pipe.c`: ejecución NATIVA x86-64 (FTZ/DAZ = RunFast del 3DS) con un anfitrión `.exe` que habla por tubería con el verificador. **Bloqueado hoy por Smart App Control** (ver abajo).
- `runtime\runtime_arm.c` + `verificar_recomp_arm.py`: verifica la **lógica del traductor** compilando el C generado para ARM y corriéndolo en Unicorn al lado de la original. Reutiliza todo `decomp\verificar.py` (generadores, espías, stubs con guion, comparación).
- `sabotear_recomp.py`: errores sembrados en el traductor/runtime.

## Resultados
- Lote piloto: 17 funciones + dependencias = 27 funciones, 515 instrucciones, **0 sin soporte**. **17/17 verificadas** (300+ pruebas c/u) contra la original.
- 6 de esas funciones **Ghidra no las tiene** (métodos llamados solo por vtable): el recompilador del juego entero debe descubrirlas solo (recorrer vtables). Por ahora el límite es la siguiente función conocida.
- Sabotaje del traductor: 5/9 detectados. Los 4 restantes, explicados:
  - **LS y `sxth`: 0 usos en el lote** → hace falta una batería por instrucción (cada forma probada sola contra Unicorn), no solo por función.
  - **NaN sin normalizar y `lsl` por 32**: solo fallan en x86; compilado para ARM, el hardware ARM da el resultado correcto y lo tapa. Se ven únicamente con el anfitrión nativo.

## FPSCR del 3DS (corregido 7 oct)
El juego configura el VFP **una sola vez** (`vmsr fpscr` en `0x105208`) con **`0x03000000`** = DN + FZ y **redondeo al más cercano**. Hasta el 7 oct los verificadores usaban `0x03C00000` (supuesto, no leído del binario), que además enciende **redondeo hacia cero**: la ejecución nativa x86 lo destapó (3 funciones de float fallaban; p. ej. `0,001 − 10⁸ + 10⁸` daba 8 en vez de 0). Con el valor del juego: **17/17 en decomp a mano, recomp en ARM y recomp nativa x86-64** (1.000 pruebas c/u).

## Smart App Control
**Apagado por el dueño el 7 oct** (estado 0) → la ejecución nativa funciona (`verificar_recomp.py`). Antes:
Windows tiene Smart App Control **activo** (`HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState = 1`). Bloquea la DLL y el `anfitrion.exe` propios (no por carpeta: por contenido/reputación). Un `hola.exe` mínimo sí corre. Desactivarlo es decisión del dueño (históricamente, en Windows 11 apagarlo era definitivo salvo reinstalar o restablecer Windows; verificar cómo funciona en su versión antes de tocarlo). Alternativas: firmar el binario con un certificado de confianza, otra PC/VM sin SAC, o seguir verificando la lógica en ARM y dejar lo nativo para después.

## Juego entero y batería por instrucción (7 oct, cierre)
- `py -I recomp\recomp.py --todo -o recomp\gen\todo.c`: 12.283 funciones, 552.738 instrucciones, 1 sin soporte.
- `py -I recomp\bateria.py -k 3 -n 80`: censo de 444 formas; **444/444 OK**. Bugs que encontró y se corrigieron:
  - `adc/sbc/rsc` sin S tocaban banderas (capstone marca `update_flags` en lo que solo LEE el acarreo → la S se decide por mnemónico).
  - `vnmul` con NaN: normalizar el producto y DESPUÉS cambiar el signo (`0xFFC00000`).
  - constante rotada `#24, #28`: capstone la da como dos inmediatos.
  - `vmsr fpscr` debe cargar las banderas NZCV del FPSCR.
- Antes, con el censo: `lsl/lsr/asr` llegan como `mov` con desplazamiento (2 operandos); `bls/blo` empiezan con "bl" (el recorrido usa ahora el id de capstone); tablas de saltos `cmp rX,#N ; ldrls pc,[pc,rX,lsl #2]` → `switch` (141).
- Unicorn NO implementa TPIDRURW (c13,c0,2): la batería no lo compara.

## Retorno calculado en 0x3A0B68 (pendiente, analizado el 7 oct)
Unica funcion del juego que no vuelve a `bl+4`: lee una palabra de datos detras del `bl` (`ldr r4, [lr], #4`) y vuelve a `X+8+4*codigo` dentro del llamador, o retorna POR el llamador (`pop {r4, pc}`). Solo 2 llamadores (0x3A0D08, 0x3A0D7C); sus palabras de datos son el `cdplo` y el `(no decodifica)` del censo de "sin soporte". Contrato y diseno del arreglo en `ESTADO.md` (seccion del agente O). Hasta aplicarlo, esos dos caminos (casos NaN/inf de la libreria de float) corren mal.
