"""Parche 1 de raster_uber.c: especializacion (ESPECIALIZADO/LUZ), div255, combinar desenrollado."""
import sys
p = sys.argv[1]
s = open(p, encoding='utf-8').read()
N = '\\n'


def rep(a, b):
    global s
    a = a.replace('@', N)
    b = b.replace('@', N)
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''    "uniform uvec4 tev[6];          // por etapa: registros fuente, operando, combinador, escala (crudos)@"''',
'''    "#ifndef ESPECIALIZADO          // si no, la estructura (TEV, config de luz) llega como constantes@"
    "uniform uvec4 tev[6];          // por etapa: registros fuente, operando, combinador, escala (crudos)@"
    "uniform uint tev_upd;          // 0x0E0 crudo (bits 8-15: que etapas actualizan el buffer)@"
    "uniform int luz_on;@"
    "uniform int luz_n;@"
    "uniform uint luz_c0;           // 0x1C3@"
    "uniform uint luz_c1;           // 0x1C4@"
    "uniform uint luz_abs;          // 0x1D0@"
    "uniform uint luz_ent;          // 0x1D1@"
    "uniform uint luz_esc;          // 0x1D2@"
    "uniform int luz_mues;          // bit n = muestreador n soportado y no apagado (0 D0 1 D1 3 FR 4 RB 5 RG 6 RR 8 SP)@"
    "#define LUZ@"
    "#endif@"''')
rep('''    "uniform uint tev_upd;          // 0x0E0 crudo (bits 8-15: que etapas actualizan el buffer)@"
    "uniform sampler2D tex0;@"''', '''    "uniform sampler2D tex0;@"''')
rep('''    "struct Luz {''', '''    "#ifdef LUZ@"
    "struct Luz {''')
rep('''    "uniform int luz_on;@"
    "uniform int luz_n;@"
    "uniform vec3 luz_amb;@"
    "uniform uint luz_c0;           // 0x1C3@"
    "uniform uint luz_c1;           // 0x1C4@"
    "uniform uint luz_abs;          // 0x1D0@"
    "uniform uint luz_ent;          // 0x1D1@"
    "uniform uint luz_esc;          // 0x1D2@"
    "uniform int luz_mues;          // bit n = muestreador n soportado por la config y no apagado (0 D0 1 D1 3 FR 4 RB 5 RG 6 RR 8 SP)@"
    "uniform sampler2D luz_luts;    // RG32F 256x24: (valor, diferencia)@"''', '''    "uniform vec3 luz_amb;@"
    "uniform sampler2D luz_luts;    // RG32F 256x24: (valor, diferencia)@"
    "#endif@"''')
rep('''    "// ---------------- luz por fragmento ----------------@"''', '''    "#ifdef LUZ@"
    "// ---------------- luz por fragmento ----------------@"''')
rep('''    "    c_sec = ivec4(floor(clamp(esp, 0.0, 1.0) * 255.0 + 1e-3));@"
    "}@"''', '''    "    c_sec = ivec4(floor(clamp(esp, 0.0, 1.0) * 255.0 + 1e-3));@"
    "}@"
    "#endif@"''')
rep('''    "ivec3 operar(uint op, ivec3 a, ivec3 b, ivec3 c, bool rgb) {@"
    "    switch (op) {@"
    "    case 0u: return a;@"
    "    case 1u: return a * b / 255;@"
    "    case 2u: return min(a + b, ivec3(255));@"
    "    case 3u: return clamp(a + b - 128, 0, 255);@"
    "    case 4u: return (a * c + b * (255 - c)) / 255;@"
    "    case 5u: return max(a - b, ivec3(0));@"
    "    case 6u: case 7u: return rgb ? dot3(a, b) : ivec3(0);@"
    "    case 8u: return min((a * b + 255 * c) / 255, ivec3(255));@"
    "    case 9u: return min(a + b, ivec3(255)) * c / 255;@"
    "    }@"
    "    return ivec3(0);@"
    "}@"''', '''    "// x / 255 truncado, exacto para 0 <= x <= 65534 (aqui x <= 65025): sin division entera (cara en la GPU)@"
    "ivec3 d255(ivec3 x) { return (x + 1 + (x >> 8)) >> 8; }@"
    "ivec3 operar(uint op, ivec3 a, ivec3 b, ivec3 c, bool rgb) {@"
    "    switch (op) {@"
    "    case 0u: return a;@"
    "    case 1u: return d255(a * b);@"
    "    case 2u: return min(a + b, ivec3(255));@"
    "    case 3u: return clamp(a + b - 128, 0, 255);@"
    "    case 4u: return d255(a * c + b * (255 - c));@"
    "    case 5u: return max(a - b, ivec3(0));@"
    "    case 6u: case 7u: return rgb ? dot3(a, b) : ivec3(0);@"
    "    case 8u: return min(c + d255(a * b), ivec3(255));   // (ab + 255c)/255 = c + ab/255@"
    "    case 9u: return d255(min(a + b, ivec3(255)) * c);@"
    "    }@"
    "    return ivec3(0);@"
    "}@"''')
rep('''    "    ivec3 t = sign(p) * (abs(p) / 256);   // division de C: trunca hacia 0@"''',
    '''    "    ivec3 t = sign(p) * (abs(p) >> 8);    // division de C: trunca hacia 0@"''')
rep('''    "ivec4 combinar() {@"
    "    ivec4 prev = ivec4(0), buf = ivec4(0), sig = rgba8(tev_buf);@"
    "    for (int k = 0; k < 6; k++) {@"
    "        uint s = tev[k].x, o = tev[k].y, c = tev[k].z, e = tev[k].w;@"''',
    '''    "void etapa(const int k, uvec4 cfg, inout ivec4 prev, inout ivec4 buf, inout ivec4 sig) {@"
    "    {@"
    "        uint s = cfg.x, o = cfg.y, c = cfg.z, e = cfg.w;@"''')
rep('''    "        if (k < 4) {@"
    "            if (((tev_upd >> (8 + k)) & 1u) != 0u) sig.rgb = prev.rgb;@"
    "            if (((tev_upd >> (12 + k)) & 1u) != 0u) sig.a = prev.a;@"
    "        }@"
    "    }@"
    "    return prev;@"
    "}@"''', '''    "        if (k < 4) {@"
    "            if (((tev_upd >> (8 + k)) & 1u) != 0u) sig.rgb = prev.rgb;@"
    "            if (((tev_upd >> (12 + k)) & 1u) != 0u) sig.a = prev.a;@"
    "        }@"
    "    }@"
    "}@"
    "ivec4 combinar() {   // desenrollado: con ESPECIALIZADO cada etapa se pliega a su receta@"
    "    ivec4 prev = ivec4(0), buf = ivec4(0), sig = rgba8(tev_buf);@"
    "    etapa(0, tev[0], prev, buf, sig);@"
    "    etapa(1, tev[1], prev, buf, sig);@"
    "    etapa(2, tev[2], prev, buf, sig);@"
    "    etapa(3, tev[3], prev, buf, sig);@"
    "    etapa(4, tev[4], prev, buf, sig);@"
    "    etapa(5, tev[5], prev, buf, sig);@"
    "    return prev;@"
    "}@"''')
rep('''    "    c_pri = ivec4(0);@"
    "    c_sec = ivec4(0);@"
    "    if (luz_on != 0) iluminar();@"
    "#endif@"''', '''    "    c_pri = ivec4(0);@"
    "    c_sec = ivec4(0);@"
    "#ifdef LUZ@"
    "#ifndef ESPECIALIZADO@"
    "    if (luz_on != 0)@"
    "#endif@"
    "    iluminar();@"
    "#endif@"
    "#endif@"''')
open(p + '.tmp', 'w', encoding='utf-8', newline='').write(s)
import os
os.replace(p + '.tmp', p)
print('ok')
