# Agente E — gsp::Gpu HLE (`recomp\gpu\`) — 8 oct 2026

## Resultado
- **`py recomp\gpu\probar_gsp.py`: buena 438/438 comprobaciones OK; sabotajes detectados 6/6.** Compila sin avisos (`-Wall -Wextra`, zig cc).
- Referencia: Azahar (solo lectura) `hle\service\gsp\gsp_gpu.cpp/.h`, `gsp_command.h`, `gsp_interrupt.h`, `video_core\gpu.cpp`, `renderer_software\sw_blitter.cpp`, `pica\regs_external.h`, `regs_lcd.h`, `utils.h` (Morton), `common\color.h`. Reimplementado, sin copiar.

## Archivos (todos nuevos)
- `recomp\gpu\gsp.h` — API + contrato `void pica_ejecutar(uint32_t dir_fisica, uint32_t tam)` y gancho `GspPicaFn gsp_pica`.
- `recomp\gpu\gsp.c` — servicio. Sabotajes con `-DSABOTAJE=n`.
- `recomp\gpu\prueba_gsp.c` — prueba en C; `recomp\gpu\probar_gsp.py` — compila la buena + 6 sabotajes y exige que fallen. Binarios en `recomp\gpu\build\`.

## Qué implementa
- **IPC** (`gsp_ipc(cmd, sesion)`): WriteHWRegs 0x0001, WriteHWRegsWithMask 0x0002 (validación como el GSP real: 0xE0E02A01 rango/alineado, 0xE0E02BEC tamaño >0x80, 0xE0E02BF2 tamaño no múltiplo de 4), ReadHWRegs 0x0004 (escribe en el buffer estático 0 de TLS+0x180 = `cmd[0x41]`), Flush/InvalidateDataCache 0x0008/0x0009 (no-op), SetLcdForceBlack 0x000B (registros de relleno LCD 0x1ED02204/0x1ED02A04), TriggerCmdReqQueue 0x000C, RegisterInterruptRelayQueue 0x0013 (crea la shm 0x1000 por el anfitrión; 1ª vez 0x2A07; respuesta `0x00130082` {res, id de hilo, 0, shm}), Unregister 0x0014, AcquireRight 0x0016 / TryAcquireRight 0x000F / ReleaseRight 0x0017, ImportDisplayCaptureInfo 0x0018; el resto (SaveVramSysArea, RestoreVramSysArea, SetInternalPriorities…) "OK".
- Id de hilo GSP por sesión: el primero libre (0..3) al ver la sesión por primera vez (el juego hace AcquireRight ANTES de Register).
- **Registros**: banco GPU 0x1EF00000 (0x800 palabras) y LCD 0x1ED02000; escribir el disparo de MemoryFill (0x1C/0x2C), DisplayTransfer (0xC18) o lista (0x18F0/F4) ejecuta como el hardware.
- **Cola GX** (shm+0x800+hilo*0x200; cabecera índice/cantidad/estado/parar; 15 × 0x20): RequestDma(0, copia virtual→virtual, DMA), ProcessCommandList(1 → `gsp_pica(física, tam)` + P3D), MemoryFill(2; 16/24/32 bits; con los dos buffers solo PSC0; sin interrupción si inicio=0), DisplayTransfer(3) y TextureCopy(4) (→ PPF), CacheFlush(5, no-op), bit "stop".
- **DisplayTransfer**: mosaico↔lineal, mosaico→mosaico, lineal→lineal; 5 formatos (RGBA8, RGB8, RGB565, RGB5A1, RGBA4); volteo; escala X/XY (promedio); volteo+recorte con el sesgo del hardware. **TextureCopy** con anchos/huecos (unidades de 16 bytes; hueco 0 = contiguo).
- **Interrupciones**: cola de relevo en shm+hilo*0x40 (índice, cuenta, error, config bit0 = ignorar PDC, PDC perdidos, 0x34 slots); PDC a todos los hilos registrados, el resto solo al hilo con derechos; desde 0x20 pendientes los PDC se cuentan como perdidos; cola llena → error=1. Evento del hilo señalado por callback.
- **`gsp_vblank()`**: PDC0 y PDC1; por cada hilo registrado lee `shm+0x200+(2*hilo+pantalla)*0x40` {índice (byte 0), dirty (byte 1), 2×FrameBufferInfo de 0x1C en +4/+0x20}; si dirty aplica a los registros del framebuffer (izq/der 1 o 2 según active_fb, stride, formato, select = shown_fb) y limpia la marca. Luego presenta las dos pantallas: `GspPresentacion` con el framebuffer elegido por el select, ya **enderezado** a 400×240 / 320×240 RGBA (la memoria del LCD va por columnas de abajo arriba), o el color de relleno si SetLcdForceBlack.
- **Memoria**: todo se copia por páginas (`puntero(virtual)`, una página por vez) porque rt_pagina no garantiza contigüidad entre asignaciones; la prueba pone el heap lineal en dos bloques separados y un fill que cruza el borde. virt↔fís como Horizon: lineal 0x14000000↔FCRAM 0x20000000 (y 0x30000000), VRAM 0x1F000000↔0x18000000, DSP 0x1FF00000.

## Sabotajes (todos detectados)
| n | sabotaje | fallas | lo pilla |
|---|---|---|---|
| 1 | Morton con x/y cambiados | 341 | referencia = la TABLA 8x8 dibujada, no el entrelazado de bits |
| 2 | dirty ignorado (se aplica siempre) | 5 | VBlank sin dirty no debe cambiar el fb |
| 3 | RGB565 con verde a 5 bits | 2 | valor a mano 0x8204 |
| 4 | cola de relevo sin vuelta en 0x34 | 2 | vuelta 0x31→0x01 |
| 5 | lineal sin traducir a física | 9 | dirección física de la lista PICA y del fb |
| 6 | volteo del DisplayTransfer ignorado | 2 | mosaico→lineal con volteo |

## Lo que NO cubre / pendiente
- No hay ventana: `presentar` es un callback; falta el backend (SDL2/GL) que pinte `rgba`.
- Sin retardos de GPU: todo se ejecuta e interrumpe en el acto (como Azahar con "simular tiempos" apagado).
- Fill de 24 bits: se recorta en `fin` (Azahar puede escribir hasta 2 bytes de más).
- Estéreo: se presenta solo el ojo izquierdo. Save/RestoreVramSysArea = no-op.
- Sin verificar contra el juego real: falta integrarlo y ver el primer frame.

## PEDIDOS DE INTEGRACIÓN (no toqué archivos ajenos)
**A `recomp\sistema\sistema.c` (agente C / dueño de la capa):**
1. `case SRV_GSP:` → `gsp_ipc(cmd, <id estable de la sesión>)`. `atender()` hoy no recibe la sesión: pasarle el handle (o el puntero del Obj) que hizo el SendSyncRequest.
2. En `sis_iniciar()`: `gsp_iniciar(&(GspAnfitrion){ puntero, crear_shm, senalar_evento, presentar, log })` con:
   - `puntero(v)`: `rt_pagina[v>>12] ? P(v) : NULL`.
   - `crear_shm(tam, &host)`: lo que hace hoy `bloque_compartido()` (Obj OB_BLOQUE) devolviendo handle **y** `o->host`.
   - `senalar_evento(h)`: marcar el Obj evento como señalado + `despertar_esperas()` (el hilo de eventos GSP 0x1095F4 espera ahí).
3. Llamar `gsp_vblank()` a 59,83 Hz (cada 4.481.136 ticks) en el bucle del planificador (sistema.c ~276 "aquí entrarán los eventos del anfitrión").
4. Quitar la respuesta propia de RegisterInterruptRelayQueue: la cabecera actual `0x00130042` está mal (2 normales + 2 traducidos = **`0x00130082`**) y no guarda el evento.
5. Enlazar `recomp\gpu\gsp.c` en el build del arranque.

**Con el agente F (`recomp\render\pica*`):** `gsp_pica = pica_ejecutar;` y `pica_memoria = gsp_fisica_a_host;` (misma firma `const uint8_t *(uint32_t fisica, uint32_t tam)`; devuelve NULL si el rango no es contiguo en el anfitrión → F debería caer a `gsp_leer_fisica`). P3D lo señala el GSP al volver de la lista: F no necesita avisar.
