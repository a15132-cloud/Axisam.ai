import type { ChatEntry, Proyecto } from "./types";

/**
 * Pipeline cards (extraction/model/toolpath/simulation/gcode) are derived
 * fresh from `proyecto` on every render instead of being appended
 * imperatively after each action. The pipeline is strictly sequential, so
 * fixed-order derivation is not a simplification that loses information -
 * it's the correct model, and it means there is no separate copy of
 * "what card is showing" that can drift out of sync with the server's
 * actual state. Free-text chat messages are the only thing tracked
 * imperatively (see App.tsx) because they have no other source of truth.
 */
function buscarTs(proyecto: Proyecto, substr: string): string {
  const evento = proyecto.actividad.find((e) => e.titulo.toLowerCase().includes(substr.toLowerCase()));
  return evento?.ts || proyecto.actualizado_en;
}

export function derivarEntriesPipeline(proyecto: Proyecto): ChatEntry[] {
  const entries: ChatEntry[] = [];

  if (proyecto.archivo_plano) {
    entries.push({
      id: "upload",
      role: "user",
      kind: "upload",
      ts: proyecto.creado_en,
      archivoNombre: proyecto.archivo_plano,
    });
  }

  if (proyecto.pieza_extraida) {
    entries.push({
      id: "extraccion",
      role: "assistant",
      kind: "extraccion",
      ts: buscarTs(proyecto, "datos extraidos"),
      pieza: proyecto.pieza_extraida,
      confirmado: proyecto.pieza_confirmada,
    });
  }

  const step = proyecto.archivos.find((a) => a.tipo === "step");
  const stl = proyecto.archivos.find((a) => a.tipo === "stl");
  if (step || stl) {
    entries.push({
      id: "modelo",
      role: "assistant",
      kind: "modelo",
      ts: buscarTs(proyecto, "modelo 3d generado"),
      archivos: proyecto.archivos.filter((a) => a.tipo === "step" || a.tipo === "stl"),
      advertencias: proyecto.advertencias_modelo,
      featuresOmitidos: proyecto.features_omitidos_modelo,
      confirmado: proyecto.modelo_confirmado,
    });
  }

  if (proyecto.toolpath_plan) {
    entries.push({
      id: "trayectorias",
      role: "assistant",
      kind: "trayectorias",
      ts: buscarTs(proyecto, "trayectorias planeadas"),
      plan: proyecto.toolpath_plan,
      postprocesador: proyecto.postprocesador,
    });
  }

  if (proyecto.simulacion) {
    entries.push({
      id: "simulacion",
      role: "assistant",
      kind: "simulacion",
      ts: buscarTs(proyecto, "simulacion de maquinado"),
      simulacion: proyecto.simulacion,
      resuelto: proyecto.aprobacion_final,
    });
  }

  const gcode = proyecto.archivos.find((a) => a.tipo === "gcode");
  if (gcode) {
    entries.push({
      id: "codigo_g",
      role: "assistant",
      kind: "codigo_g",
      ts: buscarTs(proyecto, "codigo g exportado"),
      archivos: [gcode],
      operacionesConMovimientoReal: proyecto.codigo_g_resumen?.operaciones_con_movimiento_real ?? 0,
      operacionesSoloPlaneadas: proyecto.codigo_g_resumen?.operaciones_solo_planeadas ?? 0,
      advertencias: proyecto.codigo_g_resumen?.advertencias ?? [],
    });
  }

  if (proyecto.etapa === "rechazado") {
    entries.push({
      id: "rechazo",
      role: "assistant",
      kind: "error",
      ts: buscarTs(proyecto, "rechazado"),
      texto: "El proyecto fue rechazado. Puedes editar los datos y volver a intentar, o iniciar un nuevo proyecto.",
    });
  }

  return entries;
}
