/* PRESENTADOR D3D12 (8 oct noche): el equivalente de presentador_gl.inc sobre d3d12_base/d3d12_recursos.
 *   - RANURAS: copias de la pantalla de arriba en alta, para guardar los intermedios de un cuadro y mostrarlos cada
 *     uno a su hora (modo Monitor; dos juegos de 8).
 *   - BASE: la imagen del juego (una ranura o una textura cualquiera) escalada al rectangulo de la ventana, nitida
 *     (punto) o suave (lineal). D3D12 no tiene BlitFramebuffer: es un rectangulo texturizado.
 *   - CAPAS: imagenes BGRA PREMULTIPLICADAS de la CPU (HUD integrado, interfaz) que se suben solo en la zona que
 *     cambio y se dibujan encima con mezcla (ONE, ONE_MINUS_SRC_ALPHA).
 * Coordenadas de ventana con y0 desde ARRIBA (como el camino GL). Las texturas D3D12 guardan la fila 0 arriba; si la
 * fuente viene al reves, 'invertir' = 1. HLSL compilado en vivo con d3dcompiler_47 (de Windows; son 2 shaders
 * chicos: no hace falta la cadena DXC del agente B). */
#ifndef D3D12_PRESENTADOR_H
#define D3D12_PRESENTADOR_H
#include "d3d12_recursos.h"

#define D3DP_RANURAS 16

int d3dp_iniciar(void);
/* copia 'fuente' (la pantalla de arriba en alta) a la ranura r */
int d3dp_guardar(ID3D12GraphicsCommandList *l, D3dTextura *fuente, int r);
D3dTextura *d3dp_ranura(int r);
/* empieza: limpia el buffer de atras de la swap chain a negro (la lista ya esta abierta con d3d_empezar_cuadro) */
int d3dp_empezar(ID3D12GraphicsCommandList *l);
int d3dp_base(ID3D12GraphicsCommandList *l, D3dTextura *t, int x0, int y0, int x1, int y1, int lineal, int invertir);
int d3dp_subir(ID3D12GraphicsCommandList *l, int c, const uint8_t *bgra, int w, int h, int x0, int y0, int x1, int y1);
int d3dp_capa(ID3D12GraphicsCommandList *l, int c, int x0, int y0, int x1, int y1, int lineal);
/* copia lo compuesto (BGRA, fila 0 ARRIBA) a 'bgra' para verificar: espera a la GPU (solo verificacion) */
int d3dp_leer(ID3D12GraphicsCommandList *l, uint8_t *bgra);

#endif
