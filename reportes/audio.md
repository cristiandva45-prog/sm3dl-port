# Audio — ruta del DSP y diseño del mezclador HLE (agente G, 7 oct 2026)

> Estado: **incompleto por cierre de sesión**. Hecho: ruta del firmware, protocolo de pipes, capa del driver. Falta: bucle por frame de nn::snd, `tools\audio_bcstm.py` y censo del bcsar (ver "Lo que falta").

## Herramientas nuevas
- `tools\audio_censo_code.py`: busca el magic `DSP1` y cadenas de sonido en `code.bin`.
- `tools\audio_llamadores.py [0xDIR ...]`: quién llama (bl) o carga como literal una dirección (sin args: los `DSP_*` de `simbolos.txt`).
- `tools\audio_dis.py 0xINI 0xFIN`: desensambla con nombres y resuelve literales.

## 1. Firmware DSP: EMBEBIDO en code.bin (no hay .cdc en el RomFS)
- Componente en **`.data` 0x003E31B0**, tamaño **0xBE44** (48.708 B); magic `DSP1` en 0x003E32B0 (= +0x100, tras la firma RSA, formato estándar de `dspaudio.cdc`). CONFIRMADO.
- Lo carga **`0x1F2D8C`** (propuesta: `DspFirm_Load`): guarda puntero/tamaño en el estado global del DSP (`0x3E2674`: +8 handle, +0xC máscara de interrupciones registradas, +0x18 puntero firmware, +0x1C tamaño) y llama `DSP_LoadComponent(fw, 0xBE44, prog_mask=0xFF, data_mask=0xFF, &loaded@0x3E2675)`. Si no hay handle devuelve `0xC8A0A7FC`.
- Para el port: **no se ejecuta el firmware** (HLE, como Azahar, que lo ignora salvo para un hash de log). `LoadComponent` responde "cargado = 1".

## 2. Comandos dsp::DSP y capas
Wrappers IPC (ya en `simbolos.txt`): RecvData 0x1F323C, RecvDataIsReady 0x1F2FEC, SetSemaphore 0x1F2F7C, ConvertProcessAddressFromDspDram 0x1F31FC, WriteProcessPipe 0x1F306C, ReadPipeIfPossible 0x1F30E8, LoadComponent 0x28BBD4, UnloadComponent 0x28A8D4, FlushDataCache 0x1F2FB4, InvalidateDataCache 0x1F3158, RegisterInterruptEvents 0x1F31C4, GetSemaphoreEventHandle 0x1F3190, SetSemaphoreMask 0x1F3034, GetHeadphoneStatus 0x1F30B0.

Capa fina con chequeo "inicializado" (error `0xC8A0A7F8` si no hay handle) — propuestas de nombre:
| Dir | Propuesta | Hace |
|---|---|---|
| 0x23ABC4 | `dsp_ConvertAddr` | ConvertProcessAddressFromDspDram |
| 0x23AC00 | `dsp_ReadPipe` | ReadPipeIfPossible(canal, peer 0, buf, len, &leidos) |
| 0x23AC50 | `dsp_SetSemaphore` | tail-call a SetSemaphore |
| 0x23AC7C | `dsp_WritePipe` | tail-call a WriteProcessPipe |
| 0x23ACC0 | `dsp_RegisterInterrupt` | registra/desregistra y lleva la máscara en 0x3E2674+0xC |

Driver de nn::snd (objeto `drv`, propuestas):
- **`0x1F8310` `SndDsp_Open`**: `svcCreateEvent` → `RegisterInterruptEvents(evento, tipo=2 (pipe), canal=2 (audio))`. Ese evento es el **tick de audio**.
- **`0x1F8BD0` `SndDsp_Initialize(drv, despertar)`**: escribe 4 bytes al pipe 2 con estado **0 = Initialize** (o **2 = Wakeup**, restaurando antes 0x1080 bytes guardados); `SetSemaphore(0x4000)`; lee del pipe 2 un u16 N y N direcciones DSP (palabras de 16 bits); convierte cada una dos veces (`addr` → región 0, `addr|0x10000` → región 1) y guarda pares de punteros. Luego arma, para las **24 fuentes (0x18)**, punteros con pasos **0xC0** (SourceConfiguration, 192 B), **12** (SourceStatus) y **0x20** (coeficientes ADPCM) en cada región; mezclas intermedias en `drv+0x12F0..` (+0xA00 = segunda mitad). Pone `frame_counter = 4` en la región de escritura (`drv+0x131A` lleva la cuenta), `SetSemaphore(0x4000)` y `svcSignalEvent`.
- **`0x1F9444` `SndDsp_Finalize(drv, dormir)`**: pipe 2 con estado **1 = Shutdown** o **3 = Sleep**; espera con `RecvData` (0x1F2CE8/0x1F32E4, sleep 1 ms entre intentos) a que el DSP conteste 1; guarda 0x1080 bytes si duerme; desregistra la interrupción y cierra eventos.
- **Coincide byte a byte con el layout de Azahar** (`src\audio_core\hle\shared_memory.h`): el juego usa el firmware estándar, no uno propio.

### Memoria compartida (resumen del layout, verificado contra los pasos del driver)
DSP RAM del proceso en 0x1FF00000 (512 KB); `ConvertProcessAddressFromDspDram(a) = (a << 1) + 0x1FF40000`. Dos regiones de 0x8000 B en **+0x50000 y +0x70000** (doble buffer). Cada región: DspStatus, FinalMixSamples (160×2 s16), SourceStatus[24]×12, Compressor, DspConfiguration (196 B: volumen maestro, aux, formato de salida, delay/reverb), IntermediateMixSamples (2×4×160 s32), SourceConfiguration[24]×192, AdpcmCoefficients[24]×16 s16, …, `frame_counter` u16 al final. Los u32 del DSP van **"middle-endian"** (mitades de 16 bits intercambiadas); los float y las muestras intermedias, little-endian normales.
SourceConfiguration por fuente: palabra de bits *dirty*, gain[3][4] (3 mezclas × 4 canales), rate_multiplier, interpolación, filtros simple/biquad, cola de 4 buffers {dirección física, largo, estado ADPCM, loop, id}, enable, sync_count, play_position, buffer embebido {dirección, largo, formato PCM8/PCM16/ADPCM, mono/estéreo, ADPCM ps/yn, loop, id}.

## 3. Diseño del mezclador HLE para el port
1. **Servicio `dsp::DSP` falso** (en la capa de sistema): LoadComponent → ok y "cargado"; RegisterInterruptEvents → guardar el evento por (tipo, canal); WriteProcessPipe canal 2 → máquina de estados (0/2: escribir en la cola de lectura del pipe 2 el u16 15 + las 15 direcciones de estructura = `0x8000 + offset/2` de cada estructura, y señalar el evento del pipe 2; 1/3: apagar/dormir y que `RecvData(0)` devuelva 1); ReadPipeIfPossible → sirve esa cola; ConvertProcessAddressFromDspDram → fórmula de arriba; Flush/Invalidate/SetSemaphore/SetSemaphoreMask → ok; GetHeadphoneStatus → 0.
2. **Memoria**: mapear 512 KB de DSP RAM en 0x1FF00000 del guest (lo pide la capa de sistema de D).
3. **Tick cada 160 muestras a 32.728 Hz (~4,889 ms)**, en un hilo de audio del anfitrión: elegir región de lectura = la de `frame_counter` mayor (con los casos 0xFFFF/0xFFFE de Azahar); por cada fuente procesar *dirty bits* → avanzar la cola de buffers, decodificar PCM8/PCM16/DSP-ADPCM desde la memoria física del guest, re-muestrear (rate_multiplier, interpolación lineal primero), aplicar gain a las 3 mezclas; mezclar con DspConfiguration (volumen maestro, aux; reverb/delay después); escribir SourceStatus y la mezcla final en la **otra** región; señalar el evento del pipe 2. Es el despertador del hilo de sonido del juego (en la capa de fibras: un evento señalado desde fuera de las fibras → el planificador lo atiende en el próximo cambio).
4. **Salida PC**: SDL2 (ya trae re-muestreo y es simple) o WASAPI directo; 32.728 → 48.000 Hz en el anfitrión, cola de 2–4 frames para no cortar.
5. Alternativa descartada por ahora: enganchar `nn::snd`/el reproductor BCSAR más arriba. El HLE del DSP es más chico (una sola interfaz, ya documentada) y no depende de entender la librería.

## Lo que falta (ordenado)
1. Ubicar el **bucle por frame** de nn::snd (hilo que espera el evento de 0x1F8310, escribe las SourceConfiguration y sube `drv+0x131A`) y la función que llena los parámetros de cada voz (formato, tasa, volúmenes, loop). Pista: el bloque 0x1F5F00–0x1FA400 tiene WaitSynchronizationN (svc 0x25?) y ArbitrateAddress (0x22); las cadenas útiles son pocas (`SoundHeap` 0x38C498, `rom:/SoundData/RedPepperSound.bcsar` 0x3DB0B5).
2. **`tools\audio_bcstm.py`** (CSTM: bloques INFO/SEEK/DATA, DSP-ADPCM con 16 coeficientes por canal, frames de 8 bytes/14 muestras, loop) — **HECHO al cierre**: `tools\audio_bcstm.py` decodifica a WAV (`recomp\audio\wav\`, uso personal). Verificado en 2 pistas: BEACH = ADPCM, **6 canales** (3 pares estéreo: capas de la música dinámica), 32.000 Hz, 64,9 s, loop [315392, 2078008); ATHLETIC = 4 canales, 44,4 s, loop [344064, 1421960). El fin del loop coincide con el total de muestras. Señal tonal, no ruido: rms_diff/rms = 0,15 y 0,27 (ruido blanco ≈ 1,41). Falta: escucharlas, y probar pistas de 2 canales y las `_FAST`.
3. Censo de `RedPepperSound.bcsar` (15 MB): cantidad de sonidos, ondas (CWAV/CWAR) y formatos.
4. Implementar en C el servicio falso + el mezclador (`recomp\audio\`), probándolo primero con un bcstm decodificado inyectado como fuente.

---
## Agente H (8 oct 2026): DSP HLE implementado y probado

**Archivos** (`recomp\audio\`): `dsp.h/.c` (servicio + región compartida + mezclador), `audio_salida.h/.c` (cola, 48 kHz, backends WASAPI/SDL2 por `#define`), `prueba_dsp.c`, `prueba_salida.c`, `probar.py` (todo en un comando: `py -I recomp\audio\probar.py`). Herramienta: `tools\audio_vector.py` (escenario con bcstm reales + mezclador de referencia en Python puro, float32 emulado). Compilar con `-ffp-contract=off` (sin eso clang fusiona mul+add y la mezcla float no es reproducible).

**Qué hace `dsp.c`**: 24 fuentes con ParseConfig por bits *dirty*, cola de buffers por `buffer_id`, buffer embebido y cola de 4, PCM8 / PCM16 / DSP-ADPCM (mono) con coeficientes y estado `yn`, bucles (re-encola el buffer), interpolación lineal o ninguna (Polyphase = lineal, como Azahar), filtros simple y biquad, rampa de ganancia de 1 frame al cambiar gain, 3 mezclas intermedias x 4 canales, aux bus 0/1 (lee/escribe `IntermediateMixSamples`), volumen maestro/aux, salida mono/estéreo, SourceStatus (buffer id, last id, posición, sync), FinalMixSamples, elección de región por `frame_counter` (casos 0xFFFF/0xFFFE), pipe 2 con Initialize/Shutdown/Wakeup/Sleep y las 15 direcciones, RecvData (0 encendido, 1 apagado). `dsp_hilo_iniciar()` (con `-DDSP_HILO_WIN32`) tickea a 32.728/160 Hz con QPC.
**No implementado**: delay y reverb (Azahar tampoco hace reverb), ADPCM estéreo, pipe Binary (decodificador AAC: devuelve error), actualización parcial de buffer PCM8/ADPCM, `loop_related`.

**Verificación** (`probar.py`): escenario con 3 fuentes reales: (0) ADPCM de BEACH canal 0, 2 buffers en cola (el 2.º continúa el estado `yn`), rate 32000/32728, cambio de gain con rampa en el tick 60; (1) PCM16 estéreo en bucle de ATHLETIC; (2) PCM8 sin interpolación a rate 0,5, buffer embebido. 220 ticks, 70.400 muestras: **0 diferencias** contra la referencia (rms 2872: no es silencio). La referencia es independiente (flujo continuo, decodifica con `audio_bcstm.py`, no con el código C).
Sabotajes vistos fallar: (a) predictor del frame 3 alterado en la memoria del guest: 100 muestras distintas, error máx 2756; (b) referencia con floor en vez de ceil para delta negativo (el original hace la cuenta en u64 con delta con signo: `x0 + fr*d/2^24` da `-ceil`, no `-floor`): 19.394 muestras distintas, error ±2. Ese redondeo está reproducido a propósito.
Rendimiento: 0,01 ms por tick con 3 fuentes (presupuesto 4,889 ms). En vivo (`prueba_salida.exe`, hilo real + WASAPI): inicializa (rc 0), 202,6 ticks/s (esperado 204,5), 0 descartes de cola. No se escuchó, solo se midió.

**Pedido de integración (capa de sistema, agente C).** Servicio `dsp::DSP` = comando IPC -> estas funciones (nombres del SDK, ya en `dsp.h`):
`LoadComponent(size,pm,dm,&cargado)`, `UnloadComponent`, `GetSemaphoreEventHandle` (la capa crea el evento y llama `dsp_poner_evento_semaforo(h)`), `RegisterInterruptEvents(handle,tipo,canal)`, `WriteProcessPipe(canal,buf,len)`, `ReadPipeIfPossible(canal,peer,buf,len,&leidos)`, `ConvertProcessAddressFromDspDram(a)`, `FlushDataCache`/`InvalidateDataCache` (no-op), `SetSemaphore`/`SetSemaphoreMask` (no-op), `RecvData(0)`/`RecvDataIsReady`, `GetHeadphoneStatus`. Además: (1) mapear `dsp_ram()` (512 KB) en 0x1FF00000 del guest; (2) pasar `dsp_host_t.fis(paddr,n)` = traducción física a host (FCRAM 0x20000000 <-> heap lineal 0x14000000) y `senal(handle)` = SignalEvent del evento registrado; (3) llamar `dsp_hilo_iniciar()` al primer Initialize, o `dsp_tick()` desde el planificador cada 4,889 ms; el tick señala el evento del pipe 2 (despertador del hilo de sonido del juego); (4) definir `AUDIO_BACKEND_WASAPI` y enlazar `-lole32`. Hay una `CRITICAL_SECTION` solo con `DSP_HILO_WIN32`; el juego escribe la RAM del DSP sin bloqueo, igual que en hardware.

### Estático del bucle por frame de nn::snd (parcial)
- `0x1F5F88` = **nn::snd::Initialize**: `srvInit`, `SndDsp_Open(0x1F8310, drv=0x426B54)`, crea subsistemas (`0x1F638C` con el motor `0x427EE8`, `0x1F67B8`, `0x1F787C`) y registra hooks (`0x1F2EB8` con 0x1F8088 / 0x1F98F0 / 0x1F803C).
- **`0x1F86D4` = actualización por frame** (propuesta `SndDsp_FrameTick(drv)`): si el DSP está vivo, lee el `frame_counter` de la región que el DSP acaba de escribir (punteros guardados en `drv+0x1098+4*idx`), y si es distinto de 0 incrementa `drv+0x131A` (si da 0 salta a 2) y elige el buffer `drv+0x131C = contador & 1`. Luego, **para las 24 fuentes**, llama `0x1FACA8(motor 0x427EE8, i, ptr)` con la `SourceConfiguration` preparada en `drv+0x1170+...` (vuelca los parámetros de cada voz a la región compartida), después `0x28F08C(motor, drv+0x1310)` (DspConfiguration/mezcla) y `0x1F6D9C(..., 0xA0 bytes)` (callback de usuario) y termina con tail-call a `0x1F6B24`. Coincide con mi driver de prueba: el juego sube el contador de la región de escritura y el DSP lee la de contador mayor.
- `0x1F95EC` es un lock recursivo (ldrex/strex con el TLS como dueño), no parte del audio. El bucle del hilo está en `0x1F711C` (espera por evento y llama a `0x1F7580`/`0x1F7660`, que invocan `0x1F86D4` bajo ese lock). Estos nombres son hipótesis desde el desensamblado; no se verificaron en ejecución.
- Pendiente: leer `0x1FACA8` (qué dirty bits usa el juego por voz) y de dónde salen los PCM (bcsar/bcwav/bcstm vía `RedPepperSound`).
