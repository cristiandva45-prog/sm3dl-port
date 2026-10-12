# Agente P (progreso) — bitácora

- Inicio: leído brief y ESTADO.md. Plan: guion de entrada, capturas, avanzar.

## Hito 1 — guion + capturas PNG (hecho)
- `SM3DL_GUION=<archivo>` (hid.c: `hid_guion_cargar/aplicar`; enchufes.c `hid_periodico` lo suma con el vblank de gsp). Formato `<vblank> <botones>[+..] [dur=6]`, `TOQUE x y [dur]`, `STICK x y [dur]`, `CARRIBA..` (circle pad), `#` comentario. Funciona sin foco (va despues del filtro de teclado).
- `SM3DL_CAPTURAS=<carpeta>` + `SM3DL_CAPTURA_CADA=<n>`: PNG 400x480 (las dos pantallas) `v<vblank>.png` sin zlib (deflate stored). Sin la variable: PPM de siempre.
- `agentes_noche\P\hoja.py <carpeta>`: hoja de contactos con el vblank en cada miniatura + cambios por hash.
- Build de diagnostico `agentes_noche\P\compilar_diag.py [--exefs] [--eula]` -> `recomp\arranque\sm3dl_Pdiag.exe` con copia de recomp\sistema en `P\sis_diag` + volcado IPC (`SM3DL_VOLCAR_IPC="APT:U cecd:u"`).

## Hito 2 — StreetPass: "Activate" se cuelga (causa raiz)
- Con A en "Would you like to activate StreetPass?" (Activate) el juego lee cfg 0x000C0000 y 0x000D0000 (EULA, en ceros), abre SelfNCCH **tipo 2 (ExeFS "icon")** -> fs.c lo rechaza, y lanza el **applet de error 0x406** (APT 0x16 Preload, 0x18 PrepareToStart, 0x0C SendParameter 0x300->0x406 senal 2, 0x20 bytes desde 0x003F9400). APT no responde -> pantalla en blanco para siempre.
- Hacen falta LOS DOS arreglos (probado por separado: con uno solo sigue el applet 0x406): `P\parche_fs_exefs.py` (fs.c) + `P\parche_cfg_eula.py` (stubs.c, EULA 0x7F7F como Azahar). Con ambos: "StreetPass has not been activated" (cecd sin implementar) -> **pantalla de titulo "Press A to Start"** -> **seleccion de archivo (A/B/C New Game)** -> aviso "no tienes Mii, se te dara uno premade".

## Hito 3 — SIN parches: titulo + seleccion de archivo (exe normal sm3dl_P.exe)
- Guion `P\guiones\g2_cancelar_streetpass.txt`: A,A,A, **B (Cancel)** en "activate StreetPass?" -> "StreetPass has not been activated" -> **"Press A to Start"** (v846, `P\hitos\titulo_v846.png`) -> **seleccion de archivo A/B/C New Game** (v966, `hitos\seleccion_archivo_v966.png`) -> "You don't have any Mii characters... premade Mii" -> OK.
- Al OK el juego lanza el **selector de Mii (applet 0x402)**: Preload 0x16, GetAppletInfo, IsRegistered, SendParameter(0x300->0x402, senal 2, CaptureBufferInfo 0x20 de 0x003F9400) y espera la respuesta: se queda en la seleccion de archivo ignorando botones (no se cae).

## Hito 4 — con `parche_apt_applets.py` (diag): ARCHIVO CREADO
- HLE minimo de applets en APT (stubs.c): Request -> Response + memoria compartida; StartLibraryApplet -> WakeupByExit con MiiResult 0x84 (Mii estandar + crc16 CCITT) o eco de la configuracion (error 0x406).
- Bug encontrado al probarlo: el hilo 3 (eventos de APT) hace GlanceParameter y CIERRA el handle movido; si Receive devuelve el MISMO numero, el hilo 1 hace MapMemoryBlock(0x1002D, 0x10004000) con un handle cerrado y cae escribiendo en 0x10004000 (f_00296B2C, inicializa un heap ahi; cadena via `P\cadena_P.py`). Arreglo: guardar el SisObj y dar `sis_handle_nuevo` en CADA Glance/Receive.
- Resultado: FormatSaveData -> **"The file has been created"**, archivo A = **WORLD 1** (`hitos\archivo_creado_v1401.png`). Con A otra vez: fundido a AZUL (color de limpieza) = escena 3D sin dibujar.

## Nota — S ya implemento los applets en stubs.c (14:10)
- El APT de S (en vivo) ya da handle NUEVO por entrega y cierra applets al instante; Mii 0x402 devuelve "cancelado" (return_code 1). Con el guardado ya creado el juego no vuelve a pedir el Mii, asi que no pude confirmar si "cancelado" basta en un archivo nuevo; mi version (`parche_apt_applets.py`) devolvia un Mii estandar (MiiResult 0x84 con crc16) y SI llego a "The file has been created". **Pedido a S: probar archivo nuevo con su "cancelado"; si se cuelga, devolver el Mii estandar de mi parche.**
- ⚠️ Mi corrida diag de las 14:15-14:17 (sin SM3DL_GUARDADO) escribio en el `guardado\` COMPARTIDO (FormatSaveData + GameData.bin con archivo A = WORLD 1). Desde ahi el juego SALTA la bienvenida/StreetPass y va directo al titulo. Desde ahora uso `SM3DL_GUARDADO=agentes_noche\P\g<n>` (copia de `P\guardado_w1_base`).

## Hito 5 — 3D en pantalla: topologia 3 = lista de triangulos (pedido para R)
- Con guardado: titulo (v199) -> seleccion "A WORLD 1" (v319) -> A -> cinematica de apertura / mundo en 3D. Todo lo 3D sale en **topologia 3** (`Shader_008F2C` e0/e1/e2/e3 = prog F6C041B5 entradas 0/389/403/416, 12 atributos, hasta 9.900 vertices; y 9E8683BE, EF5FA4AD, 90A468A4, E8DA41C8 e27 a texturas 64x64) y `raster_gl.c` la SALTA ("topologia 3: se salta") -> pantalla azul.
- En PICA la topologia 3 (Shader) sin geometry shader se ensambla IGUAL que la lista (Azahar primitive_assembly.cpp: List y Shader en el mismo case; gl_rasterizer.cpp MakePrimitiveMode -> GL_TRIANGLES).
- Probado en diag (`compilar_diag.py --estable --topo3`, raster de antes de la tanda + el cambio): **sale el 3D**: fondo de nubes y suelo verde detras del logo del titulo, y la cinematica de apertura (nubes de tormenta) en gris (sin TEV/luz todavia). `P\hitos\3d_titulo_y_cinematica_topo3.png`. Sin el cambio (sabotaje natural): azul liso.
- **Pedido de integracion a R** (raster_gl.c, version nueva): antes de `if (topo > 2) {` poner `if (topo == 3) topo = 0;   /* Shader sin GS = List (Azahar) */`. (Si alguna vez hay GS real, el winding alterno de Azahar aplica solo con GS.)
- Programas que aparecen y NO estan en programas.tsv: fnv512 9FCCAA64 (e0), 088F5431 (e27), 07A0E153 (e0), E29EC423 (e0).

## Hito 6 — MAPA DEL MUNDO 1 y NIVEL 1-1 (diag `--estable --topo3`, guardado con archivo A)
- Guion `P\guiones\g6_mapa_entrar.txt` con `SM3DL_GUARDADO=<copia de P\guardado_w1_base>`: titulo -> archivo A -> cinematica (START la salta) -> **mapa W1** (~v3860, `hitos\mapa_mundo1_v4460.png`) -> DERECHA (v4500) + A (v4800) -> cartel "WORLD 1-1" (v4999) -> **nivel 1-1 corriendo** (cronometro 499->478, HUD W1-1, "NO ITEM", `hitos\nivel_1_1_v5659.png`) -> START = menu PAUSE (Continue / To Course Selection / Quit). Sin caidas en 118 s.
- En el nivel se ve suelo/cielo en gris (sin TEV/luz) y NO se ve a Mario (modelo con piel/otro programa: area de R).
- Sabotaje del guion: sin guion (cap0) la bienvenida sigue igual hasta v1446; con A cada 2 s (cap1) avanza por 4 dialogos. Un 2o sabotaje con boton B en guardado vacio quedo NO concluyente (en esa corrida final tampoco avanzo el guion con A en 13 s: no hubo tiempo de mirar por que; probablemente el arranque con guardado vacio + build diag tarda mas que v300).

## Pedidos de integracion (resumen)
1. **R (raster_gl.c):** topologia 3 = lista (`if (topo == 3) topo = 0;` antes de `if (topo > 2)`). Es LO que hace aparecer todo el 3D. Ojo: con el raster nuevo de R a las 14:22 el texto de los dialogos NO se dibujaba (cap11: logo si, dialogo no) y "bajar 13.9 s" de tiempo.
2. **S (fs.c):** SelfNCCH tipo 2 = ExeFS (`P\parche_fs_exefs.py`). **S (stubs.c cfg):** bloque 0x000D0000 EULA = 7F 7F (`P\parche_cfg_eula.py`). Ambos juntos hacen que "Activate StreetPass" no lance el applet de error.
3. **S (APT):** confirmar que Mii "cancelado" sirve con archivo NUEVO; si no, Mii estandar de `P\parche_apt_applets.py`.
4. **Sesion principal:** el `guardado\` compartido tiene ya el archivo A (lo escribio mi corrida de 14:17).

## Archivos tocados (respaldos .antes_P)
- `recomp\hid\hid.c/.h` (guion), `recomp\sistema\enchufes.c` (guion en hid_periodico + capturas PNG). main.c, ventana.c/h, capturas_png.py sin cambios.
- Herramientas: `P\hoja.py`, `P\compilar_diag.py [--estable --topo3 --exefs --eula --applets]` -> `recomp\arranque\sm3dl_Pdiag.exe`, `P\cadena_P.py` (CADENA_EXE=exe), parches `P\parche_*.py`.
- `sm3dl_P.exe` enlaza limpio con el arbol actual (cierre).
