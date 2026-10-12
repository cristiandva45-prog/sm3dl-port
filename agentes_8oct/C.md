# Agente C — capa IPC HLE (bitácora, 8 oct 2026)

## Resultado
- `prueba_ipc.c`: **OK 97/97** (solo sistema) y **OK 99/99** con hid (D) + gsp (E) + pica (F) + dsp (H) enchufados. EffectData.szs (332.440 B) leído por IPC desde la ROM = extraido\romfs, 0 diferencias.
- Sabotajes: `-DSABOTAJE_FS_OFFSET` → 4 fallos; `-DSABOTAJE_DESC_MAPEADO` → 11 fallos; `-DSABOTAJE_PID` → 1 fallo. `prueba_fibras` sigue OK. `sistema.c` + `main.c` del arranque compilan (no enlacé sm3dl.exe: compilar.py no es mío).

## Archivos (recomp\sistema\)
- `sistema.h`: PUNTO DE ENCHUFE (IpcPeticion/IpcSesion/IpcDesc, `ipc_registrar`, `ipc_registrar_crudo(nombre, f(ctx,cmd,sesion), ctx)`, ayudas de respuesta, objetos de kernel para servicios, `sis_periodico`, `sis_hid_preparar`/`sis_senal_hid`, `sis_fisica_a_host`, `sis_ticks`, `fs_configurar`).
- `sistema.c`: Obj sesión → `IpcSesion*`; ConnectToPort/SendSyncRequest → ipc; API de objetos; eventos periódicos en el planificador; `sis_iniciar` registra base + enchufes; incluye ipc.c/srv.c/stubs.c/fs.c/enchufes.c (unidad única; `-DSIS_IPC_SEPARADO` para compilarlos aparte).
- `ipc.c` (despachador + tabla), `srv.c` (srv:, err:f), `stubs.c` (APT:U, cfg:u, dsp, ndm, mic, cecd:u/s, hid/gsp provisionales), `fs.c` (fs:USER real), `enchufes.c` (D/E/F/H), `prueba_ipc.c`, `DISENO.md` §5 actualizado.

## Hallazgos
- RomFS: el SDK abre la IMAGEN nivel 3 (SelfNCCH, ruta binaria tipo 0) y la parsea él mismo → se sirve desde la ROM descifrada (`..\Super Mario 3D Land USA.3ds`, offset NCCH romfs + 0x1000; variable SM3DL_ROM). extraido\romfs solo sirve de referencia.
- Bugs viejos corregidos: GetServiceHandle respondía cmd[2]=0 (debe ser MoveHandleDesc 0x10); RegisterInterruptRelayQueue con cabecera 0x00130042 (es 0x00130082) y sin guardar el evento.
- Bug propio cazado por la prueba: OpenDirectory leía el archive después de que `ipc_respuesta` pusiera cmd[1..] en cero.
- APT: tras Enable se encola "despertar" (remitente 0x101, señal 1) y se señala el evento de parámetro (como Horizon); el censo de J sugería "sin parámetros" — si el juego se cuelga esperando, revisar aquí.
- ptm:u quitado (el juego no lo usa). Handle 0 (servicio 0x3E3190) → 0xD8E007F7, sin romper.

## Pendientes
- dsp provisional (sin -DSIS_CON_DSP) no entrega la tabla de direcciones del pipe 2: el audio real necesita el de H.
- `sis_periodico` no tiene prueba propia con fibras (sí se ejercitan los adaptadores). Riesgo: un hilo que no hace svc nunca devuelve el control y no corre el VBlank.
- `presentar` de gsp = NULL (falta ventana). Guardado: ControlArchive no hace nada (se escribe directo).

## Pedidos de integración
1. `recomp\arranque\compilar.py`: agregar `-DSIS_CON_HID -DSIS_CON_GSP -DSIS_CON_PICA -DSIS_CON_DSP -DAUDIO_BACKEND_WASAPI` y los fuentes `recomp\hid\hid.c servicio_hid.c`, `recomp\gpu\gsp.c`, `recomp\render\pica.c pica_dibujar.c texturas.c`, `recomp\audio\dsp.c audio_salida.c`, más `-lxinput1_4 -lole32` (ya usa -ffp-contract=off). Comando probado: ver encabezado de prueba_ipc.c y esta bitácora.
2. `main.c`: nada obligatorio; opcional `fs_configurar(rom, carpeta)` si la ROM no está en la ruta por defecto.
