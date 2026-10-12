import os
R = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port"
p = os.path.join(R, r"recomp\sistema\stubs.c")
s = open(p, encoding="utf-8").read()
apt = open(os.path.join(R, r"agentes_noche\S\apt_nuevo.c"), encoding="utf-8").read()
cec = open(os.path.join(R, r"agentes_noche\S\cecd_nuevo.c"), encoding="utf-8").read()
apt = apt.replace("        if (n < 0x84) n = n;   /* el juego pidio menos: se devuelve lo que entra */\n", "")
apt = apt.replace("res = 0xC8A0CFF8u;   /* (descr. 1016?) el MAC no cuadra: datos no envueltos aqui */",
                  "res = 0xC9010401u;   /* como Horizon al fallar el descifrado: desc 1, PS(65), WrongArgument, Status */")
# cecd: Open de archivo = crear si la carpeta de arriba existe (Azahar abre con crear; sin carpeta del buzon falla)
viejo = """            if (t < 0) {
                if (modo & 4) { cecd_escribir(s->ruta, NULL, 0); t = 0; }   /* Azahar abre siempre con crear */
                else { cmd[1] = CECD_RES_NO_HAY; cmd[2] = 0; s->abierto = 0; break; }
            }"""
nuevo = """            if (t < 0) {   /* Horizon abre los archivos con "crear": falla solo si no existe la carpeta del buzon */
                char arriba[MAX_PATH]; snprintf(arriba, sizeof arriba, "%s", s->ruta);
                char *c = strrchr(arriba, '\\'); if (c) *c = 0;
                if (!fs_es_dir(arriba)) { cmd[1] = CECD_RES_NO_HAY; cmd[2] = 0; s->abierto = 0; }
                else { cecd_escribir(s->ruta, NULL, 0); t = 0; }
            }
            if (t >= 0) { cmd[2] = (u32)t; s->abierto = 1; }"""
assert cec.count(viejo) == 1
cec = cec.replace(viejo, nuevo)
cec = cec.replace("""            cmd[2] = (u32)t; s->abierto = 1;
        }
        if (sis_traza)""", """        }
        if (sis_traza)""")
assert "break; }" not in cec.split("case 0x0001")[1].split("case 0x0002")[0]
cec = cec.replace("""    case 0x000C: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetLastErrorCode */
    case 0x000D: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 1; return;   /* GetStatus: desconectado */""",
"""    case 0x000C: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetStatus: desconectado (Azahar dice internet) */
    case 0x000D: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetWifiStatus: sin red */""")
cec = cec.replace("    case 0x0018: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* CheckNew3DS: 3DS viejo */\n", "")
cec = cec.replace("    case 0x0006: ipc_respuesta(p, 3, 0, RES_OK); cmd[2] = 0; cmd[3] = 0; return;    /* GetMyFriendKey (sin cuenta) */",
                  "    case 0x0006: ipc_respuesta(p, 4, 0, RES_OK); return;                          /* GetMyPreference: privado, nada a la vista */")
# APT
i = s.index("/* ============================================================ APT:U */")
j = s.index("/* ============================================================ cfg:u */")
s = s[:i] + apt + s[j:]
# cecd viejo
i = s.index("static SisObj *cecd_evento;")
j = s.index("/* ============================================================ gsp::Gpu y hid:USER provisionales")
s = s[:i] + s[j:]
k = s.index("/* ============================================================ gsp::Gpu y hid:USER provisionales")
s = s[:k] + cec + s[k:]
s = s.replace("/* ============================================================ ndm:u, mic:u, cecd:u/s */", "/* ============================================================ ndm:u, mic:u */")
# mic StartSampling
v = "    case 0x0001: case 0x0002: case 0x0005: case 0x0008: case 0x000A: case 0x000C: case 0x000D: st_ok(p, 1); return;"
assert s.count(v) == 1
s = s.replace(v, "    case 0x0001: case 0x0002: case 0x0003: case 0x0005: case 0x0008: case 0x000A: case 0x000C: case 0x000D: st_ok(p, 1); return;   /* Map/Unmap, StartSampling (silencio), ... */")
# cfg bloques que deben ser cero
v = "    default: return 0;\n    }\n}\n\nstatic void cfg_atender"
assert s.count(v) == 1
s = s.replace(v, "    case 0x000C0000: case 0x000C0001: case 0x00130000: return 1;                                     /* control parental, COPPACS, modo depuracion: en cero */\n" + v)
# registro
v = '    ipc_registrar("hid:USER", hid_provisional);\n}'
assert s.count(v) == 1
s = s.replace(v, '''    ipc_registrar("hid:USER", hid_provisional);
    /* del exheader (agente S): el juego no los abre hoy, pero si lo hace no cae en "servicio sin implementar" */
    ipc_registrar("ptm:u", ptm_atender);
    ipc_registrar("ac:u", ac_atender);
    ipc_registrar("frd:u", frd_atender);
    ipc_registrar("gsp::Lcd", lcd_atender);
    ipc_registrar("boss:U", generico_atender);
    ipc_registrar("news:u", generico_atender);
    ipc_registrar("cam:u", generico_atender);
    ipc_registrar("y2r:u", generico_atender);
    ipc_registrar("ir:USER", generico_atender);
    ipc_registrar("nwm::UDS", generico_atender);
}''')
open(p + ".tmp", "w", encoding="utf-8").write(s)
os.replace(p + ".tmp", p)
print("ok")
