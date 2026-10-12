# Brief común — tanda "4x a 60 FPS" (7 oct noche, 2 agentes: A y B)

## Objetivo del dueño
Resolución interna **4x** (`SM3DL_RESOLUCION=4`) corriendo a **60 FPS fluidos**. Hoy: 1x ~57 cuadros/s, 4x ~25 cuadros/s.

## Contexto que ya está resuelto (no re-derivar)
- Todo el juego corre en **UN hilo del SO** (fibras). Lo que la presentación o el raster gasten en ese hilo se lo quita al juego.
- Síntoma de asfixia: en `[gsp-est]` los `vblanks`/`presentaciones` avanzan pero `listas`/`swaps` no.
- **Métrica principal: `swaps` por `vblank`** entre dos líneas `[gsp-est]` del régimen estable (después del vblank ~1500 con el guion de abajo). 60 FPS ≈ **1,9–2,0 swaps/vblank** (el juego hace 2 swaps por cuadro: arriba y abajo). Hoy 1x ≈ 1,92; 4x ≈ 0,83.
- Ya arreglado: `raster_alta` (raster_gl.c) gira la pantalla en alta con un shader y no rehace cuadros repetidos. Verificador en proceso: `SM3DL_ALTA_VERIFICAR=1` (=2 sabotea un byte). Detalle en `ESTADO.md`, sección "Resolución interna injugable → arreglada".
- Contadores del raster (`[raster] tramos`): por dibujo y por transferencia cuestan IGUAL a 1x que a 4x. Lo que crece a 4x está en lo NO medido: trabajo de GPU / esperas de sincronización (A) y presentación por GDI (B).

## Cómo correr una prueba (siempre así)
Desde la RAÍZ del port (`C:\Users\usuario\Desktop\Decopilar\sm3dl-port`; si no, "no abre extraido\code.bin"):
```
SM3DL_SIN_TRAZA=1  SM3DL_VENTANA_OCULTA=1  SM3DL_TURBO=3  SM3DL_SEGUNDOS=45
SM3DL_GUION=sesion_juego\j8\partida.txt      (llega al 1-1 con Mario)
SM3DL_GUARDADO=<TU carpeta>\guardado          (copia NUEVA de sesion_juego\j8\guardado en cada corrida)
SM3DL_RESOLUCION=1 | 4
```
- En PowerShell: `Start-Process ... -WorkingDirectory <raíz> -RedirectStandardError <tu carpeta>\log.txt -PassThru -NoNewWindow`, después `$p.PriorityClass='BelowNormal'` y `WaitForExit`. **El dueño está usando el PC**: una corrida a la vez, nunca en ráfaga, nunca sin `SM3DL_TURBO=3`.
- **Compila TU exe**: `py -I recomp\arranque\compilar.py -o sm3dl_A.exe` (o `sm3dl_B.exe`). **NUNCA** escribas `sm3dl.exe`: es el del dueño.
- Compilar enlaza TODO, también los archivos del otro agente. Deja tus archivos **compilando entre una edición y la siguiente** (cambios pequeños y atómicos). Si falla por un archivo del otro, espera un minuto y reintenta.
- Los dos agentes corren pruebas a la vez y se roban CPU. **Compara siempre 1x contra 4x en corridas seguidas tuyas**, y prefiere los cronómetros dentro del proceso (ms por cuadro de tu sección) a los totales.

## Reglas
- **Dueño exclusivo de archivos.** A: `recomp\render\raster_gl.c` (+ `raster_gl.h`). B: `recomp\render\ventana.c`, `recomp\render\ventana_hud.c` (+ `ventana.h`). No toques los del otro. Si necesitas algo del otro lado, escríbelo en tu bitácora como "PEDIDO a A/B" y sigue con otra cosa.
- Antes de editar, copia `<archivo>.antes_<A|B>` (una sola vez).
- **Bitácora obligatoria**: `agentes_7oct\<A|B>.md`, actualizada tras cada paso (qué mediste, qué cambiaste, números). Si te cortan, se retoma desde ahí.
- **Verificación**: todo cambio que toque lo que se ve tiene que demostrar que la imagen sigue IGUAL, comparando **dentro del mismo proceso** (las corridas no son deterministas: las capturas entre corridas no sirven). Y el verificador nuevo hay que **verlo FALLAR con un sabotaje**. 🩹 Esta noche, una versión daba la pantalla negra y "medía" más rápido: medir sin verificar la imagen puede estar midiendo negro.
- Cambios con interruptor: `SM3DL_<ALGO>=0` vuelve al camino viejo, para comparar.
- 🪛 Gotchas de este PC: en la herramienta Bash los heredoc colapsan `\\` (un `\\0` llega como NUL) → escribe los scripts con la herramienta Write. `py -I` no trae numpy (usa Python puro). Nunca mates procesos por nombre: solo el PID que lanzaste tú.
- No toques `ESTADO.md` ni la memoria: eso lo consolida el coordinador.
- Tiempo: ~45 min. Al terminar, deja compilando + bitácora al día. Entrega un informe corto: medido antes/después (swaps/vblank a 4x y 1x), qué cambiaste (archivo:función), cómo se verificó y qué falta para llegar a 60.
