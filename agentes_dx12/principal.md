# Sesión principal — paso 3: base de Direct3D 12 (8 oct noche)

## Archivos (nuevos, de la sesión principal)
- `recomp\render\d3d12_base.h/.c`: dispositivo (GPU de alto rendimiento por `EnumAdapterByGpuPreference`; integrada con
  `SM3DL_GPU_INTEGRADA`; capa de depuración con `SM3DL_D3D_DEBUG=1`), cola directa, 3 allocators + 1 lista, fence por
  cuadro, swap chain FLIP_DISCARD x3 BGRA con FRAME_LATENCY_WAITABLE_OBJECT (latencia 1) + ALLOW_TEARING si hay,
  `DXGI_MWA_NO_ALT_ENTER` (pantalla completa = ventana sin bordes → independent flip), anillo de SUBIDA de 64 MB
  (posiciones monótonas, se recicla por la fence del cuadro más viejo en vuelo), anillo de descriptores visibles
  (65.536), RTV (1.024) / DSV (256) fijos, `d3d_barrera`, estadísticas DXGI (refrescos sin imagen nueva).
- `recomp\render\prueba_d3d12.c` → `agentes_dx12\principal\prueba_d3d12.exe` (zig cc, `-ld3d12 -ldxgi -ldxguid`).
- C con COBJMACROS + `WIDL_C_INLINE_WRAPPERS` (las funciones que devuelven estructuras, p. ej.
  `GetCPUDescriptorHandleForHeapStart`, en C van por puntero oculto; los wrappers de mingw lo resuelven).

## Medido (ventana 800x480, solo ClearRenderTargetView, RTX 5050 Laptop, 144 Hz)
- vsync 1: 545 cuadros, intervalo medio **6,942 ms (144,0 Hz)**, desviación **0,325 ms**, peor 8,34 ms;
  DXGI: 575 presentaciones, **0 refrescos sin imagen nueva**.
- SABOTAJE (`SM3DL_D3D_SABOTAJE=1`, Sleep 12 ms cada 7 cuadros): 107,8 Hz, desv 6,7 ms, **138 refrescos sin imagen
  nueva** → la medición ve el fallo.
- Pendiente: lo mismo a pantalla completa sin bordes (independent flip) y con carga real.

## Siguiente (sesión principal)
- Paso 7 adelantado como prototipo: hilo de presentación que espera el objeto de latencia y presenta a 144 mientras
  otro hilo "juego" entrega cuadros a ~30 con temblor; medir ritmo. Es el diseño que quita los tirones.
- Integrar con la interfaz de `raster_backend.h` (agente A) y la cadena de shaders (agente B) cuando entreguen.

## Prototipo del paso 7: presentación en hilo aparte (`recomp\render\prueba_d3d12_hilo.c`)
- Hilo "juego" a 30 FPS con temblor ±3 ms y un tirón de 60 ms cada 97 cuadros (que no recupera el tiempo, como el real);
  hilo de presentación con el objeto de latencia, interpola una barra para el instante en que se VERÁ
  (ahora + periodo − retraso, retraso = 1 cuadro + 8 ms).
- 1er intento MAL (794 repetidas de 1009): tras cada tirón la línea del juego queda atrasada para siempre y el
  presentador pedía un instante sin estado. Arreglo: `desfase` que salta lo mínimo cuando falta estado y se recorre
  0,05 ms por refresco si sobra margen.
- **Clave**: la línea de tiempo del juego = nº de cuadro × 33,367 ms, NO la hora de cierre → el temblor no entra.
- Medido 8 s, 144 Hz: **error del paso 2,9 %, 15 repetidas (= los 2 tirones), 0 dobles**, DXGI 0 refrescos perdidos.
  SABOTAJE (t = k/5 fijos): 8,9 %, 39 dobles → la medición lo ve.
- Aplicable YA al modo Monitor en GL (sin esperar D3D12): usar cuadro × 33,367 como línea de tiempo en `alto_cerrar`
  en vez del cierre real, + desfase para los tirones.

## Recursos (pasos 4-6): `recomp\render\d3d12_recursos.h/.c` + `prueba_d3d12_recursos.c` (sin ventana, < 1 s)
- Texturas 2D (color / RT / D24S8 TYPELESS con SRV), estado seguido a mano, liberación diferida por fence, SRV en
  montón de CPU con reciclado; subida de regiones por el anillo (pitch 256); **lectura de vuelta asíncrona**
  (buffer READBACK + valor de fence; `d3d_leer_listo` sin bloquear); `d3d_ejecutar` para cargas; **caché de PSO** con
  `ID3D12PipelineLibrary` en disco (escritura atómica .tmp → rename; se descarta sola si cambia el driver).
- Medido: subida 400x240 + región → lectura **EXACTA (0 bytes)**; SABOTAJE (región 1 px corrida) → 4.079 bytes
  distintos. RT limpiado bien. PSO + triángulo (HLSL con d3dcompiler_47 de Windows) bien; 1ª corrida creado 17 ms,
  **2ª corrida del disco 0,5 ms**.
- Aprendido: (1) **D24S8 = dos planos** en D3D12 (subrecurso 0 z, 1 stencil R8): la lectura copia ambos y los
  empaqueta como la PICA (z 24 bajos, stencil byte alto). (2) float→UNORM8 en el medio punto no es exacto
  (0,5 → 127 en la RTX; la norma tolera 0,6 ULP): la comparación por píxel GL vs D3D12 debe ir con el TEV en enteros
  y tolerar ±1 en caminos float.

## Presentador D3D12: `recomp\render\d3d12_presentador.h/.c` + `prueba_d3d12_pres.c`
- Equivalente de `presentador_gl.inc`: 16 ranuras (CopyResource), base escalada (rectángulo texturizado: D3D12 no
  tiene BlitFramebuffer; muestreo punto/lineal por constante raíz), 2 capas BGRA premultiplicadas con subida por zona
  sucia y mezcla (ONE, INV_SRC_ALPHA), lectura de lo compuesto para verificar. Firma raíz: 12 constantes + 1 SRV + 2
  samplers estáticos. HLSL con d3dcompiler_47 (2 shaders chicos; no hace falta DXC).
- Medido (1600x960 → 1200x720 nítido + HUD 400x240 + interfaz): **0 px distintos** contra la composición de
  referencia en CPU (el camino GL daba ≤ 0,5 % legítimo por muestreo distinto); SABOTAJE base 3 px: 56,3 % muy
  distintos → detectado (umbral 1 %, el mismo del pres-verif GL).
- Ojo: la 1ª composición tarda ~19 ms (compila los 2 HLSL + PSO); las siguientes, nada. Compilar al iniciar.

## Prueba con el juego del paso 1 (A), 8 oct noche — `agentes_dx12\A\trabajo\juego_x1\`
- 5 corridas (oculto, turbo 3, 45 s, partida j8). antes vs nuevo: **69/110 capturas idénticas byte a byte**, incluido
  TODO el tramo del nivel (vblank 3.203-6.623); las 41 distintas caen en intro/menús/transiciones animadas.
- El CONTROL (mismo exe 2 veces) no comparte ni un nombre de captura (v000082 vs v000083: el turbo corre 1-2 vblanks
  entre corridas) → la prueba no es determinista por vblank tal como está; no se puede exigir 0 px en tramos animados.
- Sabotaje 1 detectado. `SM3DL_BACKEND=d3d12` avisaba "NO IMPLEMENTADO" y caía a gl (correcto).
- Veredicto: aceptado (junto con el arnés de A: 21/21 escenarios byte a byte). Mejora pendiente: capturar por número
  de CUADRO del juego (no por vblank) para que el control sea comparable.

## Base D3D12 v2 (LISTA CONTINUA) e integración del backend
- `d3d12_base`: pool de 16 allocators con fence, `d3d_lista()`/`d3d_vaciar()` sin espera, marcas por vaciado para
  reciclar los anillos (subida, SRV, y NUEVO anillo de muestreadores de 2.048), `d3d_atras_empezar/presentar`.
  Las 4 pruebas siguen pasando (lectura EXACTA, sabotaje 4.079 B, presentador 0 px, 144 Hz).
- `raster_gl.c`: con `-DSM3DL_CON_D3D12` declara `rb_d3d12_obtener` e incluye `raster_backend_d3d12.c` al final.
  `compilar.py --d3d12` agrega la definición, `d3d12_{base,recursos,presentador}.c` y `-ld3d12 -ldxgi -ldxguid
  -ld3dcompiler_47`. Sin `--d3d12` todo queda como antes (`sm3dl_gl_ref.exe` compila igual).
- `raster_backend_d3d12.c` (esqueleto): tipos `DxTex/DxRT/DxEtapa/DxProg/DxLectura` (el GL define `struct RbTex` en el
  MISMO archivo de compilación → se convierten con `DX_TEX(p)`…), estado `dx`, tabla; partes con relleno
  `raster_d3d12_recursos.inc` (agente C) y `raster_d3d12_dibujo.inc` (agente D). Brief: `BRIEF_BACKEND.md`.
- Nota 6 de `raster_backend.h` corregida (pedido de B: el VS voltea, no el viewport).
