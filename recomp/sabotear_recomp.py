"""Sabotaje del RECOMPILADOR: mete errores tipicos en el traductor o el runtime, regenera, verifica y
exige que el verificador los detecte. Restaura siempre los archivos.

Uso: py -I recomp\\sabotear_recomp.py
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
LOTE = "26EBE0 27DB90 27DBA0 277D5C 225458 1A9520 1B8B74 1A7288 18144C 225498 2D2C6C 2D3B34 326C54 326C78 326C44 30820C 2D3D58"
EXCLUIR = "26DD60,26DD4C,26DCF0,26DC94,26DC84,26E1D4,27B0F8,27A4D0,27A500,270620,2806A0,280608,27D540,279BC4,272C6C"
H, PY = os.path.join("runtime", "recomp.h"), "recomp.py"
SABOTAJES = [
    (H, "return add_f(c, a, ~b, cin);", "return add_f(c, a, ~b, 0);", "acarreo de la resta mal (cmp/sub)"),
    (PY, 'arm.ARM_CC_LS: "(!c->c || c->z)"', 'arm.ARM_CC_LS: "(!c->c && c->z)"', "condicion LS mal traducida"),
    (PY, 'arm.ARM_CC_GE: "(c->n == c->v)"', 'arm.ARM_CC_GE: "(c->n == c->z)"', "condicion GE mal traducida"),
    (H, "        return 0x7FC00000u; /* DN: NaN por defecto */", "        return b;", "no normalizar NaN (modo DN)"),
    (PY, '"ldrsb": "(u32)(s32)(s8)R8(a)"', '"ldrsb": "R8(a)"', "ldrsb sin extension de signo"),
    (H, "    if (s < 32) { *co = (v >> (32 - s)) & 1; return v << s; }",
     "    if (s <= 32) { *co = (v >> (32 - s)) & 1; return v << s; }", "lsl por registro con 32"),
    (PY, 'out.append(f"    if ({CC[i.cc]}) {{ " + " ".join(cuerpo) + " }")', 'out += ["    " + x for x in cuerpo]',
     "ignorar la condicion de las instrucciones"),
    (H, "    else if (a < b) { c->fn = 1;", "    else if (a <= b) { c->fn = 1;", "vcmp: igual tratado como menor"),
    (PY, 'cast = {"sxth": "(u32)(s32)(s16)"', 'cast = {"sxth": "(u32)(u16)"', "sxth sin signo"),
]


def correr(*a):
    return subprocess.run([sys.executable, "-I", *a], capture_output=True, text=True, cwd=os.path.dirname(AQUI))


def regenerar():
    return correr(os.path.join(AQUI, "recomp.py"), *LOTE.split(), "--cierre", "--excluir", EXCLUIR,
                  "-o", os.path.join(AQUI, "gen", "juego.c"))


NATIVO = "--nativo" in sys.argv


def main():
    vistos = 0
    for rel, viejo, nuevo, que in SABOTAJES:
        p = os.path.join(AQUI, rel)
        orig = open(p, encoding="utf-8").read()
        assert viejo in orig, f"sabotaje desactualizado: {que}"
        shutil.copyfile(p, p + ".respaldo")
        try:
            open(p, "w", encoding="utf-8").write(orig.replace(viejo, nuevo, 1))
            g = regenerar()
            if g.returncode:
                print(f"??  {que}: no regenera\n{g.stdout[-300:]}{g.stderr[-300:]}")
                continue
            if NATIVO:
                exe = subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-s",
                                      "-ffp-contract=off", "-fno-strict-aliasing", "-msse2", "-Wno-unused-label",
                                      "-Wno-unused-variable", "-Wno-parentheses-equality",
                                      "-I", os.path.join(AQUI, "runtime"), "-o", os.path.join(AQUI, "build", "anfitrion.exe"),
                                      os.path.join(AQUI, "gen", "juego.c"), os.path.join(AQUI, "runtime", "runtime.c"),
                                      os.path.join(AQUI, "runtime", "anfitrion_pipe.c")], capture_output=True, text=True)
                if exe.returncode:
                    print(f"??  {que}: el C saboteado no compila para x86")
                    continue
            v = correr(os.path.join(AQUI, "verificar_recomp.py" if NATIVO else "verificar_recomp_arm.py"), "-n", "600")
            fallas = [l for l in v.stdout.splitlines() if l.startswith("FALLA")]
            if "no compila" in v.stdout + v.stderr:
                print(f"??  {que}: el C saboteado no compila")
                continue
            vistos += bool(fallas)
            print(f"{'DETECTADO' if fallas else 'NO VISTO '}  {que}" + (f"\n    {fallas[0][:140]}" if fallas else ""))
        finally:
            shutil.copyfile(p + ".respaldo", p)
            os.remove(p + ".respaldo")
    regenerar()
    print(f"\n{vistos}/{len(SABOTAJES)} sabotajes del recompilador detectados")


if __name__ == "__main__":
    main()
