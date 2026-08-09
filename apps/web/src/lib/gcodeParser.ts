/**
 * Real G-code interpreter for the standalone "Simulación" tool - parses
 * motion into an ordered list of 3D segments so they can be drawn and
 * played back over an uploaded model. This is path visualization only:
 * it does NOT check the tool against stock/fixtures for collisions (see
 * Axiscam's own disclosed limitation on that), it only shows where the
 * tool centerline goes and in what order, exactly as written in the file.
 *
 * Handles the same modal semantics Axiscam's own G-code emits (verified
 * against apps/orchestrator/app/cam/gcode.py's actual output: G0/G1,
 * G81/G82/G83 canned cycles with G98/G99 retract, G80 cancel, G90/G91,
 * G20/G21) plus G2/G3 arcs (I/J form) since real-world G-code from other
 * sources uses them too. Anything else recognized-but-unhandled (G18/G19
 * non-XY planes, tool comp G41/G42, rotation/scaling) is reported as an
 * explicit warning rather than silently mis-simulated.
 */

export type TipoSegmento = "rapido" | "corte" | "arco" | "taladro";

export interface SegmentoTrayectoria {
  desde: [number, number, number];
  hasta: [number, number, number];
  tipo: TipoSegmento;
  linea: number;
}

export interface ResultadoParseoGCode {
  segmentos: SegmentoTrayectoria[];
  advertencias: string[];
  lineasIgnoradas: number;
}

interface EstadoModal {
  x: number;
  y: number;
  z: number;
  absoluto: boolean;
  mmPorPulgada: number; // 1 si ya esta en mm, 25.4 si el archivo esta en pulgadas
  modoMovimiento: "G0" | "G1" | "G2" | "G3" | "G81" | "G82" | "G83" | null;
  cicloR: number | null;
  cicloZ: number | null;
  retraerAInicial: boolean; // true = G98 (retrae a Z inicial), false = G99 (retrae al plano R)
  zInicialAntesDelCiclo: number;
}

function quitarComentarios(linea: string): string {
  return linea.replace(/\([^)]*\)/g, " ").replace(/;.*/, "").trim();
}

function extraerPalabras(linea: string): Record<string, number> {
  const palabras: Record<string, number> = {};
  const regex = /([A-Za-z])\s*(-?\d+\.?\d*)/g;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(linea)) !== null) {
    palabras[m[1].toUpperCase()] = parseFloat(m[2]);
  }
  return palabras;
}

function generarArco(
  desde: [number, number, number],
  hasta: [number, number, number],
  i: number,
  j: number,
  horario: boolean
): [number, number][] {
  const cx = desde[0] + i;
  const cy = desde[1] + j;
  const r0 = Math.hypot(desde[0] - cx, desde[1] - cy);
  let a0 = Math.atan2(desde[1] - cy, desde[0] - cx);
  let a1 = Math.atan2(hasta[1] - cy, hasta[0] - cx);

  if (horario) {
    if (a1 >= a0) a1 -= 2 * Math.PI;
  } else {
    if (a1 <= a0) a1 += 2 * Math.PI;
  }

  const pasos = Math.max(8, Math.ceil((Math.abs(a1 - a0) / (Math.PI / 16)) | 0));
  const puntos: [number, number][] = [];
  for (let s = 1; s <= pasos; s++) {
    const a = a0 + ((a1 - a0) * s) / pasos;
    puntos.push([cx + r0 * Math.cos(a), cy + r0 * Math.sin(a)]);
  }
  return puntos;
}

export function parsearGCode(texto: string): ResultadoParseoGCode {
  const segmentos: SegmentoTrayectoria[] = [];
  const advertenciasSet = new Set<string>();
  let lineasIgnoradas = 0;

  const estado: EstadoModal = {
    x: 0,
    y: 0,
    z: 0,
    absoluto: true,
    mmPorPulgada: 1,
    modoMovimiento: null,
    cicloR: null,
    cicloZ: null,
    retraerAInicial: false,
    zInicialAntesDelCiclo: 0,
  };
  let posicionConocida = false;

  function agregar(hasta: [number, number, number], tipo: TipoSegmento, linea: number) {
    const desde: [number, number, number] = [estado.x, estado.y, estado.z];
    const seMueve = desde[0] !== hasta[0] || desde[1] !== hasta[1] || desde[2] !== hasta[2];
    if (posicionConocida && seMueve) {
      segmentos.push({ desde, hasta, tipo, linea });
    }
    estado.x = hasta[0];
    estado.y = hasta[1];
    estado.z = hasta[2];
    posicionConocida = true;
  }

  function resolverDestino(palabras: Record<string, number>): [number, number, number] {
    const f = estado.mmPorPulgada;
    const dx = "X" in palabras ? palabras.X * f : undefined;
    const dy = "Y" in palabras ? palabras.Y * f : undefined;
    const dz = "Z" in palabras ? palabras.Z * f : undefined;
    if (estado.absoluto) {
      return [dx ?? estado.x, dy ?? estado.y, dz ?? estado.z];
    }
    return [estado.x + (dx ?? 0), estado.y + (dy ?? 0), estado.z + (dz ?? 0)];
  }

  function ejecutarCicloCanned(palabras: Record<string, number>, tipoCiclo: "G81" | "G82" | "G83", linea: number) {
    if ("R" in palabras) estado.cicloR = palabras.R * estado.mmPorPulgada;
    if ("Z" in palabras) estado.cicloZ = palabras.Z * estado.mmPorPulgada;
    if (estado.cicloR === null || estado.cicloZ === null) {
      advertenciasSet.add(`Línea ${linea}: ciclo ${tipoCiclo} sin R o Z definidos todavía - se ignoró.`);
      return;
    }
    if (tipoCiclo === "G83") {
      advertenciasSet.add(
        "G83 (taladrado con picoteo) se simplificó a un solo movimiento de bajada/retorno - no se simulan los picoteos individuales."
      );
    }

    const f = estado.mmPorPulgada;
    const xDestino = "X" in palabras ? (estado.absoluto ? palabras.X * f : estado.x + palabras.X * f) : estado.x;
    const yDestino = "Y" in palabras ? (estado.absoluto ? palabras.Y * f : estado.y + palabras.Y * f) : estado.y;

    estado.zInicialAntesDelCiclo = estado.z;
    // Rapid to the new XY at the current Z (canned-cycle convention).
    agregar([xDestino, yDestino, estado.z], "rapido", linea);
    // Rapid down to the R plane.
    agregar([xDestino, yDestino, estado.cicloR], "rapido", linea);
    // Feed down to the cycle depth.
    agregar([xDestino, yDestino, estado.cicloZ], "taladro", linea);
    // Retract per G98 (initial Z) / G99 (R plane).
    const zRetraccion = estado.retraerAInicial ? Math.max(estado.zInicialAntesDelCiclo, estado.cicloR) : estado.cicloR;
    agregar([xDestino, yDestino, zRetraccion], "rapido", linea);
  }

  const lineasArchivo = texto.split(/\r?\n/);

  for (let idx = 0; idx < lineasArchivo.length; idx++) {
    const numeroLinea = idx + 1;
    const limpia = quitarComentarios(lineasArchivo[idx]);
    if (!limpia) continue;
    if (/^[NO]\d*$/i.test(limpia.split(/\s/)[0] ?? "")) {
      // Line/program number only (e.g. "N10", "O1001") with no other words this line - skip silently, not an error.
    }

    const palabras = extraerPalabras(limpia);
    const gCodes = limpia.match(/G0*(\d+)(?!\d*\.\d)/g)?.map((g) => `G${parseInt(g.slice(1), 10)}`) ?? [];

    let huboComandoReconocido = gCodes.length > 0;

    for (const g of gCodes) {
      switch (g) {
        case "G20":
          estado.mmPorPulgada = 25.4;
          break;
        case "G21":
          estado.mmPorPulgada = 1;
          break;
        case "G90":
          estado.absoluto = true;
          break;
        case "G91":
          estado.absoluto = false;
          break;
        case "G98":
          estado.retraerAInicial = true;
          break;
        case "G99":
          estado.retraerAInicial = false;
          break;
        case "G80":
          estado.modoMovimiento = null;
          estado.cicloR = null;
          estado.cicloZ = null;
          break;
        case "G0":
        case "G1":
        case "G2":
        case "G3":
          estado.modoMovimiento = g as EstadoModal["modoMovimiento"];
          break;
        case "G81":
        case "G82":
        case "G83":
          estado.modoMovimiento = g as EstadoModal["modoMovimiento"];
          break;
        case "G17":
          break; // XY plane - the only one this parser supports, and also Axiscam's own default
        case "G18":
        case "G19":
          advertenciasSet.add(`Línea ${numeroLinea}: ${g} (plano no-XY) no está soportado por este simulador - la trayectoria mostrada puede ser incorrecta.`);
          break;
        case "G40":
        case "G41":
        case "G42":
          if (g !== "G40") advertenciasSet.add(`Línea ${numeroLinea}: compensación de radio de herramienta (${g}) no está simulada - se dibuja la trayectoria programada, no la compensada.`);
          break;
        default:
          break; // recognized-but-geometrically-irrelevant G code (G28, G54..G59, G43, etc.) - fine, no warning
      }
    }

    const huboXYZ = "X" in palabras || "Y" in palabras || "Z" in palabras;

    if (estado.modoMovimiento === "G0" && huboXYZ) {
      agregar(resolverDestino(palabras), "rapido", numeroLinea);
    } else if (estado.modoMovimiento === "G1" && huboXYZ) {
      agregar(resolverDestino(palabras), "corte", numeroLinea);
    } else if ((estado.modoMovimiento === "G2" || estado.modoMovimiento === "G3") && huboXYZ) {
      const destino = resolverDestino(palabras);
      if ("I" in palabras || "J" in palabras) {
        const i = ("I" in palabras ? palabras.I : 0) * estado.mmPorPulgada;
        const j = ("J" in palabras ? palabras.J : 0) * estado.mmPorPulgada;
        const puntos = generarArco([estado.x, estado.y, estado.z], destino, i, j, estado.modoMovimiento === "G2");
        for (const [px, py] of puntos) {
          agregar([px, py, destino[2]], "arco", numeroLinea);
        }
      } else {
        advertenciasSet.add(`Línea ${numeroLinea}: arco ${estado.modoMovimiento} sin I/J (formato de radio R no soportado) - se dibujó como línea recta.`);
        agregar(destino, "arco", numeroLinea);
      }
    } else if (estado.modoMovimiento && ["G81", "G82", "G83"].includes(estado.modoMovimiento) && (huboXYZ || "R" in palabras)) {
      ejecutarCicloCanned(palabras, estado.modoMovimiento as "G81" | "G82" | "G83", numeroLinea);
    } else if (huboXYZ && !estado.modoMovimiento) {
      advertenciasSet.add(`Línea ${numeroLinea}: coordenadas sin un modo de movimiento activo (G0/G1/G2/G3) todavía - se ignoró.`);
      huboComandoReconocido = true;
    } else if (!huboComandoReconocido && !huboXYZ) {
      lineasIgnoradas++;
    }
  }

  return { segmentos, advertencias: Array.from(advertenciasSet), lineasIgnoradas };
}
