R = [
("void (*gsp_antes_de_escribir)(uint32_t fisica, uint32_t tam);\nint gsp_presentando;\n",
"void (*gsp_antes_de_escribir)(uint32_t fisica, uint32_t tam);\nint gsp_presentando;\n"
"/* P1 (10 oct): avisos para la cache de texturas del raster (textura_para deja de re-hashear lo que no cambio).\n"
"   gsp_tras_escribir: TODA escritura de memoria hecha por la GPU emulada (copiar_fisica/copiar_virtual con escribir =\n"
"   fills, transfers, texcopy, DMA, bajadas de RT, copias de la re-ejecucion) + las escrituras de CPU que el juego avisa\n"
"   como en el 3DS real (Flush/InvalidateDataCache 0x08/0x09 y el GX 5 CacheFlush). Las escrituras de CPU sin aviso van\n"
"   directo a memoria (rt_pagina) y nadie las ve: para esas el raster re-valida una vez por cuadro (gsp_cuadro_tex).\n"
"   gsp_cuadro_tex: +1 en la DisplayTransfer de abajo (la que cierra el cuadro), NO en las re-ejecuciones del 144. */\n"
"void (*gsp_tras_escribir)(uint32_t fisica, uint32_t tam);\nuint32_t gsp_cuadro_tex;\n"),
("static int copiar_fisica(u32 fisica, u8 *buf, u32 tam, int escribir)\n{\n    u32 hecho = 0;\n",
"static int copiar_fisica(u32 fisica, u8 *buf, u32 tam, int escribir)\n{\n    u32 hecho = 0;\n"
"    if (escribir && gsp_tras_escribir) gsp_tras_escribir(fisica, tam);   /* P1 */\n"),
("static int copiar_virtual(u32 v, u8 *buf, u32 tam, int escribir)\n{\n    u32 hecho = 0;\n",
"/* P1: aviso de escritura por direccion VIRTUAL (DMA, flush de cache): las regiones visibles por la GPU son lineales */\n"
"void gsp_cpu_escribio(uint32_t v, uint32_t tam)\n{\n"
"    if (!gsp_tras_escribir || !tam) return;\n"
"    u32 f = gsp_virtual_a_fisica(v);\n"
"    if (f) gsp_tras_escribir(f, tam);\n}\n\n"
"static int copiar_virtual(u32 v, u8 *buf, u32 tam, int escribir)\n{\n    u32 hecho = 0;\n"
"    if (escribir) gsp_cpu_escribio(v, tam);   /* P1 */\n"),
("    case 5:                                               /* CacheFlush: no hay caches que vaciar */\n        break;\n",
"    case 5:                                               /* CacheFlush: no hay caches que vaciar */\n"
"        for (int k = 0; k < 3; k++) if (c[1 + 2 * k]) gsp_cpu_escribio(c[1 + 2 * k], c[2 + 2 * k]);   /* P1: la CPU escribio ahi */\n"
"        break;\n"),
("    case 0x08: case 0x09:                                 /* Flush/InvalidateDataCache: no hay cache */\n        responder(cmd, id, 1, 0, 0);\n",
"    case 0x08: case 0x09:                                 /* Flush/InvalidateDataCache: no hay cache */\n"
"        gsp_cpu_escribio(cmd[1], cmd[2]);                 /* P1: (dir, tam) que la CPU acaba de escribir */\n"
"        responder(cmd, id, 1, 0, 0);\n"),
("        if (!arriba && !es_der) {   /* la de abajo cierra el cuadro */\n",
"        if (!arriba && !es_der) {   /* la de abajo cierra el cuadro */\n"
"            if (!g_repitiendo) gsp_cuadro_tex++;   /* P1: frontera de re-validacion de texturas (no en intermedios) */\n"),
]
