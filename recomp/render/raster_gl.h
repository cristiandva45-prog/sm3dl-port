/* Rasterizador del port (ver raster_gl.c). Desde el 8 oct 2026 la GPU se maneja por la interfaz de backend
   (raster_backend.h); SM3DL_BACKEND=gl (default) | d3d12 (aun no implementado: cae a gl). Esta cabecera NO cambia: las
   funciones de abajo son la API publica de siempre y los ids de textura que devuelven son del backend activo (GL: nombre
   de textura GL). Las raster_pres_* se declaran en ventana_gpu.c. */
#ifndef RASTER_GL_H
#define RASTER_GL_H

/* engancha el rasterizador: pica_raster (dibujos) + gsp_antes_de_leer / gsp_tras_fill (sincronizacion con la
   memoria emulada). El contexto GL se crea en el primer dibujo. SM3DL_SIN_RASTER=1 lo deja apagado. */
void raster_iniciar(void);

/* SM3DL_RASTER_DESDE=N (pruebas, junto con SM3DL_TURBO): el raster queda sin enganchar hasta el vblank N, asi la
   intro corre a velocidad de CPU. Se llama en cada tick del mando con el vblank actual. */
void raster_vblank(unsigned vblank);

/* resolucion interna (7 oct): los RT se dibujan s veces mas grandes (1-4); lo que el juego lee sigue nativo */
void raster_escala(int s);
/* la pantalla que se presenta desde 'dir_fisica', en alta: devuelve s (>1) y *rgba de (ancho*s) x (alto*s), fila 0
   arriba; 0 si no hay copia en alta para ese framebuffer (se usa la imagen nativa de siempre) */
int raster_alta(unsigned dir_fisica, unsigned fmt, unsigned stride, unsigned ancho, unsigned alto,
                const unsigned char **rgba);

/* API PARA B (agente A, 7 oct noche; contrato en agentes_7oct\A.md "API PARA B"). Presentar por GL sin bajar la imagen:
   la pantalla 'dir_fisica' en alta YA GIRADA como textura GL (ancho*s x alto*s, GL_RGBA8, fila 0 ABAJO como toda textura
   GL: dibujada tal cual en el framebuffer 0 queda derecha). Devuelve s (>1) o 0 si no hay alta (usar la nativa).
   *gen cambia cuando hay un cuadro nuevo. La textura es del raster: no borrarla ni cambiarle parametros; vale hasta la
   siguiente llamada a raster_alta / raster_alta_textura. Mismos argumentos que raster_alta. */
int raster_alta_textura(unsigned dir_fisica, unsigned fmt, unsigned stride, unsigned ancho, unsigned alto,
                        unsigned *tex_gl, int *s, unsigned *gen);
/* deja el contexto GL del raster actual sobre el HDC de la ventana visible (le copia el pixel format si no tiene).
   1 si quedo. Despues: dibujar en el framebuffer 0 y SwapBuffers(hdc). */
int raster_gl_hacer_actual(void *hdc);
/* copia la ultima textura de raster_alta_textura al rectangulo [x0,x1)x[y0,y1) del framebuffer 0 (coordenadas GL,
   origen abajo a la izquierda); lineal: filtro GL_LINEAR (si no, NEAREST). No hace SwapBuffers. */
int raster_alta_a_ventana(int x0, int y0, int x1, int y1, int lineal);

#endif
