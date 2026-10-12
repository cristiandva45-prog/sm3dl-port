"""Listas de comandos de la GPU PICA200: parser, nombres de registros y decodificacion de la etapa de fragmentos.

Uso:
  py -I tools\\pica_cmd.py material <archivo.szs|.bcmdl> [nombre_material]   # cachés de comandos de cada material
  py -I tools\\pica_cmd.py censo [carpeta_romfs]   # todos los materiales del juego -> extraido\\pica_materiales.tsv + resumen
  py -I tools\\pica_cmd.py codigo                  # cabeceras de comando en el ejecutable (literal pools y tablas)
  py -I tools\\pica_cmd.py lista <archivo.bin>     # lista de comandos cruda (alineada a 8 bytes)

Formato de una lista (3dbrew "GPU/Internal Registers", "GPU commands"):
  cada comando = [parametro0][cabecera] + parametros extra, rellenado a 8 bytes.
  cabecera: bits 0-15 registro, 16-19 mascara de bytes, 20-27 cantidad de parametros extra, 31 = escritura
  consecutiva (el parametro k va al registro + k; si no, todos van al mismo registro).
Los materiales CGFX traen estos comandos ya armados (culling, depth, blend, stencil, 6 etapas TEV, texturas,
alpha test, lighting): el juego solo los copia a la lista de la GPU. Por eso se pueden leer sin ejecutar nada.
"""
import collections
import os
import struct
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(RAIZ, "tools"))  # al final: tools/dis.py taparia al dis de la stdlib

# nombres GPUREG_* (sin el prefijo), los mismos de 3dbrew
NOMBRES = {
    0x010: "FINALIZE", 0x020: "IRQ_CMP", 0x034: "IRQ_AUTOSTOP", 0x040: "FACECULLING_CONFIG",
    0x041: "VIEWPORT_WIDTH", 0x042: "VIEWPORT_INVW", 0x043: "VIEWPORT_HEIGHT", 0x044: "VIEWPORT_INVH",
    0x047: "FRAGOP_CLIP", 0x048: "FRAGOP_CLIP_DATA0", 0x049: "FRAGOP_CLIP_DATA1", 0x04A: "FRAGOP_CLIP_DATA2",
    0x04B: "FRAGOP_CLIP_DATA3", 0x04D: "DEPTHMAP_SCALE", 0x04E: "DEPTHMAP_OFFSET", 0x04F: "SH_OUTMAP_TOTAL",
    0x050: "SH_OUTMAP_O0", 0x051: "SH_OUTMAP_O1", 0x052: "SH_OUTMAP_O2", 0x053: "SH_OUTMAP_O3",
    0x054: "SH_OUTMAP_O4", 0x055: "SH_OUTMAP_O5", 0x056: "SH_OUTMAP_O6", 0x061: "EARLYDEPTH_FUNC",
    0x062: "EARLYDEPTH_TEST1", 0x063: "EARLYDEPTH_CLEAR", 0x064: "SH_OUTATTR_MODE", 0x065: "SCISSORTEST_MODE",
    0x066: "SCISSORTEST_POS", 0x067: "SCISSORTEST_DIM", 0x068: "VIEWPORT_XY", 0x06A: "EARLYDEPTH_DATA",
    0x06D: "DEPTHMAP_ENABLE", 0x06E: "RENDERBUF_DIM", 0x06F: "SH_OUTATTR_CLOCK", 0x080: "TEXUNIT_CONFIG",
    0x081: "TEXUNIT0_BORDER_COLOR", 0x082: "TEXUNIT0_DIM", 0x083: "TEXUNIT0_PARAM", 0x084: "TEXUNIT0_LOD",
    0x085: "TEXUNIT0_ADDR1", 0x086: "TEXUNIT0_ADDR2", 0x087: "TEXUNIT0_ADDR3", 0x088: "TEXUNIT0_ADDR4",
    0x089: "TEXUNIT0_ADDR5", 0x08A: "TEXUNIT0_ADDR6", 0x08B: "TEXUNIT0_SHADOW", 0x08E: "TEXUNIT0_TYPE",
    0x08F: "LIGHTING_ENABLE0", 0x091: "TEXUNIT1_BORDER_COLOR", 0x092: "TEXUNIT1_DIM", 0x093: "TEXUNIT1_PARAM",
    0x094: "TEXUNIT1_LOD", 0x095: "TEXUNIT1_ADDR", 0x096: "TEXUNIT1_TYPE", 0x099: "TEXUNIT2_BORDER_COLOR",
    0x09A: "TEXUNIT2_DIM", 0x09B: "TEXUNIT2_PARAM", 0x09C: "TEXUNIT2_LOD", 0x09D: "TEXUNIT2_ADDR",
    0x09E: "TEXUNIT2_TYPE", 0x0A8: "TEXUNIT3_PROCTEX0", 0x0A9: "TEXUNIT3_PROCTEX1", 0x0AA: "TEXUNIT3_PROCTEX2",
    0x0AB: "TEXUNIT3_PROCTEX3", 0x0AC: "TEXUNIT3_PROCTEX4", 0x0AD: "TEXUNIT3_PROCTEX5", 0x0AF: "PROCTEX_LUT",
    0x0B0: "PROCTEX_LUT_DATA0", 0x0B1: "PROCTEX_LUT_DATA1", 0x0B2: "PROCTEX_LUT_DATA2", 0x0B3: "PROCTEX_LUT_DATA3",
    0x0B4: "PROCTEX_LUT_DATA4", 0x0B5: "PROCTEX_LUT_DATA5", 0x0B6: "PROCTEX_LUT_DATA6", 0x0B7: "PROCTEX_LUT_DATA7",
    0x0C0: "TEXENV0_SOURCE", 0x0C1: "TEXENV0_OPERAND", 0x0C2: "TEXENV0_COMBINER", 0x0C3: "TEXENV0_COLOR",
    0x0C4: "TEXENV0_SCALE", 0x0C8: "TEXENV1_SOURCE", 0x0C9: "TEXENV1_OPERAND", 0x0CA: "TEXENV1_COMBINER",
    0x0CB: "TEXENV1_COLOR", 0x0CC: "TEXENV1_SCALE", 0x0D0: "TEXENV2_SOURCE", 0x0D1: "TEXENV2_OPERAND",
    0x0D2: "TEXENV2_COMBINER", 0x0D3: "TEXENV2_COLOR", 0x0D4: "TEXENV2_SCALE", 0x0D8: "TEXENV3_SOURCE",
    0x0D9: "TEXENV3_OPERAND", 0x0DA: "TEXENV3_COMBINER", 0x0DB: "TEXENV3_COLOR", 0x0DC: "TEXENV3_SCALE",
    0x0E0: "TEXENV_UPDATE_BUFFER", 0x0E1: "FOG_COLOR", 0x0E4: "GAS_ATTENUATION", 0x0E5: "GAS_ACCMAX",
    0x0E6: "FOG_LUT_INDEX", 0x0E8: "FOG_LUT_DATA0", 0x0E9: "FOG_LUT_DATA1", 0x0EA: "FOG_LUT_DATA2",
    0x0EB: "FOG_LUT_DATA3", 0x0EC: "FOG_LUT_DATA4", 0x0ED: "FOG_LUT_DATA5", 0x0EE: "FOG_LUT_DATA6",
    0x0EF: "FOG_LUT_DATA7", 0x0F0: "TEXENV4_SOURCE", 0x0F1: "TEXENV4_OPERAND", 0x0F2: "TEXENV4_COMBINER",
    0x0F3: "TEXENV4_COLOR", 0x0F4: "TEXENV4_SCALE", 0x0F8: "TEXENV5_SOURCE", 0x0F9: "TEXENV5_OPERAND",
    0x0FA: "TEXENV5_COMBINER", 0x0FB: "TEXENV5_COLOR", 0x0FC: "TEXENV5_SCALE", 0x0FD: "TEXENV_BUFFER_COLOR",
    0x100: "COLOR_OPERATION", 0x101: "BLEND_FUNC", 0x102: "LOGIC_OP", 0x103: "BLEND_COLOR",
    0x104: "FRAGOP_ALPHA_TEST", 0x105: "STENCIL_TEST", 0x106: "STENCIL_OP", 0x107: "DEPTH_COLOR_MASK",
    0x110: "FRAMEBUFFER_INVALIDATE", 0x111: "FRAMEBUFFER_FLUSH", 0x112: "COLORBUFFER_READ",
    0x113: "COLORBUFFER_WRITE", 0x114: "DEPTHBUFFER_READ", 0x115: "DEPTHBUFFER_WRITE", 0x116: "DEPTHBUFFER_FORMAT",
    0x117: "COLORBUFFER_FORMAT", 0x118: "EARLYDEPTH_TEST2", 0x11B: "FRAMEBUFFER_BLOCK32", 0x11C: "DEPTHBUFFER_LOC",
    0x11D: "COLORBUFFER_LOC", 0x11E: "FRAMEBUFFER_DIM", 0x120: "GAS_LIGHT_XY", 0x121: "GAS_LIGHT_Z",
    0x122: "GAS_LIGHT_Z_COLOR", 0x123: "GAS_LUT_INDEX", 0x124: "GAS_LUT_DATA", 0x126: "GAS_DELTAZ_DEPTH",
    0x130: "FRAGOP_SHADOW", 0x140: "LIGHT0_SPECULAR0", 0x141: "LIGHT0_SPECULAR1", 0x142: "LIGHT0_DIFFUSE",
    0x143: "LIGHT0_AMBIENT", 0x144: "LIGHT0_XY", 0x145: "LIGHT0_Z", 0x146: "LIGHT0_SPOTDIR_XY",
    0x147: "LIGHT0_SPOTDIR_Z", 0x149: "LIGHT0_CONFIG", 0x14A: "LIGHT0_ATTENUATION_BIAS",
    0x14B: "LIGHT0_ATTENUATION_SCALE", 0x150: "LIGHT1_SPECULAR0", 0x151: "LIGHT1_SPECULAR1",
    0x152: "LIGHT1_DIFFUSE", 0x153: "LIGHT1_AMBIENT", 0x154: "LIGHT1_XY", 0x155: "LIGHT1_Z",
    0x156: "LIGHT1_SPOTDIR_XY", 0x157: "LIGHT1_SPOTDIR_Z", 0x159: "LIGHT1_CONFIG",
    0x15A: "LIGHT1_ATTENUATION_BIAS", 0x15B: "LIGHT1_ATTENUATION_SCALE", 0x160: "LIGHT2_SPECULAR0",
    0x161: "LIGHT2_SPECULAR1", 0x162: "LIGHT2_DIFFUSE", 0x163: "LIGHT2_AMBIENT", 0x164: "LIGHT2_XY",
    0x165: "LIGHT2_Z", 0x166: "LIGHT2_SPOTDIR_XY", 0x167: "LIGHT2_SPOTDIR_Z", 0x169: "LIGHT2_CONFIG",
    0x16A: "LIGHT2_ATTENUATION_BIAS", 0x16B: "LIGHT2_ATTENUATION_SCALE", 0x170: "LIGHT3_SPECULAR0",
    0x171: "LIGHT3_SPECULAR1", 0x172: "LIGHT3_DIFFUSE", 0x173: "LIGHT3_AMBIENT", 0x174: "LIGHT3_XY",
    0x175: "LIGHT3_Z", 0x176: "LIGHT3_SPOTDIR_XY", 0x177: "LIGHT3_SPOTDIR_Z", 0x179: "LIGHT3_CONFIG",
    0x17A: "LIGHT3_ATTENUATION_BIAS", 0x17B: "LIGHT3_ATTENUATION_SCALE", 0x180: "LIGHT4_SPECULAR0",
    0x181: "LIGHT4_SPECULAR1", 0x182: "LIGHT4_DIFFUSE", 0x183: "LIGHT4_AMBIENT", 0x184: "LIGHT4_XY",
    0x185: "LIGHT4_Z", 0x186: "LIGHT4_SPOTDIR_XY", 0x187: "LIGHT4_SPOTDIR_Z", 0x189: "LIGHT4_CONFIG",
    0x18A: "LIGHT4_ATTENUATION_BIAS", 0x18B: "LIGHT4_ATTENUATION_SCALE", 0x190: "LIGHT5_SPECULAR0",
    0x191: "LIGHT5_SPECULAR1", 0x192: "LIGHT5_DIFFUSE", 0x193: "LIGHT5_AMBIENT", 0x194: "LIGHT5_XY",
    0x195: "LIGHT5_Z", 0x196: "LIGHT5_SPOTDIR_XY", 0x197: "LIGHT5_SPOTDIR_Z", 0x199: "LIGHT5_CONFIG",
    0x19A: "LIGHT5_ATTENUATION_BIAS", 0x19B: "LIGHT5_ATTENUATION_SCALE", 0x1A0: "LIGHT6_SPECULAR0",
    0x1A1: "LIGHT6_SPECULAR1", 0x1A2: "LIGHT6_DIFFUSE", 0x1A3: "LIGHT6_AMBIENT", 0x1A4: "LIGHT6_XY",
    0x1A5: "LIGHT6_Z", 0x1A6: "LIGHT6_SPOTDIR_XY", 0x1A7: "LIGHT6_SPOTDIR_Z", 0x1A9: "LIGHT6_CONFIG",
    0x1AA: "LIGHT6_ATTENUATION_BIAS", 0x1AB: "LIGHT6_ATTENUATION_SCALE", 0x1B0: "LIGHT7_SPECULAR0",
    0x1B1: "LIGHT7_SPECULAR1", 0x1B2: "LIGHT7_DIFFUSE", 0x1B3: "LIGHT7_AMBIENT", 0x1B4: "LIGHT7_XY",
    0x1B5: "LIGHT7_Z", 0x1B6: "LIGHT7_SPOTDIR_XY", 0x1B7: "LIGHT7_SPOTDIR_Z", 0x1B9: "LIGHT7_CONFIG",
    0x1BA: "LIGHT7_ATTENUATION_BIAS", 0x1BB: "LIGHT7_ATTENUATION_SCALE", 0x1C0: "LIGHTING_AMBIENT",
    0x1C2: "LIGHTING_NUM_LIGHTS", 0x1C3: "LIGHTING_CONFIG0", 0x1C4: "LIGHTING_CONFIG1",
    0x1C5: "LIGHTING_LUT_INDEX", 0x1C6: "LIGHTING_ENABLE1", 0x1C8: "LIGHTING_LUT_DATA0",
    0x1C9: "LIGHTING_LUT_DATA1", 0x1CA: "LIGHTING_LUT_DATA2", 0x1CB: "LIGHTING_LUT_DATA3",
    0x1CC: "LIGHTING_LUT_DATA4", 0x1CD: "LIGHTING_LUT_DATA5", 0x1CE: "LIGHTING_LUT_DATA6",
    0x1CF: "LIGHTING_LUT_DATA7", 0x1D0: "LIGHTING_LUTINPUT_ABS", 0x1D1: "LIGHTING_LUTINPUT_SELECT",
    0x1D2: "LIGHTING_LUTINPUT_SCALE", 0x1D9: "LIGHTING_LIGHT_PERMUTATION", 0x200: "ATTRIBBUFFERS_LOC",
    0x201: "ATTRIBBUFFERS_FORMAT_LOW", 0x202: "ATTRIBBUFFERS_FORMAT_HIGH", 0x203: "ATTRIBBUFFER0_OFFSET",
    0x204: "ATTRIBBUFFER0_CONFIG1", 0x205: "ATTRIBBUFFER0_CONFIG2", 0x206: "ATTRIBBUFFER1_OFFSET",
    0x207: "ATTRIBBUFFER1_CONFIG1", 0x208: "ATTRIBBUFFER1_CONFIG2", 0x209: "ATTRIBBUFFER2_OFFSET",
    0x20A: "ATTRIBBUFFER2_CONFIG1", 0x20B: "ATTRIBBUFFER2_CONFIG2", 0x20C: "ATTRIBBUFFER3_OFFSET",
    0x20D: "ATTRIBBUFFER3_CONFIG1", 0x20E: "ATTRIBBUFFER3_CONFIG2", 0x20F: "ATTRIBBUFFER4_OFFSET",
    0x210: "ATTRIBBUFFER4_CONFIG1", 0x211: "ATTRIBBUFFER4_CONFIG2", 0x212: "ATTRIBBUFFER5_OFFSET",
    0x213: "ATTRIBBUFFER5_CONFIG1", 0x214: "ATTRIBBUFFER5_CONFIG2", 0x215: "ATTRIBBUFFER6_OFFSET",
    0x216: "ATTRIBBUFFER6_CONFIG1", 0x217: "ATTRIBBUFFER6_CONFIG2", 0x218: "ATTRIBBUFFER7_OFFSET",
    0x219: "ATTRIBBUFFER7_CONFIG1", 0x21A: "ATTRIBBUFFER7_CONFIG2", 0x21B: "ATTRIBBUFFER8_OFFSET",
    0x21C: "ATTRIBBUFFER8_CONFIG1", 0x21D: "ATTRIBBUFFER8_CONFIG2", 0x21E: "ATTRIBBUFFER9_OFFSET",
    0x21F: "ATTRIBBUFFER9_CONFIG1", 0x220: "ATTRIBBUFFER9_CONFIG2", 0x221: "ATTRIBBUFFER10_OFFSET",
    0x222: "ATTRIBBUFFER10_CONFIG1", 0x223: "ATTRIBBUFFER10_CONFIG2", 0x224: "ATTRIBBUFFER11_OFFSET",
    0x225: "ATTRIBBUFFER11_CONFIG1", 0x226: "ATTRIBBUFFER11_CONFIG2", 0x227: "INDEXBUFFER_CONFIG",
    0x228: "NUMVERTICES", 0x229: "GEOSTAGE_CONFIG", 0x22A: "VERTEX_OFFSET", 0x22D: "POST_VERTEX_CACHE_NUM",
    0x22E: "DRAWARRAYS", 0x22F: "DRAWELEMENTS", 0x231: "VTX_FUNC", 0x232: "FIXEDATTRIB_INDEX",
    0x233: "FIXEDATTRIB_DATA0", 0x234: "FIXEDATTRIB_DATA1", 0x235: "FIXEDATTRIB_DATA2", 0x238: "CMDBUF_SIZE0",
    0x239: "CMDBUF_SIZE1", 0x23A: "CMDBUF_ADDR0", 0x23B: "CMDBUF_ADDR1", 0x23C: "CMDBUF_JUMP0",
    0x23D: "CMDBUF_JUMP1", 0x242: "VSH_NUM_ATTR", 0x244: "VSH_COM_MODE", 0x245: "START_DRAW_FUNC0",
    0x24A: "VSH_OUTMAP_TOTAL1", 0x251: "VSH_OUTMAP_TOTAL2", 0x252: "GSH_MISC0", 0x253: "GEOSTAGE_CONFIG2",
    0x254: "GSH_MISC1", 0x25E: "PRIMITIVE_CONFIG", 0x25F: "RESTART_PRIMITIVE", 0x280: "GSH_BOOLUNIFORM",
    0x281: "GSH_INTUNIFORM_I0", 0x282: "GSH_INTUNIFORM_I1", 0x283: "GSH_INTUNIFORM_I2", 0x284: "GSH_INTUNIFORM_I3",
    0x289: "GSH_INPUTBUFFER_CONFIG", 0x28A: "GSH_ENTRYPOINT", 0x28B: "GSH_ATTRIBUTES_PERMUTATION_LOW",
    0x28C: "GSH_ATTRIBUTES_PERMUTATION_HIGH", 0x28D: "GSH_OUTMAP_MASK", 0x28F: "GSH_CODETRANSFER_END",
    0x290: "GSH_FLOATUNIFORM_INDEX", 0x291: "GSH_FLOATUNIFORM_DATA0", 0x292: "GSH_FLOATUNIFORM_DATA1",
    0x293: "GSH_FLOATUNIFORM_DATA2", 0x294: "GSH_FLOATUNIFORM_DATA3", 0x295: "GSH_FLOATUNIFORM_DATA4",
    0x296: "GSH_FLOATUNIFORM_DATA5", 0x297: "GSH_FLOATUNIFORM_DATA6", 0x298: "GSH_FLOATUNIFORM_DATA7",
    0x29B: "GSH_CODETRANSFER_INDEX", 0x29C: "GSH_CODETRANSFER_DATA0", 0x29D: "GSH_CODETRANSFER_DATA1",
    0x29E: "GSH_CODETRANSFER_DATA2", 0x29F: "GSH_CODETRANSFER_DATA3", 0x2A0: "GSH_CODETRANSFER_DATA4",
    0x2A1: "GSH_CODETRANSFER_DATA5", 0x2A2: "GSH_CODETRANSFER_DATA6", 0x2A3: "GSH_CODETRANSFER_DATA7",
    0x2A5: "GSH_OPDESCS_INDEX", 0x2A6: "GSH_OPDESCS_DATA0", 0x2A7: "GSH_OPDESCS_DATA1", 0x2A8: "GSH_OPDESCS_DATA2",
    0x2A9: "GSH_OPDESCS_DATA3", 0x2AA: "GSH_OPDESCS_DATA4", 0x2AB: "GSH_OPDESCS_DATA5", 0x2AC: "GSH_OPDESCS_DATA6",
    0x2AD: "GSH_OPDESCS_DATA7", 0x2B0: "VSH_BOOLUNIFORM", 0x2B1: "VSH_INTUNIFORM_I0", 0x2B2: "VSH_INTUNIFORM_I1",
    0x2B3: "VSH_INTUNIFORM_I2", 0x2B4: "VSH_INTUNIFORM_I3", 0x2B9: "VSH_INPUTBUFFER_CONFIG",
    0x2BA: "VSH_ENTRYPOINT", 0x2BB: "VSH_ATTRIBUTES_PERMUTATION_LOW", 0x2BC: "VSH_ATTRIBUTES_PERMUTATION_HIGH",
    0x2BD: "VSH_OUTMAP_MASK", 0x2BF: "VSH_CODETRANSFER_END", 0x2C0: "VSH_FLOATUNIFORM_INDEX",
    0x2C1: "VSH_FLOATUNIFORM_DATA0", 0x2C2: "VSH_FLOATUNIFORM_DATA1", 0x2C3: "VSH_FLOATUNIFORM_DATA2",
    0x2C4: "VSH_FLOATUNIFORM_DATA3", 0x2C5: "VSH_FLOATUNIFORM_DATA4", 0x2C6: "VSH_FLOATUNIFORM_DATA5",
    0x2C7: "VSH_FLOATUNIFORM_DATA6", 0x2C8: "VSH_FLOATUNIFORM_DATA7", 0x2CB: "VSH_CODETRANSFER_INDEX",
    0x2CC: "VSH_CODETRANSFER_DATA0", 0x2CD: "VSH_CODETRANSFER_DATA1", 0x2CE: "VSH_CODETRANSFER_DATA2",
    0x2CF: "VSH_CODETRANSFER_DATA3", 0x2D0: "VSH_CODETRANSFER_DATA4", 0x2D1: "VSH_CODETRANSFER_DATA5",
    0x2D2: "VSH_CODETRANSFER_DATA6", 0x2D3: "VSH_CODETRANSFER_DATA7", 0x2D5: "VSH_OPDESCS_INDEX",
    0x2D6: "VSH_OPDESCS_DATA0", 0x2D7: "VSH_OPDESCS_DATA1", 0x2D8: "VSH_OPDESCS_DATA2", 0x2D9: "VSH_OPDESCS_DATA3",
    0x2DA: "VSH_OPDESCS_DATA4", 0x2DB: "VSH_OPDESCS_DATA5", 0x2DC: "VSH_OPDESCS_DATA6", 0x2DD: "VSH_OPDESCS_DATA7",
}


def nombre(reg):
    return NOMBRES.get(reg, f"REG_{reg:03X}")


def cabecera(v):
    """(registro, mascara, extra, consecutivo) o None si la palabra no puede ser una cabecera."""
    reg, mask, ext, seq = v & 0xFFFF, (v >> 16) & 0xF, (v >> 20) & 0xFF, v >> 31
    if not mask or (v >> 28) & 7 or reg >= 0x300:
        return None
    return reg, mask, ext, seq


def parsear(palabras):
    """Lista real (empieza alineada): -> [(registro, mascara, valor)]."""
    out, k = [], 0
    while k + 1 < len(palabras):
        h = cabecera(palabras[k + 1])
        if h is None:
            raise ValueError(f"cabecera invalida {palabras[k + 1]:08X} en la palabra {k + 1}")
        reg, mask, ext, seq = h
        params = [palabras[k]] + palabras[k + 2:k + 2 + ext]
        for j, p in enumerate(params):
            out.append((reg + j if seq else reg, mask, p))
        n = 2 + ext
        k += n + (n & 1)
    return out


def escanear(d, ini, fin, estricto=True):
    """Comandos sueltos dentro de una estructura (las cachés de CGFX no estan en una lista continua).
    Una cabecera candidata se descarta si otra candidata cae dentro de sus parametros extra
    (el parametro de una cabecera real suele parecer cabecera: KuriboMat00+0x140 / +0x144)."""
    cands = []
    for k in range(ini + 4, fin - 3, 4):
        v = struct.unpack_from("<I", d, k)[0]
        h = cabecera(v)
        if h is None:
            continue
        reg, mask, ext, seq = h
        if estricto and (reg not in NOMBRES or ext > 32):
            continue
        if k + 4 + 4 * ext > fin:
            continue
        cands.append((k, h))
    acept = []
    for k, h in cands:
        while acept and acept[-1][0] + 4 * acept[-1][1][2] >= k:  # k cae en los extra del anterior
            acept.pop()
        acept.append((k, h))
    out = []
    for k, (reg, mask, ext, seq) in acept:
        params = [struct.unpack_from("<I", d, k - 4)[0]] + \
            [struct.unpack_from("<I", d, k + 4 + 4 * j)[0] for j in range(ext)]
        for j, p in enumerate(params):
            out.append((k, reg + j if seq else reg, mask, p))
    return out


# ---------------- decodificacion de la etapa de fragmentos ----------------
TEV_FUENTE = {0: "color_vtx", 1: "luz_difusa", 2: "luz_especular", 3: "tex0", 4: "tex1", 5: "tex2", 6: "tex3",
              0xD: "buffer_previo", 0xE: "constante", 0xF: "previo"}
TEV_OP_RGB = {0: "", 1: "1-", 2: ".a", 3: "1-.a", 4: ".r", 5: "1-.r", 8: ".g", 9: "1-.g", 0xC: ".b", 0xD: "1-.b"}
TEV_OP_A = {0: ".a", 1: "1-.a", 2: ".r", 3: "1-.r", 4: ".g", 5: "1-.g", 6: ".b", 7: "1-.b"}
TEV_COMB = {0: "REPLACE(a)", 1: "MOD(a*b)", 2: "ADD(a+b)", 3: "ADDS(a+b-.5)", 4: "LERP(a*c+b*(1-c))", 5: "SUB(a-b)",
            6: "DOT3_RGB", 7: "DOT3_RGBA", 8: "MULADD(a*b+c)", 9: "ADDMUL((a+b)*c)"}
NARGS = {0: 1, 1: 2, 2: 2, 3: 2, 4: 3, 5: 2, 6: 2, 7: 2, 8: 3, 9: 3}
ESCALA = {0: "", 1: " x2", 2: " x4", 3: " x?"}
FUNC = ["nunca", "siempre", "==", "!=", "<", "<=", ">", ">="]
BLEND_EQ = ["add", "sub", "revsub", "min", "max"]
BLEND_F = ["0", "1", "src", "1-src", "dst", "1-dst", "src.a", "1-src.a", "dst.a", "1-dst.a", "k", "1-k", "k.a",
           "1-k.a", "src.a_sat"]
STENCIL_OP = ["keep", "zero", "replace", "incr", "decr", "invert", "incr_wrap", "decr_wrap"]


def _op(fuente, op, alfa):
    f = TEV_FUENTE.get(fuente, f"?{fuente:X}")
    o = (TEV_OP_A if alfa else TEV_OP_RGB).get(op, f"?{op}")
    return f"(1-{f}{o[2:]})" if o.startswith("1-") else f + o


def tev(src, opd, comb, color, escala):
    """Una etapa TEV en texto: 'rgb = MOD(tex0, color_vtx) | a = REPLACE(tex0.a)'."""
    def lado(alfa):
        c = (comb >> 16) & 0xF if alfa else comb & 0xF
        n = NARGS.get(c, 3)
        args = []
        for j in range(n):
            f = (src >> (16 + 4 * j if alfa else 4 * j)) & 0xF
            o = (opd >> (12 + 4 * j)) & 0x7 if alfa else (opd >> 4 * j) & 0xF
            args.append(_op(f, o, alfa))
        e = ESCALA[(escala >> 16) & 3 if alfa else escala & 3]
        return f"{TEV_COMB.get(c, f'?{c}').split('(')[0]}({', '.join(args)}){e}"
    s = f"rgb = {lado(False)} | a = {lado(True)}"
    usa_k = any(((src >> s_) & 0xF) == 0xE for s_ in (0, 4, 8, 16, 20, 24))
    return s + (f" | k = #{color:08X}" if usa_k else "")


def tev_es_paso(src, opd, comb):
    """Etapa que no hace nada: REPLACE(previo) en rgb y alfa con operandos directos."""
    return comb & 0xF == 0 and (comb >> 16) & 0xF == 0 and src & 0xF == 0xF and (src >> 16) & 0xF == 0xF \
        and opd & 0xF == 0 and (opd >> 12) & 7 == 0


def decodificar(reg, v):
    """Texto legible de los registros que definen la etapa de fragmentos (None si no es de esos)."""
    if reg == 0x040:
        return "culling " + ["ninguno", "frente(ccw)", "atras(cw)", "?"][v & 3]
    if reg == 0x100:
        return f"modo={['normal', '?1', '?2', 'gas', 'sombra'][v & 3] if (v & 3) < 4 else v & 3} " \
               f"{'blend' if v >> 8 & 1 else 'logic_op'}"
    if reg == 0x101:
        return (f"rgb: {BLEND_EQ[v & 7] if (v & 7) < 5 else v & 7}({BLEND_F[v >> 16 & 0xF]}, {BLEND_F[v >> 20 & 0xF]}) "
                f"a: {BLEND_EQ[v >> 8 & 7] if (v >> 8 & 7) < 5 else '?'}({BLEND_F[v >> 24 & 0xF]}, {BLEND_F[v >> 28 & 0xF]})")
    if reg == 0x104:
        return f"alpha_test {'on' if v & 1 else 'off'} {FUNC[v >> 4 & 7]} {v >> 8 & 0xFF}"
    if reg == 0x105:
        return f"stencil {'on' if v & 1 else 'off'} {FUNC[v >> 4 & 7]} ref={v >> 16 & 0xFF} wmask={v >> 8 & 0xFF:02X} " \
               f"imask={v >> 24 & 0xFF:02X}"
    if reg == 0x106:
        return f"stencil_op fail={STENCIL_OP[v & 7]} zfail={STENCIL_OP[v >> 4 & 7]} zpass={STENCIL_OP[v >> 8 & 7]}"
    if reg == 0x107:
        return f"depth {'on' if v & 1 else 'off'} {FUNC[v >> 4 & 7]} color_mask={''.join(c for k, c in enumerate('rgba') if v >> (8 + k) & 1) or '-'} " \
               f"depth_write={v >> 12 & 1}"
    if reg == 0x0E0:
        return f"fog={['no', '?', '?', '?', '?', 'fog', '?', 'gas'][v & 7]} buffer_rgb={v >> 8 & 0xF:04b} " \
               f"buffer_a={v >> 12 & 0xF:04b} zflip={v >> 16 & 1}"
    if reg in (0x083, 0x093, 0x09B):
        return f"mag={'lineal' if v >> 1 & 1 else 'cercano'} min={'lineal' if v >> 2 & 1 else 'cercano'} " \
               f"wrap_t={v >> 8 & 7} wrap_s={v >> 12 & 7} mip={'lineal' if v >> 24 & 1 else 'cercano'}"
    if reg in (0x08E, 0x096, 0x09E):
        return "formato " + ["RGBA8", "RGB8", "RGB5A1", "RGB565", "RGBA4", "IA8", "RG8", "I8", "A8", "IA4", "I4", "A4",
                             "ETC1", "ETC1A4"][v & 0xF] if (v & 0xF) < 14 else f"formato ?{v & 0xF}"
    return None


# ---------------- materiales CGFX ----------------
def materiales(b):
    """[(modelo, material, offset)] de un archivo CGFX: los DICT del modelo cuyos objetos son MTOB."""
    import cgfx
    out = []
    for nmod, o in cgfx.leer(b).get("modelos", []):
        for k in range(0, 0xC0, 4):
            p = o + k + 4
            if p + 4 > len(b):
                break
            v = cgfx.u32(b, p)
            if v and p + v + 4 <= len(b) and b[p + v:p + v + 4] == b"DICT":
                ents = cgfx.diccionario(b, p + v)
                if ents and all(b[x + 4:x + 8] == b"MTOB" for _, x in ents):
                    out += [(nmod, n, x) for n, x in ents]
    return out


def comandos_material(b, m):
    """Comandos de las cachés de un material: desde su MTOB hasta el siguiente MTOB (tope 0x1000 bytes)."""
    fin = b.find(b"MTOB", m + 8)
    fin = min(fin - 4 if fin > 0 else len(b), m + 0x1000, len(b))
    cmds = escanear(b, m, fin)
    # la ultima cache del material es LIGHTING_CONFIG0 (en +1000 + 140 por textura, en los 4.579 materiales);
    # lo que sigue es la malla siguiente leida como si fueran comandos (DRAWELEMENTS, FINALIZE...)
    for j, (k, reg, _, _) in enumerate(cmds):
        if reg == 0x1C3:
            return cmds[:j + 1]
    return cmds


def estado(cmds):
    """Ultimo valor de cada registro (respetando la mascara de bytes) -> {reg: valor}."""
    st = {}
    for _, reg, mask, v in cmds:
        m = sum(0xFF << 8 * k for k in range(4) if mask >> k & 1)
        st[reg] = (st.get(reg, 0) & ~m) | (v & m)
    return st


def resumen_material(st):
    """Texto de la etapa de fragmentos de un material."""
    lin = []
    for k, base in enumerate((0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8)):
        if base in st:
            s, o, c, k_, e = (st.get(base + j, 0) for j in range(5))
            if not tev_es_paso(s, o, c):
                lin.append(f"  TEV{k}: {tev(s, o, c, k_, e)}")
    for reg in (0x0E0, 0x0FD, 0x104, 0x107, 0x100, 0x101, 0x105, 0x106, 0x040, 0x080, 0x083, 0x08E, 0x093,
                0x096, 0x09B, 0x09E, 0x1C3, 0x1C4, 0x1D0, 0x1D1, 0x1D2):
        if reg in st:
            t = decodificar(reg, st[reg])
            lin.append(f"  {nombre(reg)} = {st[reg]:08X}" + (f"  ({t})" if t else ""))
    return "\n".join(lin)


def cgfx_de(ruta):
    import cgfx
    yield from cgfx.archivos_cgfx(ruta)



# ---------------- censo de todos los materiales ----------------
TEV_BASES = (0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8)


def firma_tev(st):
    """Las 6 etapas sin el color constante (que cambia por material/animacion): la 'receta' del fragment shader."""
    return tuple((st.get(b, 0), st.get(b + 1, 0), st.get(b + 2, 0), st.get(b + 4, 0)) for b in TEV_BASES)


def _censo_archivo(ruta):
    """[(archivo, modelo, material, estado, n_escrituras)] de un .szs (para el pool de procesos)."""
    out = []
    try:
        for narch, b in cgfx_de(ruta):
            for nmod, nmat, m in materiales(b):
                cmds = comandos_material(b, m)
                out.append((os.path.basename(ruta), nmod, nmat, estado(cmds), len(cmds)))
    except Exception as ex:  # noqa: BLE001
        out.append((os.path.basename(ruta), "ERROR", str(ex), {}, 0))
    return out


def censo(raiz):
    from concurrent.futures import ProcessPoolExecutor
    rutas = [os.path.join(c, a) for sub in ("ObjectData", "StageData") for c, _, arch in
             os.walk(os.path.join(raiz, sub)) for a in arch if a.endswith(".szs")]
    filas = []
    with ProcessPoolExecutor() as ex:
        for r in ex.map(_censo_archivo, rutas, chunksize=8):
            filas += r
    errores = [f for f in filas if f[1] == "ERROR"]
    mats = [f for f in filas if f[1] != "ERROR"]
    C = collections.Counter
    uso, firmas, etapas, fuentes, combs, escalas = C(), C(), C(), C(), C(), C()
    otros = collections.defaultdict(C)
    n_etapas_activas = C()
    ej_firma = {}
    for arch, nmod, nmat, st, n in mats:
        uso.update(st.keys())
        f = firma_tev(st)
        firmas[f] += 1
        ej_firma.setdefault(f, f"{arch}/{nmat}")
        activas = 0
        for s, o, c, e in f:
            if tev_es_paso(s, o, c):
                continue
            activas += 1
            etapas[(s, o, c, e)] += 1
            for sh in (0, 4, 8, 16, 20, 24):
                fuentes[TEV_FUENTE.get((s >> sh) & 0xF, f"?{(s >> sh) & 0xF:X}")] += 1
            combs[TEV_COMB.get(c & 0xF, "?").split("(")[0] + "/rgb"] += 1
            combs[TEV_COMB.get((c >> 16) & 0xF, "?").split("(")[0] + "/a"] += 1
            escalas[(e & 3, (e >> 16) & 3)] += 1
        n_etapas_activas[activas] += 1
        for reg in (0x040, 0x0E0, 0x0FD, 0x100, 0x101, 0x104, 0x105, 0x106, 0x107, 0x080, 0x083, 0x08E,
                    0x093, 0x096, 0x09B, 0x09E, 0x1C3, 0x08F):
            if reg in st:
                otros[reg][st[reg]] += 1
    # tsv por material
    salida = os.path.join(RAIZ, "extraido", "pica_materiales.tsv")
    idx_firma = {f: k for k, (f, _) in enumerate(firmas.most_common())}
    with open(salida + ".tmp", "w", encoding="utf-8") as fh:
        fh.write("archivo\tmodelo\tmaterial\tescrituras\ttev_receta\tculling\tdepth\tblend_op\tblend_func\t"
                 "alpha_test\tupdate_buffer\tlighting_config0\n")
        for arch, nmod, nmat, st, n in mats:
            g = lambda r: f"{st[r]:08X}" if r in st else "-"  # noqa: E731
            fh.write(f"{arch}\t{nmod}\t{nmat}\t{n}\tR{idx_firma[firma_tev(st)]}\t{g(0x040)}\t{g(0x107)}\t{g(0x100)}\t"
                     f"{g(0x101)}\t{g(0x104)}\t{g(0x0E0)}\t{g(0x1C3)}\n")
    os.replace(salida + ".tmp", salida)
    # resumen en texto (markdown) a stdout
    p = print
    p(f"## Censo de materiales\n\narchivos .szs: {len(rutas)} · materiales: {len(mats)} · errores: {len(errores)}\n")
    for e in errores[:5]:
        p(f"- ERROR {e[0]}: {e[2]}")
    p(f"\n### Registros escritos por las cachés de material ({len(uso)} distintos)\n")
    p(", ".join(f"`{nombre(r)}` ({n})" for r, n in sorted(uso.items())))
    p(f"\n### Recetas TEV (6 etapas, sin el color constante): **{len(firmas)} distintas**\n")
    p("| # | materiales | ejemplo | etapas activas |\n|---|---|---|---|")
    for k, (f, n) in enumerate(firmas.most_common(25)):
        txt = "<br>".join(f"{j}: {tev(s, o, c, 0, e).split(' | k')[0]}" for j, (s, o, c, e) in enumerate(f)
                          if not tev_es_paso(s, o, c)) or "(todas de paso)"
        p(f"| R{k} | {n} | {ej_firma[f]} | {txt} |")
    p(f"\nEtapas activas por material: {dict(sorted(n_etapas_activas.items()))}")
    p(f"\nEtapas distintas (fuente+operando+combinador+escala): {len(etapas)}")
    p(f"\nFuentes usadas: {dict(fuentes.most_common())}")
    p(f"\nCombinadores: {dict(combs.most_common())}")
    p(f"\nEscalas (rgb, a) en etapas activas: {dict(escalas.most_common())}")
    for reg, cnt in otros.items():
        p(f"\n### `{nombre(reg)}` — {len(cnt)} valores distintos\n")
        for v, n in cnt.most_common(8):
            t = decodificar(reg, v)
            p(f"- `{v:08X}` × {n}" + (f" — {t}" if t else ""))


# ---------------- cabeceras en el ejecutable ----------------
def codigo():
    """Cabeceras de comando PICA en el code.bin: (1) literales que el codigo carga con ldr [pc,#k];
    (2) tablas de .rodata/.data con 3+ comandos seguidos que se parsean de corrido."""
    import capstone
    from capstone import arm
    code = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
    base, text_fin = 0x00100000, 0x00100000 + 2758524
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = True
    md.skipdata = True
    lits = collections.defaultdict(list)  # valor -> [direccion de la ldr]
    for i in md.disasm(code[:text_fin - base], base):
        if i.id != arm.ARM_INS_LDR or len(i.operands) != 2:
            continue
        mem = i.operands[1]
        if mem.type == arm.ARM_OP_MEM and mem.mem.base == arm.ARM_REG_PC and not mem.mem.index:
            p_ = i.address + 8 + mem.mem.disp
            if base <= p_ < text_fin - 3 and p_ % 4 == 0:
                v = struct.unpack_from("<I", code, p_ - base)[0]
                h = cabecera(v)
                if h and h[0] in NOMBRES and h[2] <= 32 and (h[1] == 0xF or h[0] >= 0x80):
                    lits[v].append(i.address)
    print(f"## Cabeceras PICA cargadas como literal en .text: {len(lits)} distintas\n")
    por_reg = collections.defaultdict(list)
    for v, usos in lits.items():
        por_reg[v & 0xFFFF].append((v, usos))
    for reg in sorted(por_reg):
        items = por_reg[reg]
        txt = ", ".join(f"{v:08X}×{len(u)} (p.ej. 0x{u[0]:08X})" for v, u in items[:3])
        print(f"- `{nombre(reg)}` (0x{reg:03X}): {txt}")
    # tablas en rodata/data: corridas de comandos validos parseables seguidos
    print("\n## Corridas de 3+ comandos seguidos en .rodata/.data\n")
    for seg, (s, n) in {"rodata": (0x003A2000, 257616), "data": (0x003E1000, 76244)}.items():
        k = 0
        while k < n - 8:
            j, regs = k, []
            while j < n - 8:
                v = struct.unpack_from("<I", code, s - base + j + 4)[0]
                h = cabecera(v)
                if not h or h[0] not in NOMBRES or h[2] > 32:
                    break
                regs.append(h[0])
                m = 2 + h[2]
                j += 4 * (m + (m & 1))
            if len(regs) >= 3:
                print(f"- {seg} 0x{s + k:08X}: {len(regs)} comandos: " +
                      ", ".join(nombre(r) for r in regs[:12]) + (" ..." if len(regs) > 12 else ""))
                k = j
            else:
                k += 4


def main():
    acc = sys.argv[1] if len(sys.argv) > 1 else ""
    if acc == "lista":
        d = open(sys.argv[2], "rb").read()
        for reg, mask, v in parsear(list(struct.unpack_from(f"<{len(d) // 4}I", d))):
            print(f"{nombre(reg):32} {v:08X} mask={mask:X}")
    elif acc == "material":
        filtro = sys.argv[3] if len(sys.argv) > 3 else None
        for narch, b in cgfx_de(sys.argv[2]):
            for nmod, nmat, m in materiales(b):
                if filtro and nmat != filtro:
                    continue
                cmds = comandos_material(b, m)
                print(f"== {narch} / {nmod} / {nmat} ({len(cmds)} escrituras)")
                for k, reg, mask, v in cmds:
                    t = decodificar(reg, v)
                    print(f"  +{k - m:04X} {nombre(reg):32} {v:08X} mask={mask:X}" + (f"  {t}" if t else ""))
                print(resumen_material(estado(cmds)))
    elif acc == "censo":
        censo(sys.argv[2] if len(sys.argv) > 2 else os.path.join(RAIZ, "extraido", "romfs"))
    elif acc == "codigo":
        codigo()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
