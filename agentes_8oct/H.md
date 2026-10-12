# Bitácora agente H (audio), 8 oct 2026
Estado: terminado (tareas 1, 2, 3 y parte de 4). Informe técnico completo en `reportes\audio.md`, sección "Agente H".

## Hecho
- `recomp\audio\dsp.c/.h`: dsp::DSP HLE enchufable (servicio, pipes, región compartida de 512 KB, 24 fuentes, mezclador, tick de 160 muestras). Hilo del anfitrión opcional (`-DDSP_HILO_WIN32`).
- `recomp\audio\audio_salida.c/.h`: `audio_salida(int16_t*, n)`, cola, resampleo lineal 32.728 a 48.000, backend WASAPI (`-DAUDIO_BACKEND_WASAPI`: compila y abre el dispositivo, rc 0) o SDL2 (`-DAUDIO_BACKEND_SDL2`: escrito, NO compilado ni probado, SDL2 no está instalado).
- `tools\audio_vector.py` + `recomp\audio\prueba_dsp.c` + `recomp\audio\probar.py`: prueba contra referencia independiente. `recomp\audio\prueba_salida.c`: prueba en vivo.

## Cifras
- 220 ticks, 70.400 muestras, 3 fuentes reales (ADPCM BEACH 2 buffers con rampa de gain, PCM16 estéreo en bucle ATHLETIC, PCM8): 0 diferencias.
- Sabotaje predictor ADPCM: 100 muestras difieren (max 2756). Sabotaje de redondeo (floor vs ceil en delta negativo): 19.394 difieren. Ambos fallan como deben.
- 0,01 ms/tick (presupuesto 4,889 ms). En vivo: 202,6 ticks/s, 0 descartes.

## Descubrimientos
- El interpolador lineal del original opera en u64 con delta con signo: con delta negativo da `x0 - ceil(...)`. Reproducido a propósito (la referencia con floor falla).
- clang fusiona mul+add: hay que compilar con `-ffp-contract=off` para que la mezcla float coincida bit a bit.
- `py` sin `-I` rompe `tools\audio_*.py` (tools\dis.py tapa `dis` y capstone no importa). Usar `py -I`.
- numpy no está instalado en `py`: la referencia usa float32 emulado con `struct`.
- La herramienta Bash falló con heredocs largos que traen comillas simples (EOF); se usó Write.

## Pendientes
- Delay y reverb, ADPCM estéreo, pipe Binary (AAC), SDL2 sin probar, escuchar el WASAPI (solo se midió el ritmo).
- Leer `0x1FACA8` (qué dirty bits usa el juego por voz) y el censo del bcsar.

## Pedido de integración
Ver `reportes\audio.md` ("Pedido de integración"): mapear `dsp_ram()` en 0x1FF00000, `dsp_host_t.fis/senal`, tabla de servicio dsp::DSP a funciones `dsp_*`, `dsp_hilo_iniciar()` o `dsp_tick()` cada 4,889 ms, enlazar `-lole32` y definir `AUDIO_BACKEND_WASAPI`.
No toqué `recomp\sistema\sistema.h`.
