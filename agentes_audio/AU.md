# AU — bitácora audio (9 oct)
- arranque: leer BRIEF, ESTADO, recomp/audio
- Leído: dsp.c (DSP HLE) y audio_salida.c (cola 32.728 -> 48 kHz lineal -> WASAPI). Comparado contra azahar-src:
  ADPCM, interpolación lineal (Polyphase=lineal), rampa de ganancias, mezcla final mono/estéreo, offsets de
  DspConfiguration: IGUALES. Azahar tampoco implementa compresor/limitador ("clipping_mode": TODO) -> el recorte a
  ±32768 también lo tendría Azahar. El DSP no es el sospechoso principal.
- Sospechoso principal: la SALIDA (audio_salida.c), que no tiene nada de lo que Azahar sí tiene (FIFO + estirado/
  cubeb con remuestreo bueno):
  1. WASAPI se llena ENTERO (búfer de 200 ms) en cada vuelta -> el audio va ~200 ms ATRASADO respecto a la imagen.
  2. Sin colchón ni control de ritmo: la cola vive casi vacía; cada vez que el DSP llega tarde (ticks en ráfaga
     del planificador, hasta 8) se "sostiene" la última muestra (tramo plano = clic) en medio del bloque.
  3. `vacia=` solo cuenta si la cola está vacía AL EMPEZAR el bloque -> los huecos a mitad de bloque no se ven
     (por eso el log dice 0 huecos en juego).
  4. Hilo WASAPI con Sleep(5) sin timeBeginPeriod = ~15,6 ms por vuelta.
- Log sesion_juego/jugar: ritmo del DSP vs vblanks 0,999 (con caídas 0,5-0,9 en cargas = ticks perdidos);
  descartes=0 -> el DSP nunca va más rápido que la salida -> la cola siempre al borde.
- Respaldos: recomp/audio/audio_salida.c.antes_AU, audio_salida.h.antes_AU

## Arreglo (recomp/audio/audio_salida.c + .h) — por defecto; `SM3DL_AUDIO_VIEJO=1` = salida anterior tal cual
- WASAPI se llena solo hasta 30 ms (`SM3DL_AUDIO_PAD_MS`), hilo con temporizador de alta resolución de 2 ms
  (antes Sleep(5) ≈ 15,6 ms) y prioridad TIME_CRITICAL.
- Cola con colchón objetivo 40 ms (`SM3DL_AUDIO_COLA_MS`), cebado al arrancar (y a la mitad tras quedarse sin datos).
- Control de ritmo: paso del remuestreo ±0,8 % máx. según el nivel filtrado (~0,5 s) de la cola -> absorbe la deriva
  DSP vs placa en vez de sostener/descartar muestras. Desborde grande -> un solo salto (`saltos=`).
- Diagnóstico nuevo al final de la línea `[audio]`: `huecos=` (TODAS las muestras de 48 kHz sostenidas en esos ~2 s),
  `cola=` ms, `ajuste=` ppm, `recortes=` (muestras del DSP en ±32767/-32768: dirá si la saturación es real).
- DSP (dsp.c) SIN tocar.

## Pruebas (sin correr el juego)
- `py -I agentes_audio\probar_salida.py` -> TODO VERDE. Simulador `sim_salida.c` (reloj virtual: DSP 0,1 % lento,
  hilo del juego ocupado 5-25 ms por cuadro de 33 ms, ticks en ráfaga de hasta 8 como sistema.c), seno 1 kHz, 60 s:
  - VIEJO:    68 clics, 79 ms sostenidos, latencia 200 ms (muestra el bug).
  - NUEVO:    0 clics, solo los 42 ms del cebado inicial, latencia media 63 ms (máx 72).
  - SABOTAJE (`SM3DL_AUDIO_SABOTAJE=1`, sin control de ritmo): 61 clics -> la prueba FALLA como debe.
  - Escenario "rapido" (DSP 0,1 % rápido): nuevo 0 clics, 77 ms; sin control la cola sube sin fin (71 ms y creciendo).
  - Escenario "pesado" (paradas de 70 ms cada 3 s): ambos con huecos: son TICKS PERDIDOS por el planificador
    (más de 8 atrasados -> se resincroniza y ese audio no existe). No es de audio_salida: ver pedido abajo.
- `py -I recomp\audio\probar.py` (DSP vs referencia) sigue TODO VERDE (sabotaje del predictor visto).
- `sm3dl_AU.exe` enlazado con `compilar.py -o` (contiene "con colchon" y las variables nuevas).
- WAV para escuchar (BEACH, 30 s, escenario normal): `ANTES_salida_vieja_BEACH.wav` / `DESPUES_salida_nueva_BEACH.wav`
  (en el viejo los huecos son de ~1 ms: se oyen como crujidos finos; el retardo de 200 ms solo se nota jugando).

## Prueba pendiente con el juego (la corre el dueño; desde la raíz, cmd)
    set SM3DL_SIN_TRAZA=1 & set SM3DL_GUARDADO=sesion_juego\jugar\guardado & agentes_audio\sm3dl_AU.exe 2> agentes_audio\log_AU.txt
  A/B: lo mismo con `set SM3DL_AUDIO_VIEJO=1` antes (log a log_AU_viejo.txt). Mirar en el log: `huecos=` ~0 en juego,
  `cola=` ~30-45 ms, `ajuste=` dentro de ±8000 ppm, y `recortes=` (si es alto con música+efectos, la saturación es real).
  Preguntarle: ¿los saltos/efectos suenan ahora a tiempo con la imagen? ¿se fueron los crujidos?

## Pedido de integración (no es mío: recomp/sistema/sistema.c, correr_periodicos)
- Más de 8 ticks atrasados se tiran (`prox = t + periodo`): para el DSP eso es audio que no existe (en el log de
  sesion_juego/jugar se ven tramos al 50-90 % en cargas). Propuesta: para el período del DSP recuperar hasta 20 (~100 ms)
  o, mejor, hasta lo que haga falta si el atraso < 150 ms. Riesgo: ráfaga de trabajo del DSP (0,005 ms/tick: nada).

## Descartado / sin cambio
- dsp.c contra Azahar: ADPCM, interpolación, rampas, mezcla final, layout: iguales. Estéreo no invertido (L=mix[0]+mix[2]).
- Saturación: Azahar tampoco tiene limitador (clipping_mode sin implementar). Sin datos del juego no se puede medir
  offline: queda el contador `recortes=`. Si sale alto, la idea siguiente es un limitador suave detrás de variable.
- Remuestreo lineal 32.728->48.000: atenúa ~1,3 dB a 10 kHz y algo de imagen >18 kHz; menor, no lo cambié.
