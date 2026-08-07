import axios from "axios";
import type { MaterialKB, Pieza, PostprocesadorKB, Proyecto } from "./types";

const client = axios.create({ baseURL: "/api" });

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

function unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
  return promise
    .then((res) => res.data)
    .catch((err) => {
      const detail = err?.response?.data?.detail;
      throw new ApiError(typeof detail === "string" ? detail : err.message, err?.response?.status);
    });
}

export const api = {
  health: () => unwrap<{ status: string; anthropic_configurado: boolean; capa4_solidworks: string; capa4_mastercam: string }>(
    client.get("/health")
  ),

  crearProyecto: (nombre: string) => unwrap<Proyecto>(client.post("/projects", { nombre })),
  listarProyectos: () => unwrap<Proyecto[]>(client.get("/projects")),
  obtenerProyecto: (id: string) => unwrap<Proyecto>(client.get(`/projects/${id}`)),
  eliminarProyecto: (id: string) => unwrap<{ eliminado: boolean }>(client.delete(`/projects/${id}`)),

  subirPlano: (id: string, archivo: File, instrucciones?: string) => {
    const form = new FormData();
    form.append("archivo", archivo);
    if (instrucciones) form.append("instrucciones", instrucciones);
    return unwrap<Proyecto>(client.post(`/projects/${id}/plano`, form, { headers: { "Content-Type": "multipart/form-data" } }));
  },

  editarPiezaExtraida: (id: string, pieza: Pieza) => unwrap<Proyecto>(client.put(`/projects/${id}/pieza-extraida`, pieza)),
  confirmarExtraccion: (id: string) => unwrap<Proyecto>(client.post(`/projects/${id}/confirmar-extraccion`)),

  generarModelo3D: (id: string) =>
    unwrap<{ proyecto: Proyecto; propiedades_geometricas: Record<string, unknown>; advertencias: string[]; features_omitidos: string[]; archivos_generados: string[] }>(
      client.post(`/projects/${id}/generar-modelo-3d`)
    ),
  confirmarModelo: (id: string) => unwrap<Proyecto>(client.post(`/projects/${id}/confirmar-modelo`)),

  generarTrayectorias: (id: string, postprocesador?: string) =>
    unwrap<{ proyecto: Proyecto; plan: Proyecto["toolpath_plan"]; postprocesador: string }>(
      client.post(`/projects/${id}/generar-trayectorias`, { postprocesador })
    ),

  simularMaquinado: (id: string) =>
    unwrap<{ proyecto: Proyecto; simulacion: Proyecto["simulacion"] }>(client.post(`/projects/${id}/simular-maquinado`)),

  aprobarFinal: (id: string, aprobado_por: string) => unwrap<Proyecto>(client.post(`/projects/${id}/aprobar-final`, { aprobado_por })),
  rechazar: (id: string, motivo?: string) => unwrap<Proyecto>(client.post(`/projects/${id}/rechazar`, { motivo })),

  exportarCodigoG: (id: string) =>
    unwrap<{ proyecto: Proyecto; archivo: string; operaciones_con_movimiento_real: number; operaciones_solo_planeadas: number; advertencias: string[] }>(
      client.post(`/projects/${id}/exportar-codigo-g`)
    ),

  chat: (id: string, mensaje: string) =>
    unwrap<{ proyecto: Proyecto; respuesta: string; herramientas_ejecutadas: string[] }>(client.post(`/projects/${id}/chat`, { mensaje })),

  archivoUrl: (id: string, nombre: string) => `/api/projects/${id}/files/${encodeURIComponent(nombre)}`,
  planoOriginalUrl: (id: string) => `/api/projects/${id}/plano-original`,

  materiales: () => unwrap<MaterialKB[]>(client.get("/knowledge-base/materiales")),
  postprocesadores: () => unwrap<PostprocesadorKB[]>(client.get("/knowledge-base/postprocesadores")),
};
