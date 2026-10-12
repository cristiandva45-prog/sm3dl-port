# Colisión (KCL + PA) — Super Mario 3D Land

Herramientas: `tools\kcl.py` (pieza → OBJ, lote `--todo`), `tools\nivel_colision.py` (nivel → OBJ), `tools\colision_previa.py` (previas PNG con Pillow).
Salidas: `extraido\colision\piezas\*.obj/.mtl` (577), `extraido\colision\resumen_piezas.tsv`, `extraido\colision\AquariumSwimStageMap1.obj`, `extraido\colision\_previas\*.png`.

## KCL (verificado contra los bytes, little-endian)
Ejemplo `AquariumSwimStepA.kcl` (52.994 bytes): `38 00 00 00 | 30 08 00 00 | 64 7B 00 00 | 34 A7 00 00 | 40.0 | (-1104.8, -1670.6, -2570.6) | F000FFFF F000FFFF 00E0FFFF | 11 1 2`

| off | tipo | campo |
|---|---|---|
| 0x00 | u32 | offset posiciones (siempre 0x38 = fin de cabecera), vec3 f32 |
| 0x04 | u32 | offset normales, vec3 f32 |
| 0x08 | u32 | offset prismas **− 0x10** (prismas 1-indexados: el primero está en +0x10; los 16 bytes en el offset son la cola de las normales) |
| 0x0C | u32 | offset octree (fin de los prismas) |
| 0x10 | f32 | grosor del prisma (40.0) |
| 0x14 | vec3 f32 | mínimo del área (origen del octree) |
| 0x20 | u32×3 | máscaras X, Y, Z |
| 0x2C | u32×3 | shifts (coord, y, z) |

Conteos cuadran: posiciones = (nrm−pos)/12 = 170, normales = (pri+0x10−nrm)/12 = 2459, prismas = (oct−pri−0x10)/16 = 700; índices máx. usados 169 y 2458 → exacto.
Prisma (0x10): `f32 altura, u16 i_pos, u16 i_normal_cara, u16 i_arista_A, u16 i_arista_B, u16 i_arista_C, u16 atributo`. Mismo esquema que Mario Kart Wii / Galaxy, pero LE.
Reconstrucción (la fórmula del encargo funciona tal cual): CrossA=A×N, CrossB=B×N, V1=P, V2=P+CrossB·L/(CrossB·C), V3=P+CrossA·L/(CrossA·C). Se reordena V2/V3 si la normal geométrica no coincide con N (para que el OBJ quede con winding consistente).
Lote: **577 KCL, 158.970 triángulos, 0 errores**; 63 prismas degenerados (CrossX·C≈0, triángulos sin área) se omiten. Mallas continuas: StepA 653 vértices soldados para 700 triángulos; 534/577 piezas con ≥50 % de aristas compartidas (las que no, son planos/quads sueltos).

## PA (descifrado)
Es una tabla **BCSV/JMap de Galaxy** en little-endian:
- Cabecera: `u32 n_filas, u32 n_campos, u32 off_datos, u32 tam_fila` (StepA: 700, 5, 0x4C, 4).
- Campo (12 bytes): `u32 hash_nombre, u32 máscara, u16 offset_en_fila, u8 shift, u8 tipo (0 = entero)`.
- Hash JMap `h = h*31 + c`; nombres confirmados contra cadenas de `code.bin`: `Sound_code` (máscara 0x7F), `Floor_code` (0x1F80>>7), `Floor2_code` (0x7E000>>13), `Wall_code` (0x780000>>19), `Camera_through` (0x800000>>23). Los 577 .pa tienen exactamente estos 5 campos.
- **Relación con el KCL:** el `atributo` u16 del prisma es el índice de fila del .pa (en StepA los atributos son 0..699 = una fila por prisma; en 73 piezas el .pa tiene 1-5 filas de más). 0 atributos fuera de rango en las 577.
- Valores vistos: Floor_code {0, 1 (874 tris: ColNeedle, bordes de SkyLift, KoopaLavaTruckTowerOutside → probablemente daño/púas), 2 (721: LavaWheelBase, KoopaLava*, KoopaThirdLava → **lava**), 3 (14, CavePatanMain)}; Wall_code {0, 1 (UpUpLand, CaveClimbGoal, RopeClimb → probablemente pared escalable/agarrable)}; Sound_code 0-20 (material sonoro: 9 = SweetsScroll/MountainRope, 20 = SkyChikuwa…); Floor2_code y Camera_through siempre 0. Los significados de los números son **hipótesis por contexto**, no confirmados en el código.
- En el OBJ cada triángulo va a `usemtl S<sound>_F<floor>_F2<floor2>_W<wall>_C<cam>` con color estable en el .mtl.

## Transformación de los niveles
`v_mundo = pos + R · (escala ⊙ v_local)`, `R = Rz(dir_z)·Ry(dir_y)·Rx(dir_x)` en grados (X se aplica primero), mano derecha, Y arriba. Unidades del KCL = unidades de `pos_*` (bloque = 100; BlockBrick en rejilla de 100 encaja). Escala con determinante negativo invierte el winding.
Cómo se eligió el orden:
- Los ángulos tipo `(180, φ, 180)` (decomposición de una guiñada pura) solo salen con **Y como eje del medio** → ZYX o XYZ.
- `nivel_colision.py --probar-orden` (vértices de piezas con 2+ ejes girados que coinciden con vértices de otras piezas, en todos los StageMap): ZYX gana a XYZ en 5 de 6 casos discriminantes (BattleShipRollerSp HexaSmall 20 vs 0, SkyPatan2 PatanBoard 6/4/6 vs 0/0/4, SkyPatan1 13 vs 11); pierde en uno (BattleShipRoller HexaSmall 94 vs 45, pieza que rota en juego).
- Coincide con la convención de Galaxy (Whitehole: Rz·Ry·Rx). **Confianza media-alta**, no confirmado en el binario. Previas de contraste: `_previas\prueba_orden_SkyPatan2_{ZYX,XYZ}.png`.

## Nivel de prueba `AquariumSwimStageMap1`
72 objetos con colisión, 2.593 triángulos. Se omiten `AreaObjInfo`/`CameraAreaInfo`. Para cada objeto se usa el `.kcl` que se llama como su archivo (o el primero).
Previas: `AquariumSwimStageMap1.png`, `..._sin_muros.png`, `Aquarium_zoom_tramo_principal.png`, `Aquarium_zoom_sala_bonus.png`. Se ve: el pozo de inicio (StepA), el tramo de nado lateral (StepB) como un túnel continuo con WoodBox, TrampleSwitch y Dokan apoyados en su piso/cornisas, la meta (AquariumSwimGoal + PoleGoal) y la sala bonus (BonusRoomBrickA + bloques en rejilla de 100). Las zonas están separadas a propósito (se conectan por tuberías), no es un hueco de colocación.

## Qué falta
- **Pista desde el código (7 oct, `reportes\grafo.md`):** `FUN_00225498(colisionador, N)` recorre los contactos activos y compara el campo `+0xc` de la info de choque con N; en el grafo de Mario, desde Daño y desde Estatua, **N = 2 o 3 lleva a Morir**. Cuadra con Floor_code 2 = lava. Falta confirmar que `+0xc` sea exactamente Floor_code (leer dónde se llena esa info desde el `.pa`).
- Confirmar el orden de rotación (y Floor_code/Wall_code/Sound_code) en el código cuando se pueda usar Ghidra.
- Objetos con varios KCL por estado (KoopaSwitch `Onwait`/`Offwait_NoAction`, DossunTailBody/Roof…): hoy se usa solo el principal.
- Objetos con colisión que no viene de `ObjectData\<name>.szs` (si alguno usa `ModelName`/otro archivo) y colisiones generadas por código (cajas/esferas de actores) no aparecen.
- No se lee el octree (no hace falta para exportar; el port puede reconstruir su propia estructura de búsqueda).
- Piezas móviles (FallMapParts, rodillos, PatanBoard) se exportan en su pose inicial.
