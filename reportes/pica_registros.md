# Registros PICA200 y etapa de fragmentos â€” censo (agente E, 7 oct 2026)

Herramienta: `tools\pica_cmd.py`
- `material <szs>`: comandos de cada material, decodificados.
- `censo`: todos los materiales de ObjectData + StageData â†’ `extraido\pica_materiales.tsv` + resumen. Tarda 7 s.
- `codigo`: cabeceras de comando en el ejecutable. Tarda 3 s.
- `lista <bin>`: parser estricto de una lista de comandos real.

Los nombres de registro son los `GPUREG_*` de 3dbrew, tomados de la tabla de `azahar-src\...\regs_internal.cpp` (397). Los campos se verificaron contra `regs_texturing.h`, `regs_lighting.h` y `regs_framebuffer.h`.

## 1. DÃ³nde vive el estado de fragmentos

### a) Materiales CGFX (MTOB): comandos PICA ya armados
Son pares `(parÃ¡metro, cabecera)` sueltos dentro de la estructura del material; no forman una lista continua.

**Orden fijo en los 4.579 materiales:**
1. culling `0x040`
2. depth `0x107` (con mÃ¡scara de bytes 1)
3. `0x126` (byte 3)
4. rÃ¡faga `0x100â€“0x103` (operaciÃ³n de color, blend, logic op, blend color)
5. stencil `0x105` y `0x106`
6. texturas 0/1/2 (`0x08E` + `0x081â€“0x08A`, `0x091â€“0x098`, `0x099â€“0x0A2`)
7. **6 etapas TEV** (cada una en rÃ¡faga `0x804F00Cx`)
8. alpha test `0x104`
9. `0x0FD` buffer color
10. `0x0E0` (mÃ¡scara 2)
11. `LIGHTING_CONFIG0 0x1C3` (mÃ¡scara 2), siempre el Ãºltimo

La posiciÃ³n de `0x1C3` dentro del material solo depende de cuÃ¡ntas texturas tiene: +1000 bytes sin texturas, +140 por cada una (1140/1280/1420). El escÃ¡ner corta ahÃ­; lo que sigue es la malla siguiente leÃ­da como si fueran comandos. AsÃ­ se eliminaron los falsos `DRAWELEMENTS`/`FINALIZE`.

**Son plantillas.** El runtime de NW4C completa en el momento de dibujar:
- `TEXUNITn_TYPE` siempre es 0, y `DIM`/`ADDR` tambiÃ©n: el formato, el tamaÃ±o y la direcciÃ³n de la textura se ponen al enlazarla.
- `DEPTH_COLOR_MASK` solo escribe el byte 0 (test on, funciÃ³n `<`); la mÃ¡scara de color y la escritura de depth vienen de otro lado.
- `LIGHTING_CONFIG0` solo escribe el byte 1 (0x04, sin campo con nombre). La configuraciÃ³n real del fragment lighting sale de campos NO-comando del material: capa (`config`), fresnel, bump, LUTs, sombras.

### b) Ejecutable (`code.bin`)
- **302 cabeceras distintas** cargadas como literal (`ldr [pc]`). El runtime escribe:
  - framebuffer, viewport y scissor
  - las 8 luces (`0x140â€“0x1BB`) y `LIGHTING_*` (`0x1C0â€“0x1D9`, incluido `LUT_INDEX` Ã—15)
  - fog LUT (`0x0E6/0x0E8`) y gas
  - shadow (`0x130`) y proctex (`0x0A8â€“0x0B4`)
  - todo el pipeline de geometrÃ­a (`0x200â€“0x25F`) y los uniforms y cÃ³digo de VSH/GSH (`0x280â€“0x2DF`)
  - TEV y blend sueltos (sobrescrituras de material)
- **Tablas de comandos en `.rodata`/`.data`** (corridas de 3 o mÃ¡s comandos vÃ¡lidos seguidos):
  - `0x003A7D70`â€“`0x003A8588`: plantillas de estado por defecto: fragmentos, TEV, viewport y framebuffer, geometrÃ­a y draw.
  - `0x003AEDA0`: 38 comandos.
  - `.data` `0x003F0780` (28), `0x003F09B4` (56, TEV), `0x003F1220` (24, framebuffer, depthmap, culling, stencil).
  - Las corridas de 3 en `0x003E0Axx` y `0x003B3224` son probablemente ruido.
  - Detalle completo en el ApÃ©ndice B.

## 2. Censo (4.579 materiales, 1.556 .szs, 0 errores)
- **337 recetas TEV distintas** (las 6 etapas sin el color constante), con 432 etapas distintas. Hay mucha concentraciÃ³n: las 5 primeras cubren 1.957 materiales.
- **Etapas activas por material:** 6 â†’ 2.147 Â· 5 â†’ 1.583 Â· 3 â†’ 235 Â· 1 â†’ 442 Â· 2 â†’ 86 Â· 4 â†’ 82 Â· 0 â†’ 4.
- **PatrÃ³n base del juego** (aparece en cientos de recetas):
  - `TEV0 rgb = (1 âˆ’ especular.a)Â·k + difusa`, `a = color_vtx.aÂ·tex0.a`
  - despuÃ©s `Â·tex0`, `Â·buffer_previo`, `+especular(Â·tex1)`, y `(color_vtx+k)Â·previo` con Ã—2
  - es decir, **todo depende del fragment lighting** (difusa/especular por fragmento).
- **Fuentes:** constante 39K Â· previo 37K Â· luz_difusa 19,6K Â· tex0 11,7K Â· luz_especular 10,2K Â· color_vtx 9,9K Â· buffer_previo 4,6K Â· tex1 2,5K Â· tex2 80. **No usa tex3/proctex en materiales.**
- **Combinadores:**
  - rgb: MULADD 9.047, MOD 6.452, ADDMUL 3.390, LERP 1.096, ADD 1.034, ADDS 909, REPLACE 482, DOT3_RGB 28, SUB 6
  - alfa: casi todo REPLACE/MOD
  - escalas Ã—2 frecuentes (4.033) y Ã—4 raras
- **Buffer de combinador** (`0x0E0`): se usa mucho (buffer_rgb â‰  0 en ~3.800 materiales). **Fog = no** en todos los materiales: si hay niebla, la activa el runtime (`0x0E0` y la fog LUT aparecen en el cÃ³digo).
- **Blend:**
  - 3.486 opacos (`1,0`)
  - 611 alfa clÃ¡sico (`src.a, 1âˆ’src.a`)
  - 254 alfa solo en rgb
  - aditivos `src.a,1` (76 + 43)
  - multiplicativos `dst,0` (45 + 10)
  - unos pocos con logic op
- **Alpha test:** off en 3.692; `> 128` on en 355 (otros 475 lo tienen con la funciÃ³n puesta pero apagado); `> 125`/`> 0` en unos pocos.
- **Depth:** test `<` en 4.564. **Culling:** atrÃ¡s en 4.415, ninguno en 164. **Stencil:** off en todos (input mask FF en 808); un material usa `decr_wrap`.
- **Texturas:** wrap 2 (repeat) es lo dominante, wrap 3 (mirror) en ~500. Filtro lineal, salvo ~600 con nearest. Mip siempre nearest en el byte de la plantilla.

Por material: `extraido\pica_materiales.tsv` (receta `R#`, culling, depth, blend, alpha test, update buffer). La tabla completa de las 25 recetas mÃ¡s usadas estÃ¡ en el ApÃ©ndice A.

## 3. QuÃ© tiene que implementar el renderer de PC (por prioridad)
1. **Combinador TEV de 6 etapas + buffer de combinador** (`0x0E0`/`0x0FD`), con todas las fuentes, modificadores, los 10 combinadores y las escalas. Generar un shader de fragmentos por receta: hay 337, se pueden precompilar o cachear.
2. **Fragment lighting** (difusa y especular por fragmento, 8 luces, LUTs D0/D1/RR/RG/RB/FR, spot, atenuaciÃ³n, especular.a como factor). Sin esto, el 90 % de los materiales sale mal. Su configuraciÃ³n la arma el runtime: falta leer los campos de fragment lighting del MTOB y las escrituras de `0x1C3/0x1C4/0x1D0â€“0x1D2` en el cÃ³digo.
3. **Blend** (add con `src.a/1âˆ’src.a`, `1,1`, `dst,0`), **alpha test**, **depth `<`** y **culling**.
4. **Texturas 0â€“2** con wrap repeat/mirror/clamp, filtro lineal/nearest y formatos que vienen de la textura, no del material (ya hay PNG de las 5.693).
5. **Niebla** (fog LUT de 128 entradas, `0x0E6/0x0E8`), que la escribe el runtime. **Logic op** para unos pocos materiales.
6. Opcional o raro: stencil (1 material), DOT3 (28 etapas), shadow/gas/proctex (solo aparecen en cÃ³digo y tablas; verificar si se usan).

## 4. QuÃ© faltÃ³ (sesiÃ³n cortada)
- Decodificar el resto de campos NO-comando del MTOB: colores de material, fragment lighting (capa, fresnel, LUT samplers, bump) y texture coordinators.
- Seguir las referencias del cÃ³digo a las tablas de `.rodata`/`.data` (quiÃ©n las copia y cuÃ¡ndo).
- Confirmar la semÃ¡ntica de `0x126` (byte 3 = 3) y de los valores raros de `COLOR_OPERATION` (`0x2600`â€¦).
- Los 9 registros sueltos que quedan en el censo (cuenta 1) son ruido residual del escÃ¡ner.

## ApÃ©ndice A â€” salida de `pica_cmd.py censo`

#### Censo de materiales

archivos .szs: 1556 · materiales: 4579 · errores: 0


##### Registros escritos por las cachés de material (83 distintos)

`FACECULLING_CONFIG` (4579), `TEXUNIT0_BORDER_COLOR` (4216), `TEXUNIT0_DIM` (4216), `TEXUNIT0_PARAM` (4216), `TEXUNIT0_LOD` (4216), `TEXUNIT0_ADDR1` (4216), `TEXUNIT0_ADDR2` (4216), `TEXUNIT0_ADDR3` (4216), `TEXUNIT0_ADDR4` (4216), `TEXUNIT0_ADDR5` (4216), `TEXUNIT0_ADDR6` (4216), `TEXUNIT0_TYPE` (4216), `TEXUNIT1_BORDER_COLOR` (2547), `TEXUNIT1_DIM` (2548), `TEXUNIT1_PARAM` (2547), `TEXUNIT1_LOD` (2547), `TEXUNIT1_ADDR` (2547), `TEXUNIT1_TYPE` (2547), `REG_097` (2547), `REG_098` (2547), `TEXUNIT2_BORDER_COLOR` (2547), `TEXUNIT2_DIM` (2547), `TEXUNIT2_PARAM` (980), `TEXUNIT2_LOD` (980), `TEXUNIT2_ADDR` (980), `TEXUNIT2_TYPE` (980), `REG_09F` (980), `REG_0A0` (980), `REG_0A1` (980), `REG_0A2` (980), `TEXUNIT3_PROCTEX3` (1), `TEXENV0_SOURCE` (4578), `TEXENV0_OPERAND` (4578), `TEXENV0_COMBINER` (4578), `TEXENV0_COLOR` (4578), `TEXENV0_SCALE` (4578), `TEXENV1_SOURCE` (4579), `TEXENV1_OPERAND` (4579), `TEXENV1_COMBINER` (4579), `TEXENV1_COLOR` (4579), `TEXENV1_SCALE` (4579), `TEXENV2_SOURCE` (4579), `TEXENV2_OPERAND` (4579), `TEXENV2_COMBINER` (4579), `TEXENV2_COLOR` (4579), `TEXENV2_SCALE` (4579), `TEXENV3_SOURCE` (4579), `TEXENV3_OPERAND` (4579), `TEXENV3_COMBINER` (4579), `TEXENV3_COLOR` (4579), `TEXENV3_SCALE` (4579), `TEXENV_UPDATE_BUFFER` (4579), `TEXENV4_SOURCE` (4579), `TEXENV4_OPERAND` (4579), `TEXENV4_COMBINER` (4579), `TEXENV4_COLOR` (4579), `TEXENV4_SCALE` (4579), `TEXENV5_SOURCE` (4579), `TEXENV5_OPERAND` (4579), `TEXENV5_COMBINER` (4579), `TEXENV5_COLOR` (4579), `TEXENV5_SCALE` (4579), `TEXENV_BUFFER_COLOR` (4579), `COLOR_OPERATION` (4579), `BLEND_FUNC` (4579), `LOGIC_OP` (4579), `BLEND_COLOR` (4579), `FRAGOP_ALPHA_TEST` (4579), `STENCIL_TEST` (4579), `STENCIL_OP` (4579), `DEPTH_COLOR_MASK` (4579), `FRAMEBUFFER_FLUSH` (1), `GAS_DELTAZ_DEPTH` (4579), `LIGHT0_SPECULAR0` (1), `LIGHT0_DIFFUSE` (1), `LIGHT1_SPECULAR1` (1), `LIGHT5_AMBIENT` (1), `LIGHT7_XY` (1), `LIGHTING_CONFIG0` (4579), `ATTRIBBUFFER5_OFFSET` (1), `ATTRIBBUFFER6_OFFSET` (1), `ATTRIBBUFFER9_CONFIG1` (1), `GSH_CODETRANSFER_DATA4` (1)

##### Recetas TEV (6 etapas, sin el color constante): **332 distintas**

| # | materiales | ejemplo | etapas activas |
|---|---|---|---|
| R0 | 549 | AquariumSwimMiddleView.szs/my03_Flower001 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MOD(previo, buffer_previo) | a = REPLACE(previo.a)<br>3: rgb = ADD(luz_especular, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) x2 | a = REPLACE(previo.a) |
| R1 | 412 | BalanceTruckStepBSp.szs/my03_MatelBlack | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MOD(previo, buffer_previo) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex1, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, previo, previo) x2 | a = REPLACE(previo.a) |
| R2 | 373 | AquariumSwimGoal.szs/ms01_RockA002 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MOD(previo, buffer_previo) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex1, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) x2 | a = REPLACE(previo.a) |
| R3 | 365 | Barrel.szs/BarrelMat00 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, previo) | a = REPLACE(previo.a)<br>2: rgb = ADDS(previo, constante) | a = REPLACE(previo.a)<br>3: rgb = LERP((1-previo), previo, luz_especular) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, buffer_previo, previo) x2 | a = REPLACE(previo.a) |
| R4 | 262 | AquariumSwimGoal.szs/FenceWood00 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MULADD(previo, buffer_previo, luz_especular) | a = REPLACE(previo.a)<br>3: rgb = MULADD(tex1, constante, previo) | a = REPLACE(previo.a)<br>4: rgb = MULADD(color_vtx, constante, color_vtx) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, buffer_previo, constante) x2 | a = REPLACE(previo.a) |
| R5 | 211 | AquariumSwimStepA.szs/s_Shadow01 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = ADD(color_vtx.a, tex1.r)<br>1: rgb = MOD(tex0, constante) | a = MOD(previo.a, color_vtx.a) x4<br>2: rgb = MOD(previo, buffer_previo) | a = ADDS(previo.a, constante.a) x2<br>3: rgb = MULADD(luz_especular, tex1, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) x2 | a = REPLACE(previo.a) |
| R6 | 134 | AquariumSwimStepBSurface.szs/b_Test1 | 0: rgb = MOD(luz_difusa, tex0) | a = MOD(color_vtx.a, tex0.a) |
| R7 | 112 | AssistItem.szs/AssistItemMat00 | 0: rgb = MOD(tex0, constante.a) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = ADDS(previo, constante) | a = REPLACE(previo.a)<br>2: rgb = MULADD((1-luz_especular), previo, luz_especular) | a = REPLACE(previo.a)<br>3: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>4: rgb = MULADD(previo, buffer_previo, previo) x2 | a = REPLACE(previo.a) |
| R8 | 106 | BoneRollerCoasterParts.szs/Bone | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MULADD(previo, buffer_previo, constante) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex1, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, previo, previo) x2 | a = REPLACE(previo.a) |
| R9 | 105 | AquariumSwimStepA.szs/a_Sand02 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MOD(previo, buffer_previo) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex0, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, color_vtx) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, buffer_previo, constante) x2 | a = REPLACE(previo.a) |
| R10 | 86 | CourseBackGroundS1.szs/CircleCloudMat | 0: rgb = REPLACE(constante) | a = REPLACE(tex0.r)<br>1: rgb = LERP(previo, constante, previo.a) | a = MOD(color_vtx.a, tex0.a)<br>2: rgb = LERP(constante, previo, color_vtx) | a = REPLACE(previo.a) |
| R11 | 83 | DemoObjectShip.szs/MiniatureBattleshipMat03 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, previo) | a = REPLACE(previo.a)<br>2: rgb = ADDS(previo, constante) | a = REPLACE(previo.a)<br>3: rgb = MULADD(tex0, luz_especular, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, buffer_previo, previo) x2 | a = REPLACE(previo.a) |
| R12 | 75 | Burner.szs/BurnerMat | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MULADD(previo, buffer_previo, constante) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, (1-buffer_previo), previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, previo, previo) x2 | a = REPLACE(previo.a) |
| R13 | 71 | BoomerangMountainBalancePassage.szs/xx01_Metal01 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(previo, constante) | a = REPLACE(previo.a)<br>2: rgb = ADD(luz_especular, previo) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex0, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) x2 | a = REPLACE(previo.a) |
| R14 | 70 | BeatKabeheiStepA.szs/Wood01 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) x2 | a = REPLACE(previo.a)<br>2: rgb = MOD(previo, buffer_previo) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex1, previo) | a = REPLACE(previo.a)<br>4: rgb = MOD(color_vtx, constante) x2 | a = REPLACE(previo.a)<br>5: rgb = ADDMUL(previo, color_vtx, buffer_previo) x2 | a = REPLACE(previo.a) |
| R15 | 65 | KinopioRaccoonDog.szs/KinopioBodyMat00 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, previo) | a = REPLACE(previo.a)<br>2: rgb = ADDS(previo, constante) | a = REPLACE(previo.a)<br>3: rgb = MULADD((1-buffer_previo), luz_especular, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, buffer_previo, previo) x2 | a = REPLACE(previo.a) |
| R16 | 61 | MiniatureAquariumSwim.szs/MiniatureAquariumSwimMat09 | 0: rgb = REPLACE(constante) | a = REPLACE(constante.a) |
| R17 | 57 | BalanceTruckLavaGoalSp.szs/RockUnder | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MOD(previo, buffer_previo) | a = REPLACE(previo.a)<br>3: rgb = MULADD(luz_especular, tex1, previo) | a = REPLACE(previo.a)<br>4: rgb = MOD(color_vtx, constante) x2 | a = REPLACE(previo.a)<br>5: rgb = ADDMUL(previo, color_vtx, buffer_previo) x2 | a = REPLACE(previo.a) |
| R18 | 55 | BattleShipGoal.szs/my03_ShadowLine01 | 0: rgb = ADD(constante, color_vtx) | a = REPLACE(color_vtx.a) |
| R19 | 52 | BalanceTruck.szs/BalanceTruckMat00 | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, previo) | a = REPLACE(previo.a)<br>2: rgb = ADDS(previo, constante) | a = REPLACE(previo.a)<br>3: rgb = MULADD(tex1, luz_especular, previo) | a = REPLACE(previo.a)<br>4: rgb = ADDMUL(color_vtx, constante, previo) | a = REPLACE(previo.a)<br>5: rgb = MULADD(previo, buffer_previo, previo) x2 | a = REPLACE(previo.a) |
| R20 | 52 | BalanceTruckGoal.szs/BigTreeWoodA | 0: rgb = MULADD((1-luz_especular.a), constante, luz_difusa) | a = MOD(color_vtx.a, tex0.a)<br>1: rgb = MOD(tex0, constante) | a = REPLACE(previo.a)<br>2: rgb = MULADD(previo, buffer_previo, luz_especular) | a = REPLACE(previo.a)<br>3: rgb = MULADD(color_vtx, constante, color_vtx) | a = REPLACE(previo.a)<br>4: rgb = MULADD(previo, buffer_previo, constante) x2 | a = REPLACE(previo.a)<br>5: rgb = LERP(previo, constante, color_vtx.a) | a = REPLACE(previo.a) |
| R21 | 50 | BattleShipKillerBossRoom.szs/Shadow | 0: rgb = MOD(luz_difusa, color_vtx) | a = REPLACE(color_vtx.a) |
| R22 | 49 | CourseBackGroundS1.szs/CloudMat | 0: rgb = REPLACE(constante) | a = REPLACE(tex0.r)<br>1: rgb = LERP(previo, constante, previo.a) | a = MOD(color_vtx.a, tex0.a)<br>2: rgb = LERP(constante, previo, color_vtx) | a = MOD(previo.a, tex0.a) |
| R23 | 42 | AquariumSwimStepB.szs/ShadowLine | 0: rgb = ADD(luz_especular, constante) | a = MOD(color_vtx.a, constante.a) |
| R24 | 35 | BlockPropellerSilhouette.szs/BlockPropellerSilhouetteMat00 | 0: rgb = REPLACE(luz_difusa) | a = REPLACE(color_vtx.a) |

Etapas activas por material: {0: 4, 1: 443, 2: 85, 3: 235, 4: 82, 5: 1583, 6: 2147}

Etapas distintas (fuente+operando+combinador+escala): 427

Fuentes usadas: {'constante': 39226, 'previo': 36810, 'luz_difusa': 19593, 'tex0': 11712, 'luz_especular': 10220, 'color_vtx': 9930, 'buffer_previo': 4612, 'tex1': 2475, 'tex2': 80}

Combinadores: {'REPLACE/a': 17512, 'MULADD/rgb': 9047, 'MOD/rgb': 6453, 'MOD/a': 4315, 'ADDMUL/rgb': 3390, 'LERP/rgb': 1096, 'ADD/rgb': 1034, 'ADDS/rgb': 909, 'REPLACE/rgb': 480, 'ADD/a': 305, 'ADDS/a': 298, 'DOT3_RGB/rgb': 28, 'MULADD/a': 11, 'SUB/rgb': 6, 'LERP/a': 2}

Escalas (rgb, a) en etapas activas: {(0, 0): 17752, (1, 0): 4033, (0, 2): 290, (0, 1): 290, (2, 0): 43, (2, 2): 17, (1, 2): 16, (1, 1): 2}

##### `FACECULLING_CONFIG` — 2 valores distintos

- `00000002` × 4415 — culling atras(cw)
- `00000000` × 164 — culling ninguno

##### `TEXENV_UPDATE_BUFFER` — 13 valores distintos

- `00000100` × 2188 — fog=no buffer_rgb=0001 buffer_a=0000 zflip=0
- `00000000` × 783 — fog=no buffer_rgb=0000 buffer_a=0000 zflip=0
- `00000400` × 699 — fog=no buffer_rgb=0100 buffer_a=0000 zflip=0
- `00000900` × 569 — fog=no buffer_rgb=1001 buffer_a=0000 zflip=0
- `00000200` × 157 — fog=no buffer_rgb=0010 buffer_a=0000 zflip=0
- `00000500` × 122 — fog=no buffer_rgb=0101 buffer_a=0000 zflip=0
- `00000600` × 19 — fog=no buffer_rgb=0110 buffer_a=0000 zflip=0
- `00000700` × 13 — fog=no buffer_rgb=0111 buffer_a=0000 zflip=0

##### `TEXENV_BUFFER_COLOR` — 53 valores distintos

- `FFFFFFFF` × 3776
- `FF000000` × 734
- `FFFF2F00` × 5
- `FFA89E78` × 4
- `FF0040FF` × 3
- `FFFFFFDB` × 3
- `FF004DFF` × 2
- `FF0009EC` × 2

##### `COLOR_OPERATION` — 1 valores distintos

- `00E40100` × 4579 — modo=normal blend

##### `BLEND_FUNC` — 14 valores distintos

- `01010000` × 3486 — rgb: add(1, 0) a: add(1, 0)
- `76760000` × 611 — rgb: add(src.a, 1-src.a) a: add(src.a, 1-src.a)
- `01760000` × 254 — rgb: add(src.a, 1-src.a) a: add(1, 0)
- `16160000` × 76 — rgb: add(src.a, 1) a: add(src.a, 1)
- `04040000` × 45 — rgb: add(dst, 0) a: add(dst, 0)
- `01160000` × 43 — rgb: add(src.a, 1) a: add(1, 0)
- `11760000` × 42 — rgb: add(src.a, 1-src.a) a: add(1, 1)
- `01040000` × 10 — rgb: add(dst, 0) a: add(1, 0)

##### `FRAGOP_ALPHA_TEST` — 13 valores distintos

- `00000010` × 3692 — alpha_test off siempre 0
- `00008060` × 475 — alpha_test off > 128
- `00008061` × 355 — alpha_test on > 128
- `00008040` × 22 — alpha_test off < 128
- `00007D61` × 13 — alpha_test on > 125
- `00000061` × 6 — alpha_test on > 0
- `00006E60` × 5 — alpha_test off > 110
- `00000060` × 3 — alpha_test off > 0

##### `STENCIL_TEST` — 2 valores distintos

- `00000000` × 3771 — stencil off nunca ref=0 wmask=00 imask=00
- `FF000000` × 808 — stencil off nunca ref=0 wmask=00 imask=FF

##### `STENCIL_OP` — 1 valores distintos

- `00000000` × 4579 — stencil_op fail=keep zfail=keep zpass=keep

##### `DEPTH_COLOR_MASK` — 4 valores distintos

- `00000041` × 4564 — depth on < color_mask=- depth_write=0
- `00000040` × 9 — depth off < color_mask=- depth_write=0
- `00000061` × 5 — depth on > color_mask=- depth_write=0
- `00000000` × 1 — depth off nunca color_mask=- depth_write=0

##### `TEXUNIT0_PARAM` — 13 valores distintos

- `00002206` × 3249 — mag=lineal min=lineal wrap_t=2 wrap_s=2 mip=cercano
- `00003306` × 457 — mag=lineal min=lineal wrap_t=3 wrap_s=3 mip=cercano
- `00002200` × 147 — mag=cercano min=cercano wrap_t=2 wrap_s=2 mip=cercano
- `00003206` × 93 — mag=lineal min=lineal wrap_t=2 wrap_s=3 mip=cercano
- `00002204` × 93 — mag=cercano min=lineal wrap_t=2 wrap_s=2 mip=cercano
- `00002006` × 58 — mag=lineal min=lineal wrap_t=0 wrap_s=2 mip=cercano
- `00000006` × 38 — mag=lineal min=lineal wrap_t=0 wrap_s=0 mip=cercano
- `00003006` × 29 — mag=lineal min=lineal wrap_t=0 wrap_s=3 mip=cercano

##### `TEXUNIT0_TYPE` — 1 valores distintos

- `00000000` × 4216 — formato RGBA8

##### `TEXUNIT1_PARAM` — 10 valores distintos

- `00002206` × 2006 — mag=lineal min=lineal wrap_t=2 wrap_s=2 mip=cercano
- `00002200` × 436 — mag=cercano min=cercano wrap_t=2 wrap_s=2 mip=cercano
- `00003306` × 50 — mag=lineal min=lineal wrap_t=3 wrap_s=3 mip=cercano
- `00002006` × 33 — mag=lineal min=lineal wrap_t=0 wrap_s=2 mip=cercano
- `00000006` × 9 — mag=lineal min=lineal wrap_t=0 wrap_s=0 mip=cercano
- `00002306` × 5 — mag=lineal min=lineal wrap_t=3 wrap_s=2 mip=cercano
- `00003206` × 2 — mag=lineal min=lineal wrap_t=2 wrap_s=3 mip=cercano
- `00003300` × 2 — mag=cercano min=cercano wrap_t=3 wrap_s=3 mip=cercano

##### `TEXUNIT1_TYPE` — 1 valores distintos

- `00000000` × 2547 — formato RGBA8

##### `LIGHTING_CONFIG0` — 1 valores distintos

- `00000400` × 4579

##### `TEXUNIT2_PARAM` — 6 valores distintos

- `00002206` × 634 — mag=lineal min=lineal wrap_t=2 wrap_s=2 mip=cercano
- `00002200` × 338 — mag=cercano min=cercano wrap_t=2 wrap_s=2 mip=cercano
- `00000006` × 3 — mag=lineal min=lineal wrap_t=0 wrap_s=0 mip=cercano
- `00002306` × 3 — mag=lineal min=lineal wrap_t=3 wrap_s=2 mip=cercano
- `00000000` × 1 — mag=cercano min=cercano wrap_t=0 wrap_s=0 mip=cercano
- `00002006` × 1 — mag=lineal min=lineal wrap_t=0 wrap_s=2 mip=cercano

##### `TEXUNIT2_TYPE` — 1 valores distintos

- `00000000` × 980 — formato RGBA8

## ApÃ©ndice B â€” salida de `pica_cmd.py codigo`

#### Cabeceras PICA cargadas como literal en .text: 302 distintas

- `FINALIZE` (0x010): 003F0010×2 (p.ej. 0x0018B1B0), 000F0010×3 (p.ej. 0x0024A25C)
- `FACECULLING_CONFIG` (0x040): 000F0040×5 (p.ej. 0x001084E0), 003F0040×3 (p.ej. 0x00109AC8)
- `VIEWPORT_WIDTH` (0x041): 000F0041×2 (p.ej. 0x00210F30), 803F0041×1 (p.ej. 0x0029F0C4)
- `VIEWPORT_INVW` (0x042): 000F0042×1 (p.ej. 0x003381D4)
- `VIEWPORT_HEIGHT` (0x043): 000F0043×2 (p.ej. 0x00210F94)
- `VIEWPORT_INVH` (0x044): 000F0044×1 (p.ej. 0x003381E8), 003F0044×1 (p.ej. 0x003720BC)
- `SH_OUTMAP_TOTAL` (0x04F): 000F004F×1 (p.ej. 0x001EF364)
- `SH_OUTMAP_O0` (0x050): 000F0050×1 (p.ej. 0x001EF380)
- `SH_OUTATTR_MODE` (0x064): 003F0064×7 (p.ej. 0x001B6158), 000F0064×1 (p.ej. 0x001EF518)
- `SCISSORTEST_MODE` (0x065): 000F0065×3 (p.ej. 0x00108990), 802F0065×1 (p.ej. 0x003379BC)
- `SCISSORTEST_POS` (0x066): 000F0066×3 (p.ej. 0x001089B0)
- `SCISSORTEST_DIM` (0x067): 000F0067×3 (p.ej. 0x001089D0)
- `VIEWPORT_XY` (0x068): 003F0068×1 (p.ej. 0x001B61E4), 000F0068×4 (p.ej. 0x00211120)
- `DEPTHMAP_ENABLE` (0x06D): 000F006D×1 (p.ej. 0x00109D60)
- `RENDERBUF_DIM` (0x06E): 000F006E×2 (p.ej. 0x00210CD8)
- `SH_OUTATTR_CLOCK` (0x06F): 000F006F×1 (p.ej. 0x00108B04)
- `TEXUNIT_CONFIG` (0x080): 00020080×1 (p.ej. 0x00103094), 00420080×1 (p.ej. 0x001046F8), 000E0080×1 (p.ej. 0x00107EAC)
- `TEXUNIT0_BORDER_COLOR` (0x081): 000F0081×2 (p.ej. 0x002EB16C)
- `TEXUNIT0_DIM` (0x082): 00010082×2 (p.ej. 0x001056AC), 00130082×1 (p.ej. 0x001F2FC0), 000D0082×1 (p.ej. 0x001F3078)
- `TEXUNIT0_PARAM` (0x083): 000F0083×2 (p.ej. 0x002CB1D8)
- `TEXUNIT0_LOD` (0x084): 00020084×1 (p.ej. 0x00109A8C), 001F0084×1 (p.ej. 0x00296F1C), 001E0084×1 (p.ej. 0x00296F68)
- `TEXUNIT0_ADDR1` (0x085): 000F0085×2 (p.ej. 0x002CB134)
- `TEXUNIT0_ADDR2` (0x086): 000F0086×1 (p.ej. 0x00337C2C)
- `TEXUNIT0_ADDR3` (0x087): 000F0087×1 (p.ej. 0x00337C08)
- `TEXUNIT0_ADDR4` (0x088): 00210088×9 (p.ej. 0x00234100), 003C0088×1 (p.ej. 0x00385E90)
- `TEXUNIT0_SHADOW` (0x08B): 000F008B×1 (p.ej. 0x00109FD8)
- `TEXUNIT0_TYPE` (0x08E): 000F008E×4 (p.ej. 0x00211AE8)
- `LIGHTING_ENABLE0` (0x08F): 000F008F×1 (p.ej. 0x001EEA8C), 0001008F×1 (p.ej. 0x002F420C)
- `TEXUNIT1_BORDER_COLOR` (0x091): 000F0091×1 (p.ej. 0x00337D04)
- `TEXUNIT1_PARAM` (0x093): 000F0093×1 (p.ej. 0x00337D88)
- `TEXUNIT1_ADDR` (0x095): 000F0095×1 (p.ej. 0x00337E5C)
- `TEXUNIT1_TYPE` (0x096): 000F0096×1 (p.ej. 0x00337E6C)
- `TEXUNIT2_BORDER_COLOR` (0x099): 000F0099×1 (p.ej. 0x00337F0C)
- `TEXUNIT2_PARAM` (0x09B): 0004009B×1 (p.ej. 0x00287DEC), 000F009B×1 (p.ej. 0x00337F90)
- `TEXUNIT2_LOD` (0x09C): 0043009C×2 (p.ej. 0x0011D3C8)
- `TEXUNIT2_ADDR` (0x09D): 000F009D×1 (p.ej. 0x00338064)
- `TEXUNIT2_TYPE` (0x09E): 000F009E×1 (p.ej. 0x00338074)
- `TEXUNIT3_PROCTEX0` (0x0A8): 003F00A8×1 (p.ej. 0x001A51F8), 003C00A8×1 (p.ej. 0x00385EA8)
- `TEXUNIT3_PROCTEX4` (0x0AC): 003F00AC×2 (p.ej. 0x0032E048)
- `PROCTEX_LUT` (0x0AF): 000F00AF×20 (p.ej. 0x0037A7A0)
- `PROCTEX_LUT_DATA0` (0x0B0): 003F00B0×1 (p.ej. 0x001A508C), 003C00B0×1 (p.ej. 0x00373758)
- `PROCTEX_LUT_DATA4` (0x0B4): 003F00B4×2 (p.ej. 0x001A4FC4)
- `TEXENV0_SOURCE` (0x0C0): 003F00C0×2 (p.ej. 0x001A5054), 003C00C0×1 (p.ej. 0x003737F0)
- `TEXENV0_COMBINER` (0x0C2): 004B00C2×1 (p.ej. 0x00107D68), 000100C2×2 (p.ej. 0x001F1D4C), 000900C2×2 (p.ej. 0x001F1EFC)
- `TEXENV0_COLOR` (0x0C3): 000F00C3×5 (p.ej. 0x002E4A88)
- `TEXENV0_SCALE` (0x0C4): 003D00C4×1 (p.ej. 0x001A1554), 003F00C4×1 (p.ej. 0x001A506C), 000A00C4×2 (p.ej. 0x001F1F58)
- `TEXENV1_COLOR` (0x0CB): 000F00CB×1 (p.ej. 0x002B7B7C)
- `TEXENV2_SOURCE` (0x0D0): 004300D0×8 (p.ej. 0x0016FCE0), 003C00D0×1 (p.ej. 0x0038D74C)
- `TEXENV3_COLOR` (0x0DB): 000F00DB×2 (p.ej. 0x00215D30)
- `TEXENV_UPDATE_BUFFER` (0x0E0): 000400E0×1 (p.ej. 0x00190F14), 000500E0×6 (p.ej. 0x001914A0), 000100E0×1 (p.ej. 0x001EEB34)
- `FOG_COLOR` (0x0E1): 000F00E1×1 (p.ej. 0x00190F10)
- `FOG_LUT_INDEX` (0x0E6): 000F00E6×3 (p.ej. 0x002A8770)
- `FOG_LUT_DATA0` (0x0E8): 003F00E8×6 (p.ej. 0x001903F8)
- `FOG_LUT_DATA4` (0x0EC): 003F00EC×1 (p.ej. 0x0036A9F4)
- `TEXENV4_SOURCE` (0x0F0): 004300F0×1 (p.ej. 0x00170D10), 003F00F0×2 (p.ej. 0x0032C7D4), 003C00F0×1 (p.ej. 0x0038D76C)
- `TEXENV4_SCALE` (0x0F4): 003F00F4×1 (p.ej. 0x0036A860)
- `TEXENV5_COLOR` (0x0FB): 000F00FB×1 (p.ej. 0x00215C2C)
- `TEXENV_BUFFER_COLOR` (0x0FD): 000F00FD×2 (p.ej. 0x00220638)
- `COLOR_OPERATION` (0x100): 00050100×1 (p.ej. 0x001057B0), 00E40100×4 (p.ej. 0x00106914), 000F0100×1 (p.ej. 0x00107E3C)
- `BLEND_FUNC` (0x101): 000F0101×10 (p.ej. 0x00108520), 01010101×6 (p.ej. 0x0010C6E0)
- `LOGIC_OP` (0x102): 000F0102×3 (p.ej. 0x00108510), 00080102×2 (p.ej. 0x001F1EA4)
- `BLEND_COLOR` (0x103): 00E40103×1 (p.ej. 0x00109F40), 000F0103×2 (p.ej. 0x0021143C)
- `FRAGOP_ALPHA_TEST` (0x104): 000C0104×1 (p.ej. 0x00107DFC), 00030104×8 (p.ej. 0x00108564), 00010104×1 (p.ej. 0x001EE9DC)
- `STENCIL_TEST` (0x105): 000F0105×4 (p.ej. 0x001085A0), 00010105×1 (p.ej. 0x0038ED50)
- `STENCIL_OP` (0x106): 000F0106×3 (p.ej. 0x001085C4), 00070106×2 (p.ej. 0x001F1C90)
- `DEPTH_COLOR_MASK` (0x107): 000F0107×8 (p.ej. 0x00108634), 00030107×1 (p.ej. 0x00211148), 00020107×1 (p.ej. 0x002F4778)
- `FRAMEBUFFER_INVALIDATE` (0x110): 000F0110×5 (p.ej. 0x00210A54)
- `FRAMEBUFFER_FLUSH` (0x111): 000F0111×16 (p.ej. 0x00210A34)
- `COLORBUFFER_READ` (0x112): 000F0112×3 (p.ej. 0x00108B90), 80310112×1 (p.ej. 0x001EEA2C), 00010112×5 (p.ej. 0x0028A4C8)
- `COLORBUFFER_WRITE` (0x113): 000F0113×1 (p.ej. 0x00108B6C)
- `DEPTHBUFFER_READ` (0x114): 000F0114×1 (p.ej. 0x00108BAC), 003F0114×5 (p.ej. 0x001836E0), 00010114×3 (p.ej. 0x002EBF28)
- `DEPTHBUFFER_WRITE` (0x115): 000F0115×1 (p.ej. 0x00108BCC), 00010115×4 (p.ej. 0x002EA3F8)
- `DEPTHBUFFER_FORMAT` (0x116): 000F0116×3 (p.ej. 0x00210C1C)
- `COLORBUFFER_FORMAT` (0x117): 000F0117×2 (p.ej. 0x00210AF8)
- `EARLYDEPTH_TEST2` (0x118): 00010118×2 (p.ej. 0x001089F0), 003F0118×1 (p.ej. 0x00183564), 003C0118×1 (p.ej. 0x00380E20)
- `FRAMEBUFFER_BLOCK32` (0x11B): 000F011B×3 (p.ej. 0x00108A10), 0001011B×1 (p.ej. 0x002113C4)
- `DEPTHBUFFER_LOC` (0x11C): 003F011C×4 (p.ej. 0x0018308C), 000F011C×2 (p.ej. 0x00210C4C), 802F011C×1 (p.ej. 0x0033A82C)
- `COLORBUFFER_LOC` (0x11D): 000F011D×3 (p.ej. 0x00210B34)
- `FRAMEBUFFER_DIM` (0x11E): 000F011E×3 (p.ej. 0x00210CB0)
- `GAS_LIGHT_XY` (0x120): 003F0120×1 (p.ej. 0x00366DDC)
- `GAS_LUT_INDEX` (0x123): 000F0123×2 (p.ej. 0x0037B490)
- `GAS_LUT_DATA` (0x124): 003F0124×1 (p.ej. 0x00183308)
- `GAS_DELTAZ_DEPTH` (0x126): 00080126×3 (p.ej. 0x00108A80)
- `FRAGOP_SHADOW` (0x130): 000F0130×1 (p.ej. 0x0010A078), 003F0130×2 (p.ej. 0x00183348), 00420130×2 (p.ej. 0x0024056C)
- `LIGHT0_SPECULAR0` (0x140): 00010140×1 (p.ej. 0x00108834), 003F0140×2 (p.ej. 0x00183608), 00030140×1 (p.ej. 0x001F5C20)
- `LIGHT0_XY` (0x144): 803F0144×1 (p.ej. 0x00192320), 801F0144×1 (p.ej. 0x002A13D0)
- `LIGHT0_CONFIG` (0x149): 00010149×1 (p.ej. 0x002F45DC)
- `LIGHT0_ATTENUATION_BIAS` (0x14A): 8017014A×1 (p.ej. 0x00191E6C)
- `LIGHT2_SPECULAR0` (0x160): 00420160×3 (p.ej. 0x00106524), 003F0160×6 (p.ej. 0x001839A0)
- `LIGHT2_XY` (0x164): 003F0164×4 (p.ej. 0x00183C94)
- `LIGHT2_ATTENUATION_BIAS` (0x16A): 0115016A×1 (p.ej. 0x00233BCC)
- `LIGHT3_SPECULAR0` (0x170): 003F0170×4 (p.ej. 0x00212DE4)
- `LIGHT3_XY` (0x174): 003F0174×3 (p.ej. 0x00212DF4)
- `LIGHT4_SPECULAR0` (0x180): 003C0180×2 (p.ej. 0x001D13F0), 003F0180×3 (p.ej. 0x00212F20)
- `LIGHT4_XY` (0x184): 003D0184×1 (p.ej. 0x001A16F0), 003F0184×4 (p.ej. 0x00212F40)
- `LIGHT5_SPECULAR0` (0x190): 003F0190×1 (p.ej. 0x0036708C)
- `LIGHT5_DIFFUSE` (0x192): 01960192×1 (p.ej. 0x0028FE30)
- `LIGHT5_XY` (0x194): 01980194×1 (p.ej. 0x00290048)
- `LIGHT6_ATTENUATION_BIAS` (0x1AA): 003B01AA×1 (p.ej. 0x0033FB20)
- `LIGHTING_AMBIENT` (0x1C0): 003F01C0×2 (p.ej. 0x00243B08), 003C01C0×1 (p.ej. 0x00256B20), 000101C0×1 (p.ej. 0x0028FB74)
- `LIGHTING_NUM_LIGHTS` (0x1C2): 000101C2×1 (p.ej. 0x0025498C)
- `LIGHTING_CONFIG0` (0x1C3): 000F01C3×2 (p.ej. 0x002F4540)
- `LIGHTING_CONFIG1` (0x1C4): 000B01C4×1 (p.ej. 0x00192054), 000401C4×1 (p.ej. 0x002F453C)
- `LIGHTING_LUT_INDEX` (0x1C5): 000F01C5×15 (p.ej. 0x00108BE0)
- `LIGHTING_ENABLE1` (0x1C6): 000F01C6×1 (p.ej. 0x001EEAA0), 000101C6×1 (p.ej. 0x002F4210)
- `LIGHTING_LUTINPUT_ABS` (0x1D0): 003F01D0×1 (p.ej. 0x00243B10), 003C01D0×2 (p.ej. 0x002CD19C), 802F01D0×1 (p.ej. 0x002F5360)
- `LIGHTING_LIGHT_PERMUTATION` (0x1D9): 000F01D9×1 (p.ej. 0x00254990)
- `ATTRIBBUFFERS_LOC` (0x200): 800F0200×1 (p.ej. 0x00221710), 000F0200×2 (p.ej. 0x00378970), 802F0200×1 (p.ej. 0x00392E78)
- `ATTRIBBUFFERS_FORMAT_LOW` (0x201): 000F0201×4 (p.ej. 0x001EEAD0)
- `ATTRIBBUFFERS_FORMAT_HIGH` (0x202): 00010202×1 (p.ej. 0x00287DF0), 000F0202×2 (p.ej. 0x002B3C78)
- `ATTRIBBUFFER0_CONFIG1` (0x204): 00430204×1 (p.ej. 0x00170C50), 003C0204×2 (p.ej. 0x002CD1B0)
- `ATTRIBBUFFER5_CONFIG2` (0x214): 003C0214×2 (p.ej. 0x002CD1B4)
- `ATTRIBBUFFER11_OFFSET` (0x224): 003F0224×2 (p.ej. 0x0018B9C8)
- `INDEXBUFFER_CONFIG` (0x227): 000F0227×6 (p.ej. 0x00221494)
- `NUMVERTICES` (0x228): 003C0228×1 (p.ej. 0x00135924), 000F0228×9 (p.ej. 0x002214AC)
- `GEOSTAGE_CONFIG` (0x229): 000B0229×1 (p.ej. 0x00108720), 000A0229×1 (p.ej. 0x001EF1E8), 00080229×1 (p.ej. 0x001EF3AC)
- `VERTEX_OFFSET` (0x22A): 000F022A×1 (p.ej. 0x0038F5D8)
- `DRAWARRAYS` (0x22E): 000F022E×1 (p.ej. 0x0038F610)
- `DRAWELEMENTS` (0x22F): 000F022F×2 (p.ej. 0x00221498)
- `VTX_FUNC` (0x231): 000F0231×4 (p.ej. 0x002EA648)
- `FIXEDATTRIB_INDEX` (0x232): 803F0232×12 (p.ej. 0x001EEAFC), 000F0232×3 (p.ej. 0x003792CC)
- `FIXEDATTRIB_DATA0` (0x233): 802F0233×1 (p.ej. 0x00282310)
- `CMDBUF_SIZE0` (0x238): 00430238×2 (p.ej. 0x00186228), 804F0238×1 (p.ej. 0x001DC640), 003C0238×1 (p.ej. 0x00357488)
- `VSH_NUM_ATTR` (0x242): 000F0242×1 (p.ej. 0x001087C0), 00010242×3 (p.ej. 0x00221534)
- `VSH_COM_MODE` (0x244): 00010244×7 (p.ej. 0x001086DC)
- `START_DRAW_FUNC0` (0x245): 00010245×7 (p.ej. 0x001086BC), 000F0245×1 (p.ej. 0x002EB074)
- `VSH_OUTMAP_TOTAL1` (0x24A): 000F024A×1 (p.ej. 0x001087E0)
- `VSH_OUTMAP_TOTAL2` (0x251): 000F0251×1 (p.ej. 0x00108760)
- `GSH_MISC0` (0x252): 000F0252×2 (p.ej. 0x00108740)
- `GEOSTAGE_CONFIG2` (0x253): 00010253×5 (p.ej. 0x001087A0), 00030253×1 (p.ej. 0x001EF200), 00020253×1 (p.ej. 0x00220A0C)
- `GSH_MISC1` (0x254): 000F0254×1 (p.ej. 0x00108780), 00010254×1 (p.ej. 0x001EF2DC)
- `PRIMITIVE_CONFIG` (0x25E): 0005025E×1 (p.ej. 0x00108800), 0001025E×1 (p.ej. 0x001EF350), 0008025E×13 (p.ej. 0x001EF544)
- `RESTART_PRIMITIVE` (0x25F): 000F025F×4 (p.ej. 0x00221480)
- `GSH_BOOLUNIFORM` (0x280): 000F0280×1 (p.ej. 0x00220904), 00030280×1 (p.ej. 0x002212A8)
- `GSH_INPUTBUFFER_CONFIG` (0x289): 00080289×1 (p.ej. 0x00108704), 000B0289×2 (p.ej. 0x001EF228)
- `GSH_ENTRYPOINT` (0x28A): 000F028A×1 (p.ej. 0x001EF204), 000C028A×1 (p.ej. 0x0038F750)
- `GSH_ATTRIBUTES_PERMUTATION_LOW` (0x28B): 801F028B×1 (p.ej. 0x0029EA34), 000F028B×5 (p.ej. 0x00378A40)
- `GSH_ATTRIBUTES_PERMUTATION_HIGH` (0x28C): 000F028C×4 (p.ej. 0x00378A64), 003C028C×1 (p.ej. 0x00384E58)
- `GSH_CODETRANSFER_END` (0x28F): 000F028F×2 (p.ej. 0x00220880)
- `GSH_FLOATUNIFORM_INDEX` (0x290): 000F0290×5 (p.ej. 0x00108C48), 003D0290×1 (p.ej. 0x001A249C), 804F0290×10 (p.ej. 0x0022125C)
- `GSH_FLOATUNIFORM_DATA0` (0x291): 00BF0291×1 (p.ej. 0x0024D5A0), 00FF0291×1 (p.ej. 0x0024D5C0)
- `GSH_FLOATUNIFORM_DATA3` (0x294): 003F0294×2 (p.ej. 0x001DD64C)
- `GSH_FLOATUNIFORM_DATA7` (0x298): 003F0298×2 (p.ej. 0x001CDD28)
- `GSH_CODETRANSFER_INDEX` (0x29B): 000F029B×5 (p.ej. 0x00108CFC)
- `GSH_CODETRANSFER_DATA0` (0x29C): 003F029C×2 (p.ej. 0x001DE29C), 003C029C×1 (p.ej. 0x00384E64)
- `GSH_CODETRANSFER_DATA4` (0x2A0): 003F02A0×2 (p.ej. 0x001EA640)
- `GSH_OPDESCS_INDEX` (0x2A5): 000F02A5×3 (p.ej. 0x00339BBC)
- `GSH_OPDESCS_DATA2` (0x2A8): 003F02A8×6 (p.ej. 0x001BD514)
- `GSH_OPDESCS_DATA6` (0x2AC): 003F02AC×1 (p.ej. 0x001EA5E0), 003C02AC×1 (p.ej. 0x00384E70)
- `VSH_BOOLUNIFORM` (0x2B0): 000F02B0×1 (p.ej. 0x002209C4), 003F02B0×1 (p.ej. 0x0025033C), 804F02B0×2 (p.ej. 0x0029EBB4)
- `VSH_INTUNIFORM_I0` (0x2B1): 000F02B1×1 (p.ej. 0x0022CCF8)
- `VSH_INTUNIFORM_I3` (0x2B4): 003F02B4×1 (p.ej. 0x001E9CC0)
- `VSH_INPUTBUFFER_CONFIG` (0x2B9): 000B02B9×3 (p.ej. 0x0022152C)
- `VSH_ENTRYPOINT` (0x2BA): 000F02BA×1 (p.ej. 0x001EF3B0), 000C02BA×1 (p.ej. 0x0038F71C)
- `VSH_ATTRIBUTES_PERMUTATION_LOW` (0x2BB): 000F02BB×5 (p.ej. 0x00221540), 801F02BB×3 (p.ej. 0x0029E654)
- `VSH_ATTRIBUTES_PERMUTATION_HIGH` (0x2BC): 000F02BC×4 (p.ej. 0x00378A0C), 003C02BC×1 (p.ej. 0x00384E7C)
- `VSH_CODETRANSFER_END` (0x2BF): 000F02BF×5 (p.ej. 0x00108D2C)
- `VSH_FLOATUNIFORM_INDEX` (0x2C0): 804F02C0×15 (p.ej. 0x00190FF0), 000F02C0×25 (p.ej. 0x00191234), 808F02C0×1 (p.ej. 0x002F4A08)
- `VSH_FLOATUNIFORM_DATA0` (0x2C1): 000F02C1×6 (p.ej. 0x00191110), 00BF02C1×11 (p.ej. 0x00191284), 00FF02C1×8 (p.ej. 0x00191B70)
- `VSH_CODETRANSFER_INDEX` (0x2CB): 000F02CB×5 (p.ej. 0x00108CC0)
- `VSH_CODETRANSFER_DATA0` (0x2CC): 003C02CC×1 (p.ej. 0x00384E88)
- `VSH_OPDESCS_INDEX` (0x2D5): 000F02D5×3 (p.ej. 0x00339B6C)
- `VSH_OPDESCS_DATA0` (0x2D6): 000F02D6×1 (p.ej. 0x002CA868)
- `VSH_OPDESCS_DATA6` (0x2DC): 004302DC×2 (p.ej. 0x001A1658), 003C02DC×1 (p.ej. 0x00384E94)

#### Corridas de 3+ comandos seguidos en .rodata/.data

- rodata 0x003A7A70: 5 comandos: LOGIC_OP, FACECULLING_CONFIG, FRAGOP_ALPHA_TEST, FRAGOP_ALPHA_TEST, TEXENV0_COLOR
- rodata 0x003A7AA0: 3 comandos: FACECULLING_CONFIG, TEXENV0_COLOR, TEXENV0_COLOR
- rodata 0x003A7D70: 18 comandos: COLOR_OPERATION, BLEND_FUNC, FRAGOP_ALPHA_TEST, DEPTH_COLOR_MASK, GAS_DELTAZ_DEPTH, STENCIL_TEST, TEXENV1_SOURCE, TEXENV3_SOURCE, TEXENV4_SOURCE, TEXENV5_SOURCE, TEXENV0_SCALE, TEXENV1_SCALE ...
- rodata 0x003A7E40: 14 comandos: TEXUNIT_CONFIG, TEXUNIT_CONFIG, TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV2_SOURCE, TEXENV3_SOURCE, TEXENV4_SOURCE, TEXENV5_SOURCE, TEXENV0_SCALE, TEXENV1_SCALE, TEXENV2_SCALE, TEXENV3_SCALE ...
- rodata 0x003A7EF0: 16 comandos: TEXENV0_SOURCE, TEXENV0_SOURCE, TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV2_SOURCE, TEXENV3_SOURCE, TEXENV4_SOURCE, TEXENV5_SOURCE, VSH_FLOATUNIFORM_INDEX, VSH_FLOATUNIFORM_DATA0, VSH_FLOATUNIFORM_INDEX, VSH_FLOATUNIFORM_DATA0 ...
- rodata 0x003A8070: 14 comandos: VSH_FLOATUNIFORM_INDEX, VSH_FLOATUNIFORM_DATA0, VIEWPORT_WIDTH, VIEWPORT_HEIGHT, VIEWPORT_INVW, VIEWPORT_INVH, VIEWPORT_XY, SCISSORTEST_MODE, SCISSORTEST_POS, SCISSORTEST_DIM, COLORBUFFER_FORMAT, COLORBUFFER_LOC ...
- rodata 0x003A812C: 11 comandos: VSH_INPUTBUFFER_CONFIG, VSH_NUM_ATTR, VSH_ATTRIBUTES_PERMUTATION_LOW, VSH_ATTRIBUTES_PERMUTATION_HIGH, GEOSTAGE_CONFIG, GEOSTAGE_CONFIG2, PRIMITIVE_CONFIG, RESTART_PRIMITIVE, FIXEDATTRIB_INDEX, GEOSTAGE_CONFIG2, START_DRAW_FUNC0
- rodata 0x003A8194: 14 comandos: START_DRAW_FUNC0, VTX_FUNC, GEOSTAGE_CONFIG2, FRAMEBUFFER_FLUSH, PRIMITIVE_CONFIG, PRIMITIVE_CONFIG, VSH_ENTRYPOINT, FIXEDATTRIB_INDEX, TEXENV0_SOURCE, TEXENV0_COLOR, TEXENV1_SOURCE, TEXENV1_COLOR ...
- rodata 0x003A82B4: 15 comandos: COLOR_OPERATION, BLEND_FUNC, DEPTH_COLOR_MASK, GAS_DELTAZ_DEPTH, STENCIL_TEST, EARLYDEPTH_TEST1, EARLYDEPTH_TEST2, FRAMEBUFFER_FLUSH, FRAMEBUFFER_INVALIDATE, COLORBUFFER_READ, COLORBUFFER_WRITE, DEPTHBUFFER_READ ...
- rodata 0x003A84E4: 9 comandos: TEXENV0_SOURCE, TEXENV0_SOURCE, TEXENV0_COLOR, TEXENV0_SOURCE, TEXENV0_COLOR, TEXENV0_SOURCE, FACECULLING_CONFIG, TEXENV0_COMBINER, TEXENV0_COLOR
- rodata 0x003A8588: 16 comandos: TEXUNIT_CONFIG, TEXUNIT_CONFIG, GEOSTAGE_CONFIG, GEOSTAGE_CONFIG2, PRIMITIVE_CONFIG, RESTART_PRIMITIVE, INDEXBUFFER_CONFIG, NUMVERTICES, START_DRAW_FUNC0, DRAWELEMENTS, START_DRAW_FUNC0, VTX_FUNC ...
- rodata 0x003AED30: 7 comandos: SH_OUTMAP_O0, FRAMEBUFFER_FLUSH, COLOR_OPERATION, BLEND_FUNC, FRAGOP_ALPHA_TEST, TEXENV5_SOURCE, SH_OUTATTR_CLOCK
- rodata 0x003AEDA0: 38 comandos: TEXUNIT_CONFIG, TEXENV3_OPERAND, TEXENV4_OPERAND, TEXENV3_OPERAND, TEXENV4_OPERAND, TEXENV3_SOURCE, TEXENV4_SOURCE, TEXENV3_SOURCE, TEXENV4_SOURCE, FRAMEBUFFER_FLUSH, FRAMEBUFFER_INVALIDATE, COLOR_OPERATION ...
- rodata 0x003AF098: 13 comandos: VSH_FLOATUNIFORM_INDEX, GEOSTAGE_CONFIG, VSH_INPUTBUFFER_CONFIG, VSH_ENTRYPOINT, VSH_OUTMAP_MASK, VSH_OUTMAP_TOTAL2, GSH_MISC0, VSH_NUM_ATTR, VSH_OUTMAP_TOTAL1, PRIMITIVE_CONFIG, SH_OUTMAP_TOTAL, SH_OUTATTR_MODE ...
- rodata 0x003B3224: 3 comandos: ATTRIBBUFFERS_FORMAT_HIGH, BLEND_FUNC, ATTRIBBUFFERS_FORMAT_HIGH
- rodata 0x003B348C: 4 comandos: ATTRIBBUFFERS_FORMAT_HIGH, ATTRIBBUFFERS_FORMAT_HIGH, BLEND_FUNC, ATTRIBBUFFERS_FORMAT_HIGH
- rodata 0x003B65FC: 16 comandos: GSH_MISC0, GSH_MISC1, GEOSTAGE_CONFIG, GSH_INPUTBUFFER_CONFIG, VSH_OUTMAP_MASK, VSH_OUTMAP_TOTAL2, VSH_OUTMAP_TOTAL1, PRIMITIVE_CONFIG, SH_OUTMAP_TOTAL, SH_OUTMAP_O0, SH_OUTATTR_MODE, SH_OUTATTR_CLOCK ...
- rodata 0x003B891C: 3 comandos: TEXENV2_SCALE, TEXENV3_SCALE, TEXENV4_SOURCE
- rodata 0x003E0AB0: 3 comandos: EARLYDEPTH_FUNC, SH_OUTMAP_O3, EARLYDEPTH_FUNC
- rodata 0x003E0B20: 3 comandos: VIEWPORT_XY, SH_OUTATTR_MODE, VIEWPORT_INVH
- rodata 0x003E0C1C: 3 comandos: VIEWPORT_XY, SH_OUTMAP_O3, SCISSORTEST_MODE
- rodata 0x003E0CCC: 3 comandos: EARLYDEPTH_FUNC, FRAGOP_CLIP_DATA1, SH_OUTMAP_O0
- data 0x003EF06C: 4 comandos: COLOR_OPERATION, GEOSTAGE_CONFIG, GEOSTAGE_CONFIG2, PRIMITIVE_CONFIG
- data 0x003F0780: 28 comandos: TEXENV5_SOURCE, TEXENV3_SOURCE, TEXENV4_SOURCE, TEXENV5_SOURCE, TEXUNIT0_DIM, TEXUNIT0_ADDR1, TEXUNIT0_TYPE, TEXUNIT0_PARAM, TEXUNIT1_DIM, TEXUNIT1_ADDR, TEXUNIT1_TYPE, TEXUNIT1_PARAM ...
- data 0x003F09B4: 56 comandos: TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV0_SOURCE, TEXENV1_SOURCE, TEXENV0_SOURCE, TEXENV1_SOURCE ...
- data 0x003F1220: 24 comandos: FRAMEBUFFER_FLUSH, FRAMEBUFFER_INVALIDATE, VIEWPORT_WIDTH, VIEWPORT_XY, SCISSORTEST_MODE, DEPTHMAP_ENABLE, DEPTHMAP_SCALE, DEPTHMAP_OFFSET, FACECULLING_CONFIG, STENCIL_TEST, DEPTH_COLOR_MASK, COLORBUFFER_READ ...
