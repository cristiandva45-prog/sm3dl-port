R = [
("    const unsigned pista = (x->direccion * 2654435761u) >> 22;\n"
 "    TexCache *ya = &g_tex[g_tex_pista[pista]];\n"
 "    const int ya_vale = g_p1_modo && ya->tex && ya->vista && ya->dir == x->direccion && ya->w == x->ancho && ya->h == x->alto &&\n"
 "                        ya->fmt == x->formato && ya->niveles == (uint32_t)niveles && ya->cuadro == cuadro &&\n"
 "                        ya->gen == g_tex_gen && ya->hd == hd_on;\n",
 "    /* pista por la clave entera (la misma direccion con otro tamanio / mips es otra entrada); si falla, recorrido */\n"
 "    const unsigned pista = ((x->direccion ^ (x->ancho << 20) ^ (x->alto << 8) ^ (x->formato << 4) ^ ((uint32_t)niveles << 28)) *\n"
 "                            2654435761u) >> 22;\n"
 "#define P1_ES(c) ((c)->tex && (c)->dir == x->direccion && (c)->w == x->ancho && (c)->h == x->alto && (c)->fmt == x->formato && \\\n"
 "                  (c)->niveles == (uint32_t)niveles)\n"
 "    TexCache *ya = &g_tex[g_tex_pista[pista]];\n"
 "    if (g_p1_modo && !P1_ES(ya)) {\n"
 "        ya = NULL;\n"
 "        for (int k = 0; k < 256; k++) if (P1_ES(&g_tex[k])) { ya = &g_tex[k]; g_tex_pista[pista] = (uint8_t)k; break; }\n"
 "    }\n"
 "#undef P1_ES\n"
 "    const int ya_vale = g_p1_modo && ya && ya->vista && ya->cuadro == cuadro && ya->gen == g_tex_gen && ya->hd == hd_on;\n"),
]
