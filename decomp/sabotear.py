"""Prueba del verificador: mete errores tipicos de decompilacion a ojo y exige que verificar.py los detecte.

Uso: py -I decomp\\sabotear.py
Cada sabotaje se aplica sobre una copia de src/piloto.c, se compila y se verifica SOLO esa funcion.
El original se restaura siempre (try/finally). Un sabotaje NO detectado = el verificador tiene un punto ciego.
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(AQUI, "src", "piloto.c")
SRC2 = os.path.join(AQUI, "src", "tanda2.c")
SABOTAJES = [
    ("setFlagBit", "*p = *p | (n >= 32 ? 0u : 1u << n);", "*p = *p | (1u << (n & 31));",
     "olvidar que ARM da 0 al desplazar >= 32"),
    ("PlayerActionCondNot_evaluate", "return EVALUAR(CAMPO(Objeto *, self, 4)) ^ 1;",
     "return !EVALUAR(CAMPO(Objeto *, self, 4));", "usar ! en vez de ^1"),
    ("PlayerActionCondAnd_evaluate", "r = (EVALUAR(CAMPO(Objeto *, elem, 0)) & r) != 0;",
     "r = r && EVALUAR(CAMPO(Objeto *, elem, 0));", "AND con cortocircuito"),
    ("PlayerActionCondOr_evaluate", "r = (EVALUAR(CAMPO(Objeto *, elem, 0)) | r) != 0;",
     "r = r || (EVALUAR(CAMPO(Objeto *, elem, 0)) != 0);", "OR con cortocircuito (deja de evaluar al ser verdadero)"),
    ("isActorRising", "return d > 0.0f;", "return d >= 0.0f;", ">= en vez de >"),
    ("isActorRising", "f32 d = arriba->x * vel->x;\n    d = d + arriba->y * vel->y;\n    d = d + arriba->z * vel->z;",
     "f32 d = arriba->x * vel->x + (arriba->y * vel->y + arriba->z * vel->z);", "asociar la suma distinto (float)"),
    ("PlayerActionExecutor_selectNext", "it = CAMPO(u8 *, it, 4);", "it = CAMPO(u8 *, it, 0);",
     "seguir el enlace equivocado"),
    ("PlayerCollider_isTouchCode", "if (FUN_0026dcf0(iter)) {", "{", "no preguntar si el contacto es valido"),
    ("PlayerActionCondJumpOnGround_evaluate", "if (isActorRising(CAMPO(u8 *, self, 0x8)) != 0)\n        return 0;\n    return",
     "return", "olvidar la condicion de 'no subiendo'"),
    ("PlayerActionCondStopped_evaluate", "return largo.i <= 0x3DCCCCCD;", "return largo.f < 0.1f;",
     "< en vez de <= en el umbral"),
    ("PlayerInput_isJumpTriggerBuffered", "CAMPO(u32, in, 0x34) < 5", "CAMPO(s32, in, 0x34) < 5",
     "comparar con signo en vez de sin signo"),
    ("PlayerInput_isJumpHold", "return CAMPO(s8, in, 0x30);", "return CAMPO(u8, in, 0x30);",
     "byte sin signo en vez de con signo"),
]

SABOTAJES_T2 = [
    ("Kuribo_attackSensor", "sendMsgPush(otro, mio);\n        if (!sendMsgEnemyAttack(otro, mio))",
     "if (!sendMsgEnemyAttack(otro, mio))", "olvidar el empujon antes del dano"),
    ("Kuribo_attackSensor", "if (isNerve(self, NrvKuribo_PopOut))\n            return;\n", "",
     "olvidar que saliendo disparado no empuja"),
    ("Kuribo_attackSensor", "isNerve(self, NrvKuribo_PressDown) || isNerve(self, NrvKuribo_BlowDown)",
     "isNerve(self, NrvKuribo_BlowDown) || isNerve(self, NrvKuribo_PressDown)", "preguntar los nervios en otro orden"),
    ("PlayerActionCondBrake_evaluate", "    isNearZeroVec3(&stick);\n", "", "no normalizar el stick"),
    ("PlayerActionCondBrake_evaluate", "if (bits(d1) >= 0x3F3504F3", "if (bits(d1) >= 0x3F000000", "umbral 0.5 en vez de cos45"),
    ("PlayerActionCondBrake_evaluate", "CAMPO(s32, self, 0x10) = cont - 1;", "CAMPO(s32, self, 0x10) = cont;",
     "no descontar el contador"),
    ("PlayerActionCondBrake_evaluate", "if (!(rapidez < minimo)) {", "if (rapidez >= minimo) {",
     "NaN: !(a<b) no es lo mismo que a>=b"),
    ("PlayerActionCondBrake_evaluate", "&& casi_frente == 0) {\n        if (cont", ") {\n        if (cont",
     "olvidar casi_frente en el final"),
]


def correr(*args):
    return subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True)


def main():
    tanda2 = "--t2" in sys.argv
    global SRC, SABOTAJES
    if tanda2:
        SRC, SABOTAJES = SRC2, SABOTAJES_T2
    original = open(SRC, encoding="utf-8").read()
    respaldo = SRC + ".respaldo"
    shutil.copyfile(SRC, respaldo)
    detectados = 0
    try:
        for func, viejo, nuevo, que in SABOTAJES:
            assert viejo in original, f"sabotaje desactualizado: {func}: {viejo[:40]}"
            open(SRC, "w", encoding="utf-8").write(original.replace(viejo, nuevo, 1))
            b = correr(os.path.join(AQUI, "build.py"))
            if b.returncode != 0:
                print(f"??  {func}: no compila el sabotaje ({que})\n{b.stdout}{b.stderr}")
                continue
            v = correr(os.path.join(AQUI, "verificar.py"), func, "-n", "2000")
            ok = "FALLA" in v.stdout
            detectados += ok
            linea = next((l for l in v.stdout.splitlines() if l.startswith(("FALLA", "OK"))), v.stdout[-200:])
            print(f"{'DETECTADO ' if ok else 'NO VISTO  '} {func}: {que}\n    {linea[:150]}")
    finally:
        shutil.copyfile(respaldo, SRC)
        os.remove(respaldo)
        correr(os.path.join(AQUI, "build.py"))
    print(f"\n{detectados}/{len(SABOTAJES)} sabotajes detectados")


if __name__ == "__main__":
    main()
