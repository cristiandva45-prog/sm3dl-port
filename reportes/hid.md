# Entrada (hid:USER) — agente M, 7 oct 2026

## Memoria compartida de hid:USER (la que entrega GetIPCHandles)
Layout leído de Azahar (`src/core/hle/service/hid/hid.h`, solo lectura) y fijado con `_Static_assert` en `recomp/hid/hid.c`:

| Offset | Bloque | Contenido |
|---|---|---|
| 0x000 | pad | s64 ticks del reinicio del índice 0, s64 anterior, u32 índice, pad, f32 slider 3D, u32 estado actual, u32 circle crudo, pad, **8 entradas × 0x10** {actual, altas, bajas, s16 cx, s16 cy} |
| 0x0A8 | touch | igual cabecera, entrada cruda, **8 × 8** {u16 x, u16 y, u32 válido} (píxeles de la pantalla inferior 320×240) |
| 0x108 | acelerómetro | cabecera, Xyz crudo + 2, **8 × 6** {s16 x, y, z} |
| 0x158 | giroscopio | cabecera, Xyz crudo + 2, **32 × 6** |
| 0x238 | fin | |

- Bits de botones: A0 B1 Select2 Start3 →4 ←5 ↑6 ↓7 R8 L9 X10 Y11; circle pad digital en 28–31 (→ ← ↑ ↓).
- Circle pad: ±0x9A a fondo, **promedio de 3 muestras**, dirección digital si el radio > 40, con sectores de 60° (diagonal = dos bits; tan 30 / tan 60).
- Cada muestra: `índice` = siguiente posición del anillo de 8; altas = cambiados & actual, bajas = cambiados & anterior; al volver al índice 0 se copian los ticks a `ticks_prev` y se guarda el tick actual.
- Ritmo en hardware: **pad+touch a 234 Hz** (señala los eventos PadOrTouch1 y PadOrTouch2), acelerómetro 104 Hz, giroscopio 101 Hz. GetIPCHandles devuelve: shm, PadOrTouch1, PadOrTouch2, Accelerometer, Gyroscope, DebugPad.

## Qué lee el juego (confirmado en code.bin)
- `PlayerInput_update` (0x00133484) **NO lee la shm**: trabaja sobre una estructura de mando ya procesada que recibe en r1 (lee +0x04/+0x08/+0x14/+0x18/+0x24/+0x28 y los combina con una matriz de cámara para orientar el stick). La lectura de la shm ocurre más abajo, en la capa del SDK.
- `HID_Initialize` (0x001F3AC4, `simbolos.txt`) es un **thunk**: r0 = global `0x00424FC8` (estado HID del SDK), r1 = `[0x003A98D8 + 8]`, salta a **0x001F3890** (ahí se mapea la shm y se guarda el puntero).
- Usa también acelerómetro y giroscopio (wrappers Enable/Disable de los dos en 0x1F51A0–0x1F524C, más calibración del giroscopio): el port debe llenar esos bloques aunque sea con reposo (gravedad en el eje del acelerómetro, giro 0).
- **Pendiente:** seguir 0x001F3890 → puntero de la shm dentro de 0x424FC8 → funciones que leen `pad.índice` / `pad.e[k]` (el lector del SDK que arma la estructura que llega a PlayerInput_update).

## Lo que hay en `recomp/hid/`
- `hid.h/.c`: estructura `HidShm` (offsets con `_Static_assert`), `hid_muestrear()` (anillo, altas/bajas, ticks, promedio y dirección del circle pad, touch) y `hid_leer_pc()` (teclado + XInput con zona muerta radial reescalada; A del 3DS = B del mando Xbox, por posición).
  - Teclado: flechas = cruceta, IJKL = circle pad, X = A, Z = B, S = X, A = Y, Q = L, W = R, Enter = Start, Retroceso = Select.
- `prueba_hid.c`: pulsar/soltar, circle pad a fondo y en diagonal, vuelta completa del anillo con ticks, touch. **OK**. Sabotaje (altas calculadas con el estado anterior) → **2 FALLAS**, detectado.
- Compila: `py -m ziglang cc -target x86_64-windows-gnu -O2 -Wall -Wextra hid.c prueba_hid.c -lxinput1_4 -o prueba_hid.exe` (sin avisos). Ojo: `-lxinput` no existe en zig, es `-lxinput1_4`.
- Falta conectarlo a `recomp/sistema`: GetIPCHandles debe devolver esta shm (mapeada en la dirección que pida el juego) y los 5 eventos, y un hilo de la PC debe llamar `hid_muestrear` a 234 Hz y señalar PadOrTouch1/2.

---
# Cadena completa: del anillo de hid:USER a PlayerInput_update — agente D, 8 oct 2026 (estático, capstone)

## 1. Estado del SDK en 0x424FC8 (lo llena 0x1F3890, llamado por HID_Initialize 0x1F3AC4)
0x1F3890(estado r0, nombre "hid:USER" r1): srvInit, GetServiceHandle (handle global 0x3F0374), `HIDUSER_GetIPCHandles` (0x1F5124: cmd 0x000A0000 en TLS+0x80; lee las palabras 3..8 de la respuesta = shm, PAD0, PAD1, accel, gyro, debugpad), MapMemoryBlock (0x10B1F4) de **0x2B0 bytes** sobre `estado+0x2C` (la dirección elegida por el juego queda en `estado+0x34`), y rellena un bloque {evento, puntero} por dispositivo:

| estado+ | contenido |
|---|---|
| 0x00 / 0x04 | evento PAD0 / puntero a shm+0x000 (pad) |
| 0x08 / 0x0C | evento PAD1 / shm+0x0A8 (touch) |
| 0x10 / 0x14 | evento accel / shm+0x108 |
| 0x1C / 0x20 | evento gyro / shm+0x158 |
| 0x24 / 0x28 | evento debugpad / shm+0x238 |

Los eventos se guardan, pero no se encontró ningún WaitSync sobre ellos en el camino del pad: el juego **sondea** la shm (lee lo último cada fotograma). Señalarlos es por fidelidad (a confirmar en el primer arranque).

## 2. Lector del anillo (SDK, nn::hid::CTR)
- Getters de bloques: `0x1F5118` → &estado (0x424FC8, pad), `0x1F3AE8` → 0x424FD0 (touch), `0x1F3ADC` → 0x424FE0.
- **`0x00297690` = ReadPad del anillo** (r0 = bloque pad, r1 = salida, r2 = máx. pedidas, r3 = &n devueltas; pila: &último_tick, &último_índice). Layout confirmado: `[blk+0x10]` = índice, `[blk+0]/[blk+8]` = ticks / ticks_prev, entradas de 0x10 bytes desde `blk+0x28` (actual, altas, bajas, s16 cx, s16 cy), módulo 8. Compara los ticks del lector con los de la shm para saber cuántas muestras nuevas hay (máx. 8). **Consecuencia:** `ticks` debe ser monotónico y el índice avanzar mod 8, justo lo que hace `hid_muestrear`. Con 1 entrada pedida lee la más reciente (`e[índice]`).
- **`0x001F52E8` = PadReader::Read(this, salida)**: llama 0x297690 (n=1), recorta el stick (mínimos 0x28/0x24, máximos 0x91; rango del circle pad ±0x9A), según `this+0x19` elige modo de zona muerta (0x29733C/0x297238/0x29741C), mantiene `this+8` (estado anterior), recalcula altas = `(act^ant)&act`, bajas = `ant&~act` y **limpia el bit 0x2000**. Devuelve 1 si hubo muestra. Ctor: `0x1F572C`.
- `0x1F54C0` normaliza el stick (cx, cy) a vec2 float [-1,1] con curva y zona muerta (`this+0x1C/0x24/0x28/0x2C`).
- Acelerómetro: ctor `0x1F4E64` (Enable + calibración); giroscopio: ctor `0x1F4538` (Enable gyroscope; objeto de 0x1500 bytes).

## 3. Envoltorio del juego (singleton HID, getter `0x39A6DC`)
- **`0x2DA4FC` (puntero en la vtable de 0x3D95E8) = actualizar HID**: `PadReader::Read(this+0x15B4 → this+0x15B8)`, pone/limpia el bit 0 de `this+0x162C`; luego touch (0x1F47AC → `this+0x1CC`, bit 1).
- **`0x002DB000` = pasar el HID al "puerto de mando" del juego** (r4 = objeto del puerto, r5 = singleton HID). Si `hid+0x162C` bit0: mapea bit a bit `hid+0x15B8` (botones HID) al bitfield propio `puerto+0x110` (A→0x1, B→0x2, 0x8→0x800, 0x10→0x80000, 0x20→0x40000, 0x40→0x10000, 0x80→0x20000, 0x100→0x4000, … hasta 0x200000) y llama `0x1F54C0(reader=hid[0x15B4], puerto+0x11C, puerto+0x120, cx, cy)` → **stick normalizado en `puerto+0x11C/0x120`**; pone a 0 `puerto+0x124..0x130` (segundo stick, inexistente en 3DS base). Si bit1: touch a 0x2DCE9C.
- `0x250ED8 isPadHold(puerto, máscara)`: puerto = global `0x3E26BC → +0xD8[índice]`, +4; devuelve `[+0x10C] & máscara`. `0x26DB44 getPadLeftStick` devuelve `puerto+4+0x118` (el vec2 de `+0x11C`).

## 4. Cadena resumida
```
PC (teclado/XInput) --hid_leer_pc--> hid_tick (234 Hz) --> shm (anillo de 8 + ticks) [mapeada por 0x1F3890 en estado+0x34]
  --> 0x297690 ReadPad (lee e[índice]; cuenta por ticks)
  --> 0x1F52E8 PadReader::Read (zona muerta, altas/bajas)
  --> 0x2DA4FC (singleton HID: hid+0x15B8, flag +0x162C)
  --> 0x2DB000 (bits HID -> puerto+0x110; stick -> puerto+0x11C/0x120)
  --> isPadHold 0x250ED8 / getPadLeftStick 0x26DB44
  --> PlayerInput_update 0x133484 (la estructura de r1 ya viene procesada; la combina con la cámara)
```
**Pendiente:** el llamador por fotograma de 0x2DB000 y la derivación +0x110 → +0x10C (hold/trigger). No hace falta para el HLE (basta llenar la shm); sí para depurar si Mario no se mueve.

## 5. Servicio HLE: `recomp/hid/servicio_hid.c/.h` (+ `prueba_servicio_hid.c`)
- `hid_srv_comando(h, cmd)` atiende **0x0A GetIPCHandles** (respuesta `0x000A0047`, result, descriptor `0x14000000`, shm + 5 eventos en orden PAD0, PAD1, accel, gyro, debugpad: coincide con lo que lee 0x1F5124), **0x11/0x12** accel Enable/Disable y **0x13/0x14** gyro Enable/Disable (con cuenta), **0x15** coeficiente (14,375), **0x16** calibración ({0, 6700, -6700}×3, 18 bytes), **0x17** GetSoundVolume (0x3F). Otro: devuelve 0.
- `hid_tick(h, estadoPC, ticks)` a 234 Hz: `hid_muestrear` (pad+touch; señala PAD0/PAD1) y, con Bresenham 104/234 y 101/234, acelerómetro (reposo plano, z = -512 = 1 g, supuesto) y giroscopio (0), solo si están habilitados.
- Prueba (`py -m ziglang cc -target x86_64-windows-gnu -O2 -Wall -Wextra hid.c servicio_hid.c prueba_servicio_hid.c -lxinput1_4`): **OK**, sin avisos. Sabotajes: (1) Disable sin restar + giro a 100 Hz → **3 fallas**; (2) eventos en orden invertido → **1 falla**. Ambos detectados.

### Pedido de integración (para `recomp/sistema`, agente C)
1. En SendSyncRequest sobre el handle de `SRV_HID`: `if (hid_srv_comando(&g_hid, <puntero host a TLS+0x80 como u32*>)) { RES_OK; break; }`.
2. Al arrancar: reservar una página host de 0x1000 para la shm, `hid_srv_iniciar(&g_hid, pagina, sis_senal_hid, NULL)`; crear 5 eventos (OneShot, como el servicio real) y un handle de memoria compartida; poner `g_hid.h_shm` y `g_hid.h_ev[0..4]`.
3. `svc MapMemoryBlock(handle_shm, addr, ...)` (0x1F3890 pide 0x2B0 bytes, solo lectura): mapear esa misma página host en `addr` (la elige el juego; queda en 0x424FC8+0x34).
4. Firma que necesito de sistema: `void sis_senal_hid(void *ctx, int evento)` (evento = `HIDEV_*`) que haga SignalEvent del handle `g_hid.h_ev[evento]`.
5. Un hilo del anfitrión (o el planificador) llama `hid_leer_pc(&e); hid_tick(&g_hid, &e, ticks)` cada ~4,27 ms (234 Hz); `ticks` coherente con `svcGetSystemTick` (268.111.856 Hz). Enlazar con `-lxinput1_4`.
