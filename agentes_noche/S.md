# Agente S — servicios del sistema (tanda nocturna)

## Estado
- Inicio: respaldos .antes_S hechos. Leyendo capa de sistema.

## Hito 1 — pedido de audio de la sesión principal (sistema.c) — HECHO
- `sis_correr`: `Sleep(ms)` → `dormir_ns()` con `CreateWaitableTimerExW(..., CREATE_WAITABLE_TIMER_HIGH_RESOLUTION)` (sin winmm; si falla, cae a Sleep). `correr_periodicos`: recupera hasta 8 periodos atrasados; más atrás, resincroniza.
- Medido (30 s): `[audio] muestras=918400` en vblank ~1700 → **~32.400 muestras/s** (99 % de 32.728); 65.600 muestras cada ~120 vblanks. vblanks 1767 en 30 s (~59/s, igual que antes).
- **Sabotaje** (`-DSABOTAJE_SUENO_GRUESO` = Sleep viejo + recuperar 1 solo tick): 262.400 en vblank ~1000 → ~15.700/s (el bug original). Log: `agentes_noche\S\log_audio*.txt`. No hace falta `-lwinmm`.

## Hito 2 — guardado de verdad + APT applets + cecd (fs.c, stubs.c)
- fs.c reescrito en la parte de guardado: cada archive abierto guarda su carpeta. SaveData (4) = `SM3DL_GUARDADO` (marca `.formato.bin`), ExtSaveData (6) / SharedExtSaveData (7) = `.extdata\ALTO_BAJO\`, SystemSaveData (8) = `.sistema\…`. Resolución de rutas con la semántica del PathParser de Horizon (barras, `.`, `..`, caracteres prohibidos, componente intermedio que no es carpeta). Códigos exactos (Azahar file_sys/errors.h): NotFormatted 0xC8A04554 (SaveData sin formatear, Shared inexistente), 0xC8A04478 (ExtSaveData inexistente), 0xC8804478 (SystemSaveData), FileNotFound 0xC8804470, PathNotFound 0xC8804471, InvalidPath 0xE0E046BE, UnsupportedOpenFlags 0xE0C046F8, UnexpectedFileOrDirectory 0xE0C04702, FileAlreadyExists 0xC82044B4, DirAlreadyExists 0xC82044B9, DirNotEmpty 0xC92044F0, WriteBeyondEnd 0xE0E046C1 (extdata tamaño fijo), InvalidOpenFlags 0xC92044E6, handle de archive malo 0xC8804465.
- SharedExtSaveData F000000B se provisiona con `gamecoin.dat` (como el PTM). El juego abre esa archive al arrancar y CREA ahí `CFL_DB.dat` (310.560 B, magia CFOG) y `ubll.lst` (12.000 B). Antes: "OpenArchive 0x7 sin soporte" ×2.
- Nuevos: GetExtDataBlockSize 0x083F, DeleteDirectory(Recursively), FormatSaveData recursivo (respeta `.extdata`), GetFormatInfo de extdata, nombres 8.3 en DirRead.
- Integrados los pedidos de P: `parche_fs_exefs.py` (SelfNCCH tipo 2 = ExeFS "icon") y `parche_cfg_eula.py` (EULA 0x7F7F); Mii estándar de `parche_apt_applets.py` (con `SM3DL_MII_CANCELAR=1` se devuelve "cancelado": probado, el juego vuelve a lanzar el selector 4 veces y no crea archivo).
- APT: un parámetro en vuelo (con destino; Glance/Receive dan handle NUEVO cada vez, el bug que vio P), applets de biblioteca sin pantalla (Request→Response con bloque de memoria; Start→WakeupByExit con buffer: EULA "Agree" aceptada, Mii estándar, el resto eco), Cancel/Preload/PrepareToStart/ParameterPresent 0xC8A0CC02, Wrap/Unwrap reversibles, NotifyToWait/ReplySleep… ok.
- cecd:u/s sobre carpeta `.cecd\CEC\…` (Open/Read/Write/Delete/ReadMessage/WriteMessageWithHMAC/ReadData), GetCecdState=1 (Idle, antes 0). cfg 0x000C0000/0x000C0001/0x00130000 explícitos en cero. mic StartSampling ok.
- Registrados (exheader, el juego no los abre hoy): ptm:u, ac:u, frd:u, gsp::Lcd (+ boss:U, news:u, cam:u, y2r:u, ir:USER, nwm::UDS genéricos).
- **Medido de punta a punta** (guion `P\guiones\g3_hasta_mundo1.txt`, guardado vacío propio): Shared F000000B creada → ExeFS icon → selector de Mii 0x402 → `FormatSaveData: 262144 bytes, 0 carpetas, 1 archivos, duplicado 1` → `GameData.bin` 18.444 B; 3434 vblanks en 60 s. **Persistencia**: una corrida nueva sobre la carpeta `guardado\` (hecha por P con este fs.c) arranca en "Press A to Start" → **archivo A = WORLD 1** sin pasar por bienvenida/StreetPass.
- ⚠️ Con el `raster_gl.c`/`pica.c` actuales de R (14:17-14:21) la pantalla de abajo sale BLANCA y el juego no avanza igual; para separar, `agentes_noche\S\compilar_sinR.py` enlaza `S\sm3dl_S_sinR.exe` con los `.antes_R` del render. Con esos, todo lo de arriba anda.
- prueba_ipc.c (de C): 97/97 sigue verde.

## Hito 3 — arnés `recomp\sistema\prueba_guardado.c` + cierre
- **126/126** (archives inexistentes con su código, F000000B y monedas, extdata de tamaño fijo, FormatSaveData/GetFormatInfo, modos y rutas, carpetas, DirRead 8.3 sin archivos de la capa, borrado, GameData.bin 18.444 B + commit + "reinicio" + relectura byte a byte, APT Enable/Preload/Request→Response/ParameterPresent/Glance+Close+Receive/Mii/EULA, Wrap/Unwrap, cecd). prueba_ipc.c de C: 97/97.
- **Sabotajes, los tres fallan**: `-DSABOTAJE_GUARDADO_CODIGO` (Shared devuelve 0xC8A04478) → 1 fallo; `-DSABOTAJE_APT_HANDLE` (mismo handle en cada Glance/Receive, el bug real de P) → 2; `-DSABOTAJE_FS_OFFSET` → 2.
- El arnés encontró un bug real: cecd Read leía `cmd[1]` DESPUÉS de `ipc_respuesta` (que lo pone en cero) → leía 0 bytes. Arreglado.
- Respuesta al pedido de P: con "cancelado" el juego relanza el selector de Mii 4 veces y NO crea archivo (medido) → se devuelve el Mii estándar de P (con `SM3DL_MII_CANCELAR=1` vuelve el cancelado).
- **Corrida final** (`sm3dl_S.exe` oficial con el render actual, guion `P\guiones\g1_a_cada_2s.txt` = activar StreetPass, guardado vacío, 30 s): 0 "sin soporte", 0 "SIN IMPLEMENTAR", 0 servicios desconocidos; F000000B creada → ExeFS icon ×3 → Mii 0x402 → FormatSaveData; vblanks 1566 (≈52/s: con el raster nuevo de R; sin él 3434 en 60 s ≈57/s); `[audio] muestras=852800` (con sonido: pico 5920).
- Pendiente/limitaciones: teclado (0x401) es eco (no hay texto); sin applets de sistema/HOME; cecd sin ReadMessage real de pases (no hay radio); con `-DSIS_IPC_SEPARADO` stubs.c necesitaría las funciones de fs.c no-static (hoy todo entra por sistema.c).
- Archivos tocados: `recomp\sistema\{fs.c, stubs.c, sistema.c, DISENO.md, svcs.md}` (respaldos `.antes_S`), nuevo `recomp\sistema\prueba_guardado.c`; todo lo demás en `agentes_noche\S\`.
- Pedidos de integración: ninguno (no hizo falta tocar compilar.py ni enchufes.c; ni `-lwinmm`).
