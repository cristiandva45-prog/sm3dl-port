# Frontera con el sistema del 3DS: servicios, svc y GX

Lo hizo el agente "servicios" el 6 oct 2026. Los nombres propuestos están en `extraido/propuestas_servicios.txt` (188 líneas, 162 CONFIRMADAS y 26 HIPÓTESIS). **No se aplicaron a `simbolos.txt`.**

## Método
- Busqué en `code.bin` las 328 instrucciones `svc` (`0xEF0000NN`). Antes de cada `svc 0x32` tomé la última constante de header (literal pool, `mov` o `movw`) y la variable global de donde sale el handle.
- Para el inicio de cada función combiné dos fuentes: los destinos de BL y el último `bx lr`/`pop {pc}`/salto antes del svc, saltándome el literal pool y los nops de relleno.
- Comparé los headers con 3dbrew/libctru, agrupé por variable de handle y confirmé cada handle por la función que lo abre (`SRV_GetServiceHandle`). Usé 13 consultas a Ghidra.
- En este SDK los wrappers IPC **no** pasan por una función común. Cada uno lleva su `svc 0x32` inline: lee TLS (`mrc p15,0,rX,c13,c0,3`), escribe el header en TLS+0x80, carga el handle y hace `svc`. Por eso cada `svc 0x32` es un wrapper distinto.

## Servicios que abre el juego
Todos siguen el mismo patrón `X_Initialize`: `srvInit` (0x292EFC), luego `strlen` (0x292150) y luego `SRV_GetServiceHandle` (0x292114). Este último no recibe callbacks: lo llaman directamente **9 funciones**.

| Servicio | Handle global | Abre | Comandos usados (header) |
|---|---|---|---|
| `srv:` (puerto) | 0x3E26B4 | `srvInit` 0x292EFC (ConnectToPort) | RegisterClient 0x00010002, EnableNotification 0x00020000, **GetServiceHandle 0x00050100**, Subscribe 0x00090040, Unsubscribe 0x000A0040, ReceiveNotification 0x000B0000 |
| `gsp::Gpu` | 0x3E2694 | `GSPGPU_Initialize` 0x107A24 | WriteHWRegs 0x00010082, WriteHWRegsWithMask 0x00020084, ReadHWRegs 0x00040080, FlushDataCache 0x00080082, SetLcdForceBlack 0x000B0040, TriggerCmdReqQueue 0x000C0000, RegisterInterruptRelayQueue 0x00130042, AcquireRight 0x00160042, ReleaseRight 0x00170000, ImportDisplayCaptureInfo 0x00180000, SaveVramSysArea 0x00190000, RestoreVramSysArea 0x001A0000, SetInternalPriorities 0x001E0080 |
| `hid:USER` | 0x3F0374 | `HID_Initialize` 0x1F3AC4 | GetIPCHandles 0x000A0000, Enable/DisableAccelerometer 0x0011/0x0012, Enable/DisableGyroscope 0x0013/0x0014, GetGyroscopeRawToDpsCoefficient 0x00150000, GetGyroscopeCalibrateParam 0x00160000 |
| `fs:USER` | 0x3EF00C (+ sesiones de archivo/dir) | `FS_Initialize` 0x103E8C | Initialize 0x08010002, OpenFile 0x080201C2, OpenFileDirectly 0x08030204, DeleteFile 0x08040142, DeleteDirectory 0x08060142, CreateFile 0x08080202, CreateDirectory 0x08090182, OpenDirectory 0x080B0102, OpenArchive 0x080C00C2, ControlArchive 0x080D0144, CloseArchive 0x080E0080, IsSdmcDetected 0x08170000, IsSdmcWritable 0x08180000, 0x083F00C0 (?), GetArchiveResource 0x08490040, GetFormatInfo 0x084500C2, FormatSaveData 0x084C0242. Archivo: Read 0x080200C2, Write 0x08030102, GetSize 0x08040000, Close 0x08080000. Directorio: Read 0x08010042, Close 0x08020000 |
| `dsp::DSP` | 0x3E2674 | `DSP_Initialize` 0x1F2BD0 | RecvData, RecvDataIsReady, SetSemaphore, ConvertProcessAddressFromDspDram, WriteProcessPipe, ReadPipeIfPossible, LoadComponent 0x001100C2, UnloadComponent 0x00120000, Flush/InvalidateDataCache, RegisterInterruptEvents, GetSemaphoreEventHandle, SetSemaphoreMask, GetHeadphoneStatus (14 en total) |
| `APT:U` | 0x3E2668 | `APT_OpenSession` 0x291A68 | GetLockHandle, Initialize, Enable, GetAppletManInfo, GetAppletInfo, IsRegistered, InquireNotification, Send/Receive/Glance/CancelParameter, PreloadLibraryApplet, PrepareToStart{Library,System}Applet, Start{Library,System}Applet, PrepareToCloseApplication, CloseApplication, PrepareToJumpToHomeMenu, JumpToHomeMenu, CancelLibraryApplet(?), ReplySleepQuery, ReplySleepNotificationComplete, SendCaptureBufferInfo, SleepSystem(?), NotifyToWait, Wrap, Unwrap, AppletUtility (30 en total) |
| `cfg:u` | 0x3E2670 | `CFGU_Initialize` 0x1012C8 | GetConfigInfoBlk2 0x00010082, SecureInfoGetRegion 0x00020000, GenHashConsoleUnique 0x00030040 |
| `ndm:u` | 0x3E259C | `NDMU_Initialize` 0x291F78 | SuspendDaemons, ResumeDaemons, SuspendScheduler, ResumeScheduler, OverrideDefaultDaemons |
| `mic:u` | 0x3F0378 | `MIC_Initialize` 0x1F57A8 | Map/UnmapSharedMem, Start/StopSampling, IsSampling, SetGain/GetGain, SetPower, SetIirFilter, SetClamp |
| `cecd:u` (StreetPass) | 0x3F036C y 0x3F0370 (dos sesiones) | `CECD_Initialize` 0x1F1AB8 | Open, Read, Write, ReadMessage, WriteMessageWithHMAC, Delete, SetData, ReadData, Start, Stop, GetCecdState, GetChangeStateEventHandle (12 por sesión) |
| `err:f` (puerto) | (ConnectToPort) | `ERRF_ThrowFatal` 0x28BC4C (H) | ThrowFatalError 0x00010800 (0x107740) |
| **desconocido** | 0x3E3190 | nadie le escribe en el código: hipótesis de que lo llena otro módulo por puntero (hay un literal en 0x3862A0) | 0x003B0000 y 0x003C0000 (Get u8), 0x00130040 y 0x003D0040 (Set u8). El código que lo usa (0x105AF8 / 0x28D5FC) lee dos banderas antes de dormir, las combina con OR, las pone en 0 y las restaura al despertar. **HIPÓTESIS**: tiene que ver con el sueño/pausa del sistema. No coincide con ningún servicio que conozco de memoria |

Hay cadenas de servicios que aparecen pero que el juego **no** abre por esta vía: `gsp::Lcd`, `hid:SPVR`, `fs:LDR`, `cecd:s` y `srv:pm` (son variantes que vienen en las mismas tablas del SDK). **No aparecen en absoluto** `csnd:SND`, `ptm:u`, `ir:rst`, `cam:u`, `y2r:u`, `ac:u`, `frd:u`, `boss:U`, `news:u` ni `nim:aoc`. Por eso el sonido va **solo por DSP**: el juego no usa CSND.

## Syscalls que no son IPC (wrappers finos confirmados)
| svc | Wrapper | Uso |
|---|---|---|
| 0x01 ControlMemory | 0x29304C | heap |
| 0x03 ExitProcess | 0x29360C | |
| 0x08 CreateThread | 0x1038A0 | hilos del SDK y del juego |
| 0x09 ExitThread | inline en 0x1073FC | |
| 0x0A SleepThread | 0x28BC38 (yield) | |
| 0x0B / 0x0C Get/SetThreadPriority | 0x107404 / inline en 0x2F08AC y 0x2F08CC | |
| 0x13 CreateMutex · 0x14 ReleaseMutex (x26 inline) | 0x10C590 · 0x221CF8 (H) | nn::os::Mutex |
| 0x17 CreateEvent · 0x18/0x19 Signal/ClearEvent (x6 inline cada uno) | 0x291968 | nn::os::Event |
| 0x1E/0x1F/0x20 Create/Map/UnmapMemoryBlock | 0x10C574 / inline | memoria compartida (GSP, HID, MIC) |
| 0x21 CreateAddressArbiter · 0x22 ArbitrateAddress (x47) | 0x101B24 · 0x28BC7C | handle global **0x3E25C4**: sobre él están construidos los CriticalSection/LightEvent del SDK |
| 0x23 CloseHandle (x57) | 0x10C56C | |
| 0x25 WaitSynchronizationN | 0x28EBA0 | **No hay** svc 0x24: toda espera pasa por N |
| 0x27 DuplicateHandle | 0x10C5A8 | |
| 0x28 GetSystemTick (x22) | 0x28B7E8 | reloj del juego |
| 0x2D ConnectToPort | 0x28DC38 | `srv:` y `err:f` |
| 0x35/0x37/0x38/0x3A | 0x28BBBC / 0x28B63C / 0x1008C0 / 0x100760 | ID de proceso/hilo, límites de recursos |
| 0x3C Break | 0x28EC88 | después de cualquier fallo fatal |

## Capa gráfica (GSP + GX + nngx)
- **Cola GX**: `gspSubmitGxCommand` (0x289464) escribe comandos de 0x20 bytes en una cola de 15 entradas en la memoria compartida de GSP. Si la cola estaba vacía, llama `GSPGPU_TriggerCmdReqQueue`. Ya están identificados los cinco comandos: `GX_RequestDma` (id 0), `GX_ProcessCommandList` (id 1, con un id 5 FlushCacheRegions antes), `GX_MemoryFill` (2), `GX_DisplayTransfer` (3) y `GX_TextureCopy` (4).
- **nngx** (la API GL-like de Nintendo): `nngx_RunCmdlistRequests` (0x28C638) recorre las peticiones guardadas en la command list y las despacha a los `GX_*` por medio de los shims 0x10A0D0, 0x10A0EC, 0x10A128 y 0x10A168. `nngxGetCmdlistParameteri` (0x28ECF8, H) lee los parámetros 0x200+.
- **Swap de framebuffers (actualizado 7 oct):** CONFIRMADO que no existe `GSPGPU_SetBufferSwap`. Lo que se sabe:
  - Contexto GSP global **0x0041D1B0**: `+0x5C` = puntero a la info de framebuffer de arriba (`shm+0x200+idx*0x80`), `+0x60` = abajo (`+0x40`). Solo se escriben en la init.
  - **Arranque de pantallas por registros**: `nngx_Initialize` (0x28F9D4) escribe UNA VEZ por `WriteHWRegs` 0x400468/46C (fb arriba A/B), 0x400568/56C (abajo), 0x400470 (formato) y 0x400478/578 (select).
  - **VBlank**: `GSP_SetEventCallback` (0x107B24) registra 7 callbacks; los de VBlank (0x107258 arriba, 0x10729C abajo) solo cuentan frames (`nngx` 0x0041CFA0 +0x154/+0x158) y llaman un callback VSync del juego (+0x15C/+0x160). El swap NO se hace ahi.
  - Las 5 peticiones de nngx (DMA, cmdlist, MemoryFill, DisplayTransfer, TextureCopy) **no** incluyen el swap.
  - **No se encontro quien escribe la info de framebuffer** en shm. Descartado: ldrex/strex junto a +0x5C/+0x60, strb a `[x,#1]` y la forma {cabecera + entradas 0x1C} en GSP/nngx; ldrexh 0x2885BC es un semaforo liviano y 0x10A608 es un asignador de memoria.
  - **Para el port no hace falta encontrarlo**: un GSP falso puede leer la estructura de `shm+0x200` en cada VBlank, igual que el GSP real (asi lo hace Citra). Para confirmarlo en vivo: watchpoint de escritura en `shm+0x200..0x2FF` con el GDB stub de Azahar/Citra.
- **Init**: `GSPGPU_Initialize` (0x107A24) llama a GetServiceHandle, luego AcquireRight, y después a `GSP_InitEventsAndSharedMem`. Este último hace RegisterInterruptRelayQueue y lanza el hilo de eventos (VBlank0/1, PSC, PPF, P3D, DMA).

## Qué tiene que reemplazar el port en PC
1. **Gráficos (lo más grande).** Todo pasa por `gsp::Gpu` y la cola GX. Hay dos caminos:
   - **(a) Nivel GX/PICA**: implementar `gspSubmitGxCommand` + `GSPGPU_*` y emular los command buffers del PICA200 que manda `GX_ProcessCommandList`. Es lo que hace Citra, con el mínimo de puntos de enganche: 5 comandos GX + ~13 IPC.
   - **(b) Nivel nngx/NW4C**: reemplazar las funciones `nngx*` y el render de NW4C por un renderer nativo (GL/Vulkan). Se ve mejor, pero el trabajo es mucho mayor.

   En cualquiera de los dos hay que dar memoria compartida falsa, eventos de VBlank (para el hilo de 0x1095F4) y una implementación de DisplayTransfer (tiling a lineal + presentar ventana). WriteHWRegs/ReadHWRegs pueden ser no-op o un mínimo simulado (registros LCD/PDC).
2. **Controles.** `hid:USER`: el juego solo pide `GetIPCHandles` (memoria compartida + 5 eventos) y lee el estado directo de la memoria compartida (0x2B0 bytes mapeados en 0x1F3AC4). El port tiene que llenar esa estructura (botones, círculo, táctil, acelerómetro y giroscopio) desde teclado/mando. Lo del acelerómetro y giroscopio se puede contestar con valores fijos.
3. **Archivos.** `fs:USER` + sesiones de archivo/directorio. Basta con mapear OpenArchive (RomFS, SaveData, SDMC) y OpenFile/Read/Write/GetSize/Close/CreateFile/Delete sobre carpetas de PC (RomFS = `extraido/romfs`). FormatSaveData, GetFormatInfo y ControlArchive (commit del save) son triviales.
4. **Sonido.** Solo DSP, sin CSND. El juego carga un componente DSP (`DSP_LoadComponent`) y habla por pipes (`WriteProcessPipe`/`ReadPipeIfPossible`) y semáforos. Es el patrón del SDK `nn::snd`. Lo más práctico es enganchar más arriba, en `nn::snd`/el reproductor de BCSAR/BCSTM, y mezclar en PC. La otra opción es HLE del firmware DSP, como hace Citra. `mic:u` puede devolver silencio.
5. **Sistema / ciclo de vida.** `APT:U` (30 comandos: parámetros, sueño, HOME, applets como el teclado y errores) se puede contestar con stubs "todo bien, sin notificaciones". `ndm:u`, `cecd:u` (StreetPass), `cfg:u` (región/idioma vía GetConfigInfoBlk2), `err:f` (pasa a log y abortar) y el servicio desconocido 0x3E3190 pueden ser stubs. Las primitivas del SO (hilos, mutex, eventos, arbiter, tick, memoria) se pasan a std::thread/mutex/condvar y a un reloj de 268 MHz (`GetSystemTick`).
6. **Puntos de enganche mínimos** para un "HLE de servicios": interceptar las 9 funciones `*_Initialize` y los ~139 wrappers IPC listados (o directamente las instrucciones `svc`). Con eso el juego queda aislado del 3DS salvo por la GPU.
