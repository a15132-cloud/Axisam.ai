import type { ChatEntry, Proyecto } from "./types";

/**
 * Pipeline cards (extraction/model) are derived fresh from `proyecto` on
 * every render instead of being appended
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
      // pieza_extraida ya esta poblada desde la primera pasada (ver el
      // docstring de subir_plano en el backend - es una red de seguridad
      // en caso de que la segunda pasada nunca llegue a completarse), pero
      // eso significa que esta tarjeta puede aparecer en pantalla MIENTRAS
      // la segunda pasada (verificacion) todavia esta en curso, minutos
      // antes de que etapa avance a esperando_confirmacion_extraccion. Un
      // click en cualquier boton de accion durante esa ventana choca
      // contra una precondicion del backend que todavia no se cumple - un
      // error confuso por algo que en unos segundos mas se hubiera resuelto
      // solo. verificando le dice a PiezaCard que desactive esos botones
      // mientras tanto.
      verificando: proyecto.etapa === "extrayendo",
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

  // No hay entries de trayectorias/simulacion/codigo_g - Axiscam es CAD
  // only ahora (plano -> STEP/STL, ver approval.confirmar_modelo en el
  // backend). proyecto.toolpath_plan/simulacion/codigo_g_resumen se
  // quedan definidos en el schema pero nunca se llenan por este flujo.

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
