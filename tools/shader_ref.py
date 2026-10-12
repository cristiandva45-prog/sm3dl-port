"""Interprete de REFERENCIA del shader PICA200: la misma maquina de pilas que el hardware (y que Azahar):
un contador de programa y tres pilas (call, if, loop) que se cierran comparando con pc_viejo + 1.
No comparte el control de flujo con shader_glsl.py a proposito: ese estructura el programa en arbol; si los dos
dan lo mismo, la estructuracion es correcta. Comparten solo la aritmetica (tools\\pica_ops.py).
"""
import pica_ops


def cond(st, ins):
    x = ins["refx"] == st.cc[0]
    y = ins["refy"] == st.cc[1]
    return [x or y, x and y, x, y][ins["condop"]]


def correr(sh, entrada, st, max_pasos=100000):
    pc = entrada
    pila_call, pila_if, pila_loop = [], [], []
    pasos = 0
    while True:
        pasos += 1
        if pasos > max_pasos:
            raise RuntimeError("demasiados pasos")
        viejo = pc
        es_break = False
        ins = sh.instr(pc)
        op = ins["op"]
        if "desc" in ins:
            fuentes, m = sh.operandos(ins)
            st.ejecutar(op, ins.get("dst"), m, fuentes, ins)
        elif op == "end":
            return st
        elif op == "jmpc":
            if cond(st, ins):
                pc = ins["dst"] - 1
        elif op == "jmpu":
            if st.b[ins["uni"]] == (not (ins["num"] & 1)):
                pc = ins["dst"] - 1
        elif op in ("call", "callu", "callc"):
            si = op == "call" or (op == "callu" and st.b[ins["uni"]]) or (op == "callc" and cond(st, ins))
            if si:
                pila_call.append((ins["dst"] + ins["num"], pc + 1))
                pc = ins["dst"] - 1
        elif op in ("ifu", "ifc"):
            si = st.b[ins["uni"]] if op == "ifu" else cond(st, ins)
            if si:
                pila_if.append((ins["dst"], ins["dst"] + ins["num"]))
            else:
                pc = ins["dst"] - 1
        elif op == "loop":
            p = st.i[ins["uni"]]
            st.a[2] = p[1]
            pila_loop.append({"entrada": pc + 1, "fin": ins["dst"] + 1, "cuenta": p[0], "paso": p[2],
                              "previo": st.a[2]})
        elif op == "break":
            es_break = True
        elif op == "breakc":
            es_break = cond(st, ins)
        elif op == "nop":
            pass
        else:
            raise NotImplementedError(op)
        pc += 1
        sig = viejo + 1
        for k in range(4):
            if not pila_call or pila_call[-1][0] != sig:
                break
            if k < 3:
                pc = pila_call[-1][1]
                sig = pc
            pila_call.pop()
        if pila_if and pila_if[-1][0] == viejo + 1:
            pc = pila_if[-1][1]
            pila_if.pop()
        if pila_loop and (pila_loop[-1]["fin"] == viejo + 1 or es_break):
            lp = pila_loop[-1]
            st.a[2] = st.a[2] + lp["paso"]  # s32 en Azahar; el rango s8 se aplica al usarlo como indice
            if not es_break and lp["cuenta"]:
                lp["cuenta"] -= 1
                pc = lp["entrada"]
            else:
                pc = lp["fin"]
                if len(pila_loop) > 1:
                    st.a[2] = lp["previo"]
                pila_loop.pop()
