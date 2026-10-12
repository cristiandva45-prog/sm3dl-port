"""Lector de BYML (datos de niveles y configuracion) -> JSON.

Uso:
  py -I byml.py <archivo.byml> [salida.json]
  py -I byml.py --szs <archivo.szs> <nombre_interno.byml> [salida.json]
"""
import json
import os
import struct
import sys


class Byml:
    def __init__(self, datos):
        self.d = datos
        if datos[:2] == b"YB":
            self.e = "<"
        elif datos[:2] == b"BY":
            self.e = ">"
        else:
            raise ValueError(f"no es BYML: {datos[:4]!r}")
        self.version = self.u16(2)
        self.claves = self.tabla_strings(self.u32(4))
        self.textos = self.tabla_strings(self.u32(8))
        # La raiz suele ir en 0x0C; algunas variantes meten una tabla de rutas ahi y la raiz en 0x10
        raiz_off = self.u32(0x0C)
        if raiz_off >= len(datos) or datos[raiz_off] not in (0xC0, 0xC1):
            raiz_off = self.u32(0x10)
        self.raiz = self.nodo(self.d[raiz_off], raiz_off)

    def u16(self, o):
        return struct.unpack_from(self.e + "H", self.d, o)[0]

    def u32(self, o):
        return struct.unpack_from(self.e + "I", self.d, o)[0]

    def u24(self, o):
        b = self.d[o:o + 3]
        return int.from_bytes(b, "little" if self.e == "<" else "big")

    def tabla_strings(self, off):
        if off == 0:
            return []
        assert self.d[off] == 0xC2, f"tabla de strings esperada en {off:#x}"
        n = self.u24(off + 1)
        out = []
        for i in range(n):
            ini = off + self.u32(off + 4 + 4 * i)
            crudo = self.d[ini:self.d.index(b"\0", ini)]
            try:
                out.append(crudo.decode("cp932"))  # los textos de Nintendo van en Shift-JIS
            except UnicodeDecodeError:
                out.append(crudo.decode("utf-8", "replace"))
        return out

    def valor(self, tipo, crudo):
        if tipo == 0xA0:
            return self.textos[crudo]
        if tipo == 0xD0:
            return bool(crudo)
        if tipo == 0xD1:
            return struct.unpack(self.e + "i", struct.pack(self.e + "I", crudo))[0]
        if tipo == 0xD2:
            return round(struct.unpack(self.e + "f", struct.pack(self.e + "I", crudo))[0], 6)
        if tipo == 0xD3:
            return crudo
        if tipo == 0xFF:
            return None
        if tipo in (0xC0, 0xC1):
            return self.nodo(tipo, crudo)
        return f"<tipo {tipo:#x}: {crudo:#x}>"

    def nodo(self, tipo, off):
        assert self.d[off] == tipo, f"nodo {tipo:#x} esperado en {off:#x}, hay {self.d[off]:#x}"
        n = self.u24(off + 1)
        if tipo == 0xC0:
            tipos = self.d[off + 4:off + 4 + n]
            base = off + 4 + ((n + 3) & ~3)
            return [self.valor(tipos[i], self.u32(base + 4 * i)) for i in range(n)]
        if tipo == 0xC1:
            out = {}
            for i in range(n):
                e = off + 4 + 8 * i
                clave = self.claves[self.u24(e)]
                out[clave] = self.valor(self.d[e + 3], self.u32(e + 4))
            return out
        raise ValueError(f"tipo de nodo raiz no soportado {tipo:#x}")


def main():
    if sys.argv[1] == "--szs":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import szs
        contenido = dict(szs.sarc(szs.yaz0(open(sys.argv[2], "rb").read())))
        datos = contenido[sys.argv[3]]
        salida = sys.argv[4] if len(sys.argv) > 4 else None
    else:
        datos = open(sys.argv[1], "rb").read()
        salida = sys.argv[2] if len(sys.argv) > 2 else None
    b = Byml(datos)
    texto = json.dumps(b.raiz, ensure_ascii=False, indent=1)
    if salida:
        with open(salida + ".tmp", "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(salida + ".tmp", salida)
        print(f"BYML v{b.version} -> {salida} ({len(texto):,} caracteres)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(texto)


if __name__ == "__main__":
    main()
