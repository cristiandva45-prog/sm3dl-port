# Decompilación a mano verificada — Super Mario 3D Land

Decompilación **funcional**: cada función de `src/` hace lo mismo que la original, comprobado con pruebas diferenciales. No es *matching* (byte a byte): no tenemos el compilador de Nintendo (ARMCC).

## Cómo se trabaja
1. Leer el ensamblador de la función (`py -I tools\dis.py <dir>`); el C de Ghidra solo es referencia: **se equivoca en detalles** (p. ej. `^1` vs `!`, comparaciones de float hechas sobre los bits).
2. Escribirla en C en `src/` con la dirección original en un comentario. Llamar a las originales por su nombre de `extraido\simbolos.txt` o como `FUN_xxxxxxxx`.
3. Registrar el nombre en `extraido\simbolos.txt` (el verificador compara contra esa dirección).
4. `py -I decomp\build.py` — compila con Zig para ARM11 (arm1176jzf-s, VFPv2, hard-float, `-ffp-contract=off`) y enlaza en 0x01000000; las llamadas a originales van a su dirección real en code.bin.
5. Escribir un generador en `verificar.py` (`CASOS`) y correr `py -I decomp\verificar.py <nombre> -n 3000`.
6. **Sabotear** (`sabotear.py`): meter los errores típicos y exigir que el verificador los detecte. Un verde sin sabotaje no vale.

## El verificador (`verificar.py`)
- Carga code.bin y decomp.bin en el mismo Unicorn (FPSCR = RunFast como el 3DS).
- Corre original y decompilada con la MISMA entrada al azar (floats raros incluidos: ±0, inf, NaN, desnormales, valores a ±4 ulps de un umbral, sumas que se cancelan).
- Compara: r0, s0, toda la memoria de prueba, `.data/.bss` del juego y **el orden y los argumentos de cada llamada** (métodos virtuales "espía" y stubs "con guion").

## Estado (7 oct 2026)
- 17 funciones verificadas (3.000 pruebas c/u): piloto (15, de 2 a 44 instrucciones) + tanda 2 (`Kuribo_attackSensor` 65 instr., `PlayerActionCondBrake_evaluate` 126 instr.).
- Sabotaje: 12/12 en el piloto (tras corregir 2 puntos ciegos del generador) y 8/8 en la tanda 2.
- Lecciones del sabotaje: (a) dos "sabotajes" eran transformaciones equivalentes (`a+b` = `b+a` en float); (b) los umbrales exactos no salen al azar: hay que barrer ulps; (c) los stubs deben tener dirección FIJA, no la que enlazó la versión compilada.
