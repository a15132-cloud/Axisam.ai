"""Best-effort textual summary of a DXF file's entities, for feeding to
Claude as context when there is no raster image of the drawing.

DXF is a documented, mostly-text vector format so this is tractable
without a CAD engine. DWG is a proprietary binary format Autodesk has
never fully documented; reading it needs Autodesk's own ODA File
Converter, which is not available here - callers should ask the user to
export DWG -> DXF/PDF instead rather than pretend to parse it.
"""

from __future__ import annotations

import io

import ezdxf
from ezdxf import DXFError


class DXFLecturaError(Exception):
    pass


def resumen_textual_dxf(contenido: bytes, max_entidades_por_tipo: int = 60) -> str:
    try:
        texto = contenido.decode("utf-8", errors="replace")
        doc = ezdxf.read(io.StringIO(texto))
    except (DXFError, ValueError) as exc:
        raise DXFLecturaError(f"No se pudo leer el archivo DXF: {exc}") from exc

    msp = doc.modelspace()
    partes: list[str] = []

    unidades = doc.header.get("$INSUNITS", None)
    partes.append(f"Unidades (codigo INSUNITS DXF): {unidades}")

    textos = [e.dxf.text for e in msp.query("TEXT") if e.dxf.text.strip()]
    mtextos = [e.plain_text() for e in msp.query("MTEXT") if e.plain_text().strip()]
    if textos or mtextos:
        partes.append("\nTexto encontrado en el dibujo (posible cajetin, notas, cotas con texto):")
        for t in (textos + mtextos)[:max_entidades_por_tipo]:
            partes.append(f"  - {t}")

    dims = list(msp.query("DIMENSION"))
    if dims:
        partes.append(f"\nCotas (entidades DIMENSION), {len(dims)} encontradas:")
        for d in dims[:max_entidades_por_tipo]:
            texto_cota = (d.dxf.text or "").strip()
            medida = None
            try:
                medida = d.get_measurement()
            except Exception:
                pass
            partes.append(f"  - texto='{texto_cota or '<auto>'}' medida_calculada={medida}")

    circulos = list(msp.query("CIRCLE"))
    if circulos:
        partes.append(f"\nCirculos (posibles barrenos), {len(circulos)} encontrados:")
        for c in circulos[:max_entidades_por_tipo]:
            partes.append(
                f"  - centro=({c.dxf.center.x:.3f}, {c.dxf.center.y:.3f}) radio={c.dxf.radius:.3f} "
                f"diametro={c.dxf.radius * 2:.3f} capa='{c.dxf.layer}'"
            )

    arcos = list(msp.query("ARC"))
    if arcos:
        partes.append(f"\nArcos (posibles redondeos), {len(arcos)} encontrados:")
        for a in arcos[:max_entidades_por_tipo]:
            partes.append(f"  - centro=({a.dxf.center.x:.3f}, {a.dxf.center.y:.3f}) radio={a.dxf.radius:.3f} capa='{a.dxf.layer}'")

    lineas_entidad = list(msp.query("LINE"))
    if lineas_entidad:
        partes.append(f"\nLineas rectas, {len(lineas_entidad)} encontradas (primeras {max_entidades_por_tipo}):")
        for l in lineas_entidad[:max_entidades_por_tipo]:
            p1, p2 = l.dxf.start, l.dxf.end
            largo = ((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2) ** 0.5
            partes.append(f"  - ({p1.x:.3f},{p1.y:.3f}) -> ({p2.x:.3f},{p2.y:.3f}) longitud={largo:.3f} capa='{l.dxf.layer}'")

    polilineas = list(msp.query("LWPOLYLINE"))
    if polilineas:
        partes.append(f"\nPolilineas (posibles contornos/perfiles), {len(polilineas)} encontradas:")
        for p in polilineas[:max_entidades_por_tipo]:
            puntos = list(p.get_points())
            cerrada = p.closed
            partes.append(f"  - {len(puntos)} vertices, cerrada={cerrada}, capa='{p.dxf.layer}'")

    if len(partes) == 1:
        partes.append("\n(No se encontraron entidades TEXT/MTEXT/DIMENSION/CIRCLE/ARC/LINE/LWPOLYLINE reconocibles)")

    return "\n".join(partes)
