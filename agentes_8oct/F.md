# Agente F — intérprete PICA200 (8 oct)
Estado: arrancado. Leyendo pica_cmd.py / pica_registros.md.

## Diseño (decidido)
- `recomp\render\pica.h/.c`: banco 0x300, `pica_ejecutar(dir_fisica,tam)` (memoria por gancho `pica_memoria`, lo pone el integrador), `pica_ejecutar_palabras()` para pruebas, saltos CMDBUF_JUMP, FINALIZE/IRQ como Azahar.
- Efectos laterales (como Azahar): subida de uniforms float (cola empaquetada f24 3 palabras / f32 4 palabras; índice se incrementa EN el banco), código/swizzles (offset se incrementa en el banco), LUTs de luz/niebla, atributos fijos, VS→GS espejo si no hay GS.
- `pica_dibujar(const PicaEstado*)` vacío en `pica_dibujar.c` (la prueba trae el suyo).
- Prueba: `tools\pica_volcar_estado.py` arma listas con los BYTES REALES de las cachés de material (cabecera+param0+extras), y subidas de shader con código/swizzles/constantes reales de los DVLB; modelo de referencia en Python; compara volcado de texto.

## Resultado (cierre)
- **Archivos:** `recomp\render\pica.h`, `pica.c` (intérprete + decodificación, ~430 líneas), `pica_dibujar.c` (callback vacío), `prueba_pica.c` (volcado de texto), `tools\pica_volcar_estado.py` (casos + modelo Python + comparación). Salidas en `extraido\pica_prueba\` (casos.bin, esperado.txt, obtenido.txt, exes).
- **Prueba:** `py -I tools\pica_volcar_estado.py [--compilar] [--sabotaje MASCARA|F24]` (~35 s).
  - **830/830 casos idénticos C vs Python**: 7 sintéticos (máscaras 0..F, float24 especiales ±0/±inf/NaN con payload/denormales/máx, f32, índice 96 y 0x7F ignorados, GS separado, LUT de luz con vuelta en 256 y tabla inválida, LUT de niebla, atributos fijos + modo inmediato → error, vértices/loaders/índices + DRAWELEMENTS/DRAWARRAYS, saltos CMDBUF_JUMP encadenados, FINALIZE con IRQ_CMP/AUTOSTOP, cabecera que se sale) + 32 subidas de shader con código/swizzles/constantes REALES de los 7 DVLB (consecutivo y no) + **791 listas de material distintas** (bytes reales de las cachés de los 4.579 materiales, 14.971 cabeceras, 6.686 con extras).
  - Banco contrastado además con `pica_cmd.parsear+estado` (826 casos): 0 diferencias.
  - **Sabotajes:** máscara ignorada → 822/830 (falla el sintético + 7 materiales reales: s_water01, BlackOut02, LetterCloseMat00, MiniStones…); sesgo f24 63→64 → 797/830 (todos los de uniforms/shaders/viewport).
- Compila sin avisos con `-Wall -Wextra -Wpedantic` (zig cc x86_64-windows-gnu).

## Hallazgos
- **Las plantillas de material escriben con máscara PARCIAL en cada material:** DEPTH_COLOR_MASK (m=1: solo test/func de depth; color_mask y depth_write los pone el código), FACECULLING (1), STENCIL_TEST (13), TEXENV_UPDATE_BUFFER (2), LIGHTING_CONFIG0 (2), GAS_DELTAZ_DEPTH (8), TEXUNITn_TYPE (1). → el estado de un dibujo depende de lo que dejó el código antes: hay que ejecutar la lista completa del frame, no la plantilla sola.
- `tools\shbin.py f24()` trata exponente 0 como NORMAL ((1+m/65536)·2^-63); lo correcto (Azahar) es denormal m·2^-78. Afecta solo valores ~1e-19 (inofensivo, pero la batería de shaders comparte esa aritmética). Lo anoto, no es archivo mío.
- float24→float32: ±0, inf/NaN (payload conservado), denormal renormalizado sin pérdida (el ALU del PICA los aplana; eso es asunto del shader). Uniforms en modo float32 se guardan tal cual (como Azahar).

## Pendientes
- Modo inmediato (FIXEDATTRIB índice 15 = vértice suelto): cuenta como error, no implementado.
- PROCTEX LUT: solo al banco (el juego no usa procedural).
- Ninguna lista REAL de frame probada (solo plantillas): cuando el arranque llegue a GSP, volcar una lista real y pasarla.

## Pedidos de integración
1. Al enlazar: `pica_memoria = gsp_fisica_a_host; gsp_pica = pica_ejecutar;` (firmas ya compatibles con `recomp\gpu\gsp.h`) y enlazar `recomp\render\pica.c` + `pica_dibujar.c`.
2. GSP: tras `gsp_pica(dir,tam)`, si `pica.e.irq_p3d` creció, señalar `GSP_INT_P3D` (hoy el intérprete solo cuenta el FINALIZE).
