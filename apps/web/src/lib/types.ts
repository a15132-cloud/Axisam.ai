// Mirrors app/schemas/*.py on the orchestrator. Keep field names identical
// (snake_case, as the API returns them) rather than translating to camelCase -
// one less place for the two sides to drift apart.

export type TipoMaquinado = "fresado" | "torneado" | "fresado_multieje";

export type TipoFeature =
  | "barreno"
  | "barreno_roscado"
  | "cajera"
  | "perfil_exterior"
  | "chaflan"
  | "redondeo"
  | "ranura"
  | "escalon"
  | "saliente";

export type FormaBase = "rectangular" | "circular" | "poligonal" | "revolucion";

export interface Posicion2D {
  x: number;
  y: number;
}

export interface SimboloGDT {
  tipo: string;
  valor_mm: number;
  datum_referencia?: string | null;
  aplica_a?: string | null;
}

export interface Feature {
  id?: string | null;
  tipo: TipoFeature;
  diametro_mm?: number | null;
  profundidad_mm?: number | null;
  ancho_mm?: number | null;
  largo_mm?: number | null;
  radio_mm?: number | null;
  angulo_grados?: number | null;
  posicion?: Posicion2D | null;
  posiciones?: Posicion2D[] | null;
  cara?: string | null;
  pasante: boolean;
  cantidad: number;
  tolerancia_mm?: number | null;
  rosca?: string | null;
  gdt: SimboloGDT[];
}

export interface Dimensiones {
  forma_base: FormaBase;
  largo_mm?: number | null;
  ancho_mm?: number | null;
  diametro_mm?: number | null;
  espesor_mm: number;
  longitud_mm?: number | null;
  puntos_perfil_mm?: Posicion2D[] | null;
}

export interface ToleranciaGeneral {
  valor_mm: number;
  norma?: string | null;
}

export interface Material {
  nombre: string;
  designacion?: string | null;
  dureza?: string | null;
}

export interface ExtraccionMeta {
  confianza_global: number;
  campos_baja_confianza: string[];
  notas?: string | null;
  archivo_origen?: string | null;
}

export interface Pieza {
  pieza: string;
  tipo_maquinado: TipoMaquinado;
  material: Material;
  dimensiones: Dimensiones;
  tolerancia_general: ToleranciaGeneral;
  features: Feature[];
  acabado_superficial?: string | null;
  cantidad: number;
  unidades: string;
  extraccion: ExtraccionMeta;
}

export type Etapa =
  | "plano_subido"
  | "extrayendo"
  | "esperando_confirmacion_extraccion"
  | "modelando"
  | "esperando_confirmacion_modelo"
  | "generando_trayectorias"
  | "simulando"
  | "esperando_aprobacion_final"
  | "aprobado"
  | "rechazado"
  | "error";

export interface ArchivoGenerado {
  nombre: string;
  tipo: "step" | "stl" | "gcode" | "pdf_reporte";
  ruta: string;
  generado_en: string;
  es_simulacion: boolean;
}

export interface EventoActividad {
  ts: string;
  etapa: Etapa;
  titulo: string;
  detalle?: string | null;
}

export interface ToolpathOperacion {
  feature_id?: string | null;
  estrategia: string;
  herramienta: string;
  rpm: number;
  avance_mm_min: number;
  refrigerante: string;
}

export interface ToolpathPlan {
  estrategia: string;
  herramientas: Record<string, unknown>[];
  tiempo_estimado_min?: number | null;
  operaciones: ToolpathOperacion[];
  advertencias: string[];
}

export interface SimulacionResumen {
  tiempo_estimado_min?: number | null;
  numero_operaciones: number;
  numero_herramientas: number;
  herramientas: Record<string, unknown>[];
  cambios_herramienta: number;
  advertencias: string[];
  es_simulacion: boolean;
}

export interface Proyecto {
  id: string;
  nombre: string;
  etapa: Etapa;
  creado_en: string;
  actualizado_en: string;
  archivo_plano?: string | null;
  pieza_extraida?: Pieza | null;
  pieza_confirmada: boolean;
  modelo_confirmado: boolean;
  advertencias_modelo: string[];
  features_omitidos_modelo: string[];
  postprocesador?: string | null;
  toolpath_plan?: ToolpathPlan | null;
  simulacion?: SimulacionResumen | null;
  codigo_g_resumen?: {
    archivo: string;
    operaciones_con_movimiento_real: number;
    operaciones_solo_planeadas: number;
    advertencias: string[];
  } | null;
  aprobacion_final: boolean;
  aprobado_por?: string | null;
  aprobado_en?: string | null;
  archivos: ArchivoGenerado[];
  actividad: EventoActividad[];
  mensajes: unknown[];
}

export interface MaterialKB {
  clave: string;
  nombre_display: string;
  familia: string;
  vc_recomendada_m_min: number;
  validado_por: string | null;
}

export interface PostprocesadorKB {
  clave: string;
  nombre_display: string;
  controlador: string;
}

// --- Chat timeline (frontend-only composition of pipeline events into bubbles) ---

export type ChatEntry =
  | { id: string; role: "user"; kind: "text"; ts: string; texto: string }
  | { id: string; role: "user"; kind: "upload"; ts: string; archivoNombre: string; instrucciones?: string }
  | { id: string; role: "assistant"; kind: "text"; ts: string; texto: string }
  | { id: string; role: "assistant"; kind: "extraccion"; ts: string; pieza: Pieza; confirmado: boolean }
  | {
      id: string;
      role: "assistant";
      kind: "modelo";
      ts: string;
      archivos: ArchivoGenerado[];
      advertencias: string[];
      featuresOmitidos: string[];
      confirmado: boolean;
    }
  | { id: string; role: "assistant"; kind: "trayectorias"; ts: string; plan: ToolpathPlan; postprocesador?: string | null }
  | { id: string; role: "assistant"; kind: "simulacion"; ts: string; simulacion: SimulacionResumen; resuelto: boolean }
  | {
      id: string;
      role: "assistant";
      kind: "codigo_g";
      ts: string;
      archivos: ArchivoGenerado[];
      operacionesConMovimientoReal: number;
      operacionesSoloPlaneadas: number;
      advertencias: string[];
    }
  | { id: string; role: "assistant"; kind: "error"; ts: string; texto: string };

// Reported by GET /api/health via app/integrations/windows_bridge.py.
// Non-null only when apps/windows-bridge is actually running and reachable
// on the machine hosting the orchestrator - typically the user's own
// Windows shop-floor PC, never this dev/hosted deployment.
export interface BridgeWindowsStatus {
  status: string;
  solidworks_disponible: boolean;
  mastercam_disponible: boolean;
  mastercam_instalado?: boolean;
  version_solidworks?: string | null;
  version_mastercam?: string | null;
  detalle?: string | null;
}
