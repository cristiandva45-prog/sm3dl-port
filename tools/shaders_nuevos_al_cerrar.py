r"""(S2, 9 oct 2026) Lo corre JUGAR_D3D12.bat al CERRAR el juego: si la partida dejo PS sin DXIL en
extraido\shaders\desconocidos_d3d12\ (los vuelca D1 al caer al uber, que es lento), los convierte e instala con
`precompilar_d3d12.py desconocidos` (F1: instala atomico y, si algo falla, no cambia nada) para que la proxima partida
ya los tenga. El dueno no corre nada a mano.

  py -I tools\shaders_nuevos_al_cerrar.py

- Sin desconocidos: no imprime nada ni escribe log (sale en ~50 ms).
- Con desconocidos: un mensaje corto, precompilar en un proceso hijo con prioridad BAJA (BELOW_NORMAL), salida completa
  agregada a sesion_juego\jugar\shaders_nuevos.txt, y un resumen de una linea. Compara la cache (nombre+tamano+fecha)
  antes/despues: si fallo, dice si quedo intacta (deberia, por F1) o avisa fuerte si cambio.
- Nunca devuelve error al .bat (sale 0 siempre): una falla aqui no puede romper el cierre del juego.
- Prueba sin tocar lo real: SM3DL_SHADERS_PRUEBA=<carpeta> con desconocidos\ cache\ partida\ archivo\ trabajo\ adentro;
  el log va a <carpeta>\shaders_nuevos.txt. (Ver agentes_dx12\S2.md.)
"""
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRECOMP = os.path.join(RAIZ, "tools", "precompilar_d3d12.py")
BAJA = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
PATRON = re.compile(r"F_[0-9A-F]{8}\.glsl")
CANDADO_MAX_S = 15 * 60   # un candado mas viejo que esto es de una corrida que murio (ventana cerrada a medias)


def rutas():
    p = os.environ.get("SM3DL_SHADERS_PRUEBA")
    if p:
        p = os.path.abspath(p)
        d = {k: os.path.join(p, k) for k in ("desconocidos", "cache", "partida", "archivo", "trabajo")}
        return d, os.path.join(p, "shaders_nuevos.txt"), True
    sh = os.path.join(RAIZ, "extraido", "shaders")
    d = {"desconocidos": os.path.join(sh, "desconocidos_d3d12"), "cache": os.path.join(sh, "cache_d3d12")}
    return d, os.path.join(RAIZ, "sesion_juego", "jugar", "shaders_nuevos.txt"), False


def foto(carpeta):
    if not os.path.isdir(carpeta):
        return None
    out = {}
    for f in os.listdir(carpeta):
        st = os.stat(os.path.join(carpeta, f))
        out[f] = (st.st_size, st.st_mtime_ns)
    return out


def main():
    d, log, prueba = rutas()
    desc = d["desconocidos"]
    n = len([f for f in os.listdir(desc) if PATRON.fullmatch(f)]) if os.path.isdir(desc) else 0
    if n == 0:
        return
    os.makedirs(os.path.dirname(log), exist_ok=True)
    candado = log + ".candado"
    try:   # dos ventanas cerradas a la vez no deben convertir lo mismo dos veces
        if os.path.exists(candado) and time.time() - os.path.getmtime(candado) < CANDADO_MAX_S:
            print(f"Ya se estan preparando efectos nuevos en otra ventana; estos {n} quedan para la proxima vez.")
            return
        open(candado, "w").close()
    except OSError:
        pass
    seg = 15 + n // 2   # medido F1: ~10-15 s de inventario + ~0,35 s por PS con 2 hilos
    print(f"Preparando {n} efecto{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''} para la proxima vez... "
          f"(menos de {max(1, -(-seg // 60))} min; deja esta ventana abierta, se cierra sola)", flush=True)
    cmd = [sys.executable, "-I", PRECOMP, "desconocidos", "--hilos", "2"]
    if prueba:
        cmd += ["--desconocidos", d["desconocidos"], "--dest", d["cache"], "--partida", d["partida"],
                "--archivo", d["archivo"], "--trabajo", d["trabajo"]]
    antes = foto(d["cache"])
    t0 = time.perf_counter()
    rc, salida = -1, ""
    try:
        r = subprocess.run(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           creationflags=BAJA, timeout=30 * 60)
        rc, salida = r.returncode, r.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        salida = (e.stdout or b"").decode("utf-8", "replace") + "\n[S2] se corto: mas de 30 min\n"
    except Exception as e:  # noqa: BLE001 - cualquier cosa aqui se reporta, no rompe el cierre
        salida = f"[S2] no se pudo lanzar: {e!r}\n"
    dt = time.perf_counter() - t0
    despues = foto(d["cache"])
    intacta = antes == despues
    quedan = len([f for f in os.listdir(desc) if PATRON.fullmatch(f)]) if os.path.isdir(desc) else 0
    ok = rc == 0 and quedan == 0
    try:
        with open(log, "a", encoding="utf-8", newline="\n") as fl:
            fl.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {n} PS en {desc}\n$ {' '.join(cmd)}\n{salida}")
            fl.write(f"[S2] rc={rc} ({dt:.0f} s, prioridad baja); quedan {quedan} sin convertir; cache "
                     f"{'sin cambios' if intacta else 'ACTUALIZADA'} ({len(despues or {})} archivos)\n\n")
    except OSError:
        pass
    try:
        os.remove(candado)
    except OSError:
        pass
    rel = os.path.relpath(log, RAIZ)
    if ok and intacta:
        print(f"Listo: esos {n} efectos ya estaban preparados (solo se archivaron).")
    elif ok:
        print(f"Listo: {n} efecto{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''} instalado{'s' if n != 1 else ''} "
              f"({dt:.0f} s). La proxima partida va a ir mas fluida.")
    elif intacta:
        print(f"No se pudieron preparar los efectos nuevos (detalle en {rel}). No pasa nada: el juego queda igual que "
              f"antes y se vuelve a intentar al cerrar la proxima partida.")
    else:
        print(f"ATENCION: fallo la preparacion de efectos y la cache cambio. Detalle en {rel}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"No se pudieron preparar los efectos nuevos ({e}). El juego queda igual que antes.")
    sys.exit(0)
