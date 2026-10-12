import os
p = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\recomp\sistema\stubs.c"
s = open(p, encoding="utf-8").read()
P = open(r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_noche\P\parche_apt_applets.py", encoding="utf-8").read()
i = P.index("/* Mii \"premade\""); j = P.index("static void apt_poner_param")
bloque = P[i:j]
viejo = """    case 0x402: case 0x202:                            /* selector de Mii: cancelado (return_code 1, big endian) */
        memset(b, 0, n < 0x84 ? n : 0x84);
        if (n >= 4) b[3] = 1;
        break;"""
nuevo = """    case 0x402: case 0x202:                            /* selector de Mii: devuelve el Mii estandar (MiiResult 0x84) */
        if (getenv("SM3DL_MII_CANCELAR")) { memset(b, 0, 0x84); b[3] = 1; n = 0x84; }   /* "cancelar": el juego vuelve a preguntar */
        else n = apt_mii_resultado(b);
        break;"""
assert s.count(viejo) == 1
s = s.replace(viejo, nuevo)
k = s.index("/* el applet termina: devuelve")
s = s[:k] + "/* (Mii de P, agentes_noche\\P\\parche_apt_applets.py) */\n" + bloque + s[k:]
open(p + ".tmp", "w", encoding="utf-8").write(s); os.replace(p + ".tmp", p); print("ok")
