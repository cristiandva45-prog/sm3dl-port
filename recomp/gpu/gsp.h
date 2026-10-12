/* Servicio gsp::Gpu en HLE para el port nativo (paso 4, parte GPU).
 *
 * Que hace (Azahar hle\service\gsp + video_core\gpu.cpp + sw_blitter.cpp usados SOLO como lectura de referencia):
 *   - IPC: RegisterInterruptRelayQueue (shm 0x1000 + evento), AcquireRight/ReleaseRight, WriteHWRegs(+WithMask),
 *     ReadHWRegs, Flush/InvalidateDataCache (no-op), SetLcdForceBlack, TriggerCmdReqQueue y stubs "OK" del resto.
 *   - Cola GX por hilo en shm+0x800+hilo*0x200 (15 comandos de 0x20): RequestDma(0), ProcessCommandList(1, entrega
 *     la lista a pica_ejecutar), MemoryFill(2), DisplayTransfer(3), TextureCopy(4), CacheFlush(5, no-op).
 *   - Interrupciones: cola de relevo por hilo en shm+hilo*0x40 (PSC0, PSC1, PDC0=VBlank0, PDC1=VBlank1, PPF, P3D, DMA).
 *   - gsp_vblank(): PDC0/PDC1 a todos los hilos registrados; aplica FrameBufferUpdate de shm+0x200+(2*hilo+pantalla)*0x40
 *     si esta "dirty" y entrega el framebuffer que muestra cada pantalla al callback de presentacion.
 *
 * Modulo AUTONOMO: no incluye sistema.h. El integrador (sistema.c) le da un GspAnfitrion con la memoria del juego,
 * la creacion del bloque compartido y la senal de eventos. Ver "pedido de integracion" en agentes_8oct\E.md.
 */
#ifndef GSP_H
#define GSP_H

#include <stdint.h>
#include <stddef.h>

/* ---------------------------------------------------------------- contrato con el render (agente F) */
/* Interprete PICA: ejecuta la lista de comandos en la direccion FISICA dada (tam en bytes). Lo implementa
   recomp\render\pica.c. El GSP no lo enlaza directo: llama al gancho gsp_pica (el integrador hace gsp_pica = pica_ejecutar).
   El GSP senala P3D al volver (el FINALIZE de la lista no necesita avisar al GSP). */
void pica_ejecutar(uint32_t dir_fisica, uint32_t tam);
typedef void (*GspPicaFn)(uint32_t dir_fisica, uint32_t tam);
extern GspPicaFn gsp_pica;   /* NULL = la lista se ignora (se registra en el log) */
/* sincronizacion con el rasterizador (8 oct; NULL = sin rasterizador):
   - gsp_antes_de_leer: antes de LEER memoria fisica para un DisplayTransfer / TextureCopy / presentar. El
     rasterizador vuelca ahi lo que tenga dibujado en la GPU y aun no este en la memoria emulada.
   - gsp_tras_fill: despues de un MemoryFill (ya escrito en memoria): si cae sobre un render target, el
     rasterizador lo convierte en un clear. */
extern void (*gsp_antes_de_leer)(uint32_t fisica, uint32_t tam);
extern void (*gsp_tras_fill)(uint32_t ini, uint32_t fin, uint32_t valor, uint32_t control);

/* ---------------------------------------------------------------- interrupciones */
enum { GSP_INT_PSC0 = 0, GSP_INT_PSC1 = 1, GSP_INT_PDC0 = 2, GSP_INT_PDC1 = 3, GSP_INT_PPF = 4, GSP_INT_P3D = 5,
       GSP_INT_DMA = 6 };

/* ---------------------------------------------------------------- formatos de pixel (framebuffer / transfer) */
enum { GSP_RGBA8 = 0, GSP_RGB8 = 1, GSP_RGB565 = 2, GSP_RGB5A1 = 3, GSP_RGBA4 = 4 };
int gsp_bytes_pixel(int fmt);                         /* 4,3,2,2,2; 0 si invalido */
void gsp_decodificar_pixel(int fmt, const uint8_t *p, uint8_t rgba[4]);
void gsp_codificar_pixel(int fmt, const uint8_t rgba[4], uint8_t *p);
/* offset en bytes del pixel (x,y) dentro de una imagen en mosaicos 8x8 Morton de 'ancho' pixeles */
uint32_t gsp_offset_morton(uint32_t x, uint32_t y, uint32_t ancho, uint32_t bpp);

/* ---------------------------------------------------------------- operaciones puras (memoria del anfitrion) */
typedef struct {
    uint32_t ancho_entrada, alto_entrada, ancho_salida, alto_salida;
    uint32_t flags;   /* registro de flags del transfer: bit0 voltear, bit1 entrada lineal, bit2 recortar, bit3 texcopy,
                         bit5 no reordenar, 8-10 formato entrada, 12-14 formato salida, 24-25 escala (0 no, 1 X, 2 XY) */
} GspTransfer;
/* devuelve 0 si ok, -1 si los parametros no se soportan (en ese caso no escribe nada) */
int gsp_display_transfer(const uint8_t *entrada, uint8_t *salida, const GspTransfer *t);
/* bytes de entrada/salida que toca el transfer (para copiar desde/hacia la memoria del juego) */
void gsp_display_transfer_tam(const GspTransfer *t, uint32_t *tam_entrada, uint32_t *tam_salida);
/* DisplayTransfer diferido (sesion de velocidad, 7 oct; NULL = sin rasterizador):
   - gsp_transfer_diferido: si devuelve 1, el rasterizador se queda con el transfer (lo completa mas tarde, cuando
     la GPU ya termino) y el GSP no copia nada. Devuelve 0 si no puede (el GSP lo hace como siempre).
   - gsp_antes_de_escribir: antes de que el GSP ESCRIBA memoria fisica (MemoryFill / salida de un transfer), para
     que el rasterizador complete antes lo pendiente que caiga ahi. */
extern int (*gsp_transfer_diferido)(uint32_t ent, uint32_t sal, const GspTransfer *t, uint32_t te, uint32_t ts);
extern void (*gsp_antes_de_escribir)(uint32_t fisica, uint32_t tam);
/* 1 mientras presentar() llama a gsp_antes_de_leer: el rasterizador no espera a la GPU por un transfer diferido
   (si aun no termino, se muestra lo que haya en el framebuffer: un cuadro de retraso) */
extern int gsp_presentando;
/* TextureCopy: tam total (multiplo de 16), ancho/hueco en unidades de 16 bytes (registros input_size/output_size) */
void gsp_texture_copy(const uint8_t *entrada, uint8_t *salida, uint32_t tam, uint32_t reg_entrada, uint32_t reg_salida);
void gsp_texture_copy_tam(uint32_t tam, uint32_t reg_entrada, uint32_t reg_salida, uint32_t *tam_entrada, uint32_t *tam_salida);
/* MemoryFill: control = registro de control (bit8 relleno 24 bits, bit9 relleno 32 bits; si no, 16 bits) */
void gsp_memory_fill(uint8_t *ini, uint8_t *fin, uint32_t valor, uint32_t control);

/* ---------------------------------------------------------------- presentacion */
typedef struct {
    int pantalla;                 /* 0 arriba, 1 abajo */
    int negro;                    /* SetLcdForceBlack activo: mostrar negro */
    uint32_t dir_fisica;          /* framebuffer que se muestra (izquierdo) */
    uint32_t formato, stride;     /* registro de formato (bits 0-2 = GSP_*) y stride en bytes */
    uint32_t ancho, alto;         /* imagen YA ENDEREZADA: 400x240 arriba, 320x240 abajo */
    const uint8_t *rgba;          /* ancho*alto*4, fila 0 arriba; NULL si el framebuffer no esta mapeado */
} GspPresentacion;
/* memoria del framebuffer tal como la guarda el 3DS (columnas de 240 de abajo arriba) -> RGBA enderezado */
void gsp_framebuffer_a_rgba(const uint8_t *fb, int fmt, uint32_t stride, uint32_t ancho, uint32_t alto, uint8_t *rgba);

/* ---------------------------------------------------------------- integracion */
typedef struct {
    /* memoria del juego vista desde el anfitrion, por direccion VIRTUAL; NULL si no esta mapeada. Solo se pide
       una pagina por vez (no se asume contiguidad entre paginas). */
    uint8_t *(*puntero)(uint32_t dir_virtual);
    /* crea el bloque compartido de GSP (tam bytes, en cero): devuelve el handle para el juego y su memoria */
    uint32_t (*crear_shm)(uint32_t tam, uint8_t **host);
    /* senala el evento de interrupcion que el juego paso en RegisterInterruptRelayQueue */
    void (*senalar_evento)(uint32_t handle);
    /* framebuffer de una pantalla, en cada VBlank (puede ser NULL) */
    void (*presentar)(const GspPresentacion *p);
    void (*log)(const char *texto);    /* puede ser NULL */
} GspAnfitrion;

void gsp_iniciar(const GspAnfitrion *a);
/* atiende un comando IPC de gsp::Gpu. cmd = buffer de comando (TLS+0x80); la tabla de buffers estaticos de
   recepcion esta en cmd+0x40 palabras (TLS+0x180). sesion = identificador estable de la sesion (su handle). */
void gsp_ipc(uint32_t *cmd, uint32_t sesion);
/* VBlank de las dos pantallas (llamarlo a ~59,83 Hz desde el planificador) */
void gsp_vblank(void);
/* procesa la cola GX del hilo con derechos (lo hace TriggerCmdReqQueue; expuesto por si el integrador quiere sondear) */
void gsp_procesar_cola(void);
/* senala una interrupcion como el hardware (PDC a todos; el resto al hilo con derechos) */
void gsp_interrupcion(int id);

/* conversion de direcciones como Horizon (para el gancho pica_memoria del agente F) */
uint32_t gsp_virtual_a_fisica(uint32_t v);   /* 0 si no es memoria visible por la GPU */
uint32_t gsp_fisica_a_virtual(uint32_t f);   /* 0 si no corresponde */
/* puntero del anfitrion para [fisica, fisica+tam) si es contiguo; NULL si no (entonces copiar con gsp_leer_fisica) */
const uint8_t *gsp_fisica_a_host(uint32_t fisica, uint32_t tam);
int gsp_leer_fisica(uint32_t fisica, void *dst, uint32_t tam);          /* 0 ok, -1 si falta alguna pagina */
int gsp_escribir_fisica(uint32_t fisica, const void *src, uint32_t tam);

/* ---------------------------------------------------------------- estado (pruebas y depuracion) */
#define GSP_REG_GPU_BASE  0x1EF00000u   /* registros externos de la GPU (WriteHWRegs 0x400000) */
#define GSP_REG_LCD_BASE  0x1ED02000u   /* registros LCD (WriteHWRegs 0x202000) */
uint32_t gsp_leer_reg(uint32_t dir_io);              /* dir_io = 0x1EB00000 + offset de WriteHWRegs */
void gsp_escribir_reg(uint32_t dir_io, uint32_t v);  /* con efectos (disparos de fill/transfer/lista) */
typedef struct {
    uint32_t listas, fills, transfers, texcopies, dmas, vblanks, presentaciones, swaps;
    uint32_t hilo_con_derechos;   /* 0xFFFFFFFF = nadie */
    int forzar_negro;
} GspEstadistica;
const GspEstadistica *gsp_estadistica(void);
/* UN SOLO OJO (7 oct): el juego dibuja SIEMPRE los dos ojos (aunque el deslizador 3D este en 0) y el port solo
   muestra el izquierdo. 1 = los dibujos que vienen son del ojo DERECHO de la pantalla de arriba: pica_dibujar.c no
   los rasteriza y la transfer del ojo derecho no se hace. SM3DL_UN_OJO=0 lo apaga. */
extern int gsp_ojo_derecho;

#endif
