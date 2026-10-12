R = [
("    g_p1_modo = s ? (atoi(s) ? 1 : 0) : 1;\n",
 "    g_p1_modo = s && *s ? (atoi(s) ? 1 : 0) : 1;   /* vacia = sin poner (Start-Process puede pasar \"\") */\n"),
("    if (!(++g_p1_llamadas & 0x1FFFFF))\n",
 "    if (!(++g_p1_llamadas & 0x3FFFF))\n"),
]
