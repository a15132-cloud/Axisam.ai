import axios from "axios";
import type { BridgeWindowsStatus, MaterialKB, Pieza, PostprocesadorKB, Proyecto } from "./types";

// In local dev, Vite's proxy (vite.config.ts) forwards "/api" to the backend
// on :8001, so the default same-origin path works with no configuration. In
// production (e.g. Vercel, which only serves this static frontend - it can't
// run the Python backend) there is no backend at this origin, so the real
// backend URL must be provided at build time via VITE_API_BASE_URL.
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";

if (import.meta.env.PROD && !import.meta.env.VITE_API_BASE_URL) {
  // eslint-disable-next-line no-console
  console.warn(
    "VITE_API_BASE_URL no está definida - la app intentará llamar a /api en este mismo dominio, " +
      "que no tiene backend. Define VITE_API_BASE_URL con la URL del backend desplegado."
  );
}

const client = axios.create({ baseURL });

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

function unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
  return promise
    .then((res) => {
      // A misconfigured VITE_API_BASE_URL (or a rewrite that catches
      // unmatched paths - see vercel.json) can make an "/api/..." request
      // land on a static host that answers 200 with index.html instead of
      // a real 404. Axios then hands back the raw HTML string as `data`
      // because it isn't valid JSON. Treating that string as a Proyecto
      // silently corrupts app state instead of failing - which showed up
      // as "Cannot read properties of undefined (reading 'find')" deep in
      // a component with no idea anything was wrong upstream. Fail loudly
      // here instead, at the one place that actually knows the shape is off.
      if (typeof res.data === "string") {
        throw new ApiError(
          "El servidor respondió con HTML en vez de datos - revisa que VITE_API_BASE_URL apunte al backend real."
        );
      }
      return res.data;
    })
    .catch((err) => {
      if (err instanceof ApiError) throw err;
      const detail = err?.response?.data?.detail;
      throw new ApiError(typeof detail === "string" ? detail : err.message, err?.response?.status);
    });
}

export const api = {
  health: () =>
    unwrap<{
      status: string;
      anthropic_configurado: boolean;
      capa4_solidworks: string;
      capa4_mastercam: string;
      bridge_windows: BridgeWindowsStatus | null;
    }>(client.get("/health")),

  crearProyecto: (nombre: string) => unwrap<Proyecto>(client.post("/projects", { nombre })),
  listarProyectos: () => unwrap<Proyecto[]>(client.get("/projects")),
  obtenerProyecto: (id: string) => unwrap<Proyecto>(client.get(`/projects/${id}`)),
  eliminarProyecto: (id: string) => unwrap<{ eliminado: boolean }>(client.delete(`/projects/${id}`)),
  renombrarProyecto: (id: string, nombre: string) => unwrap<Proyecto>(client.put(`/projects/${id}/nombre`, { nombre })),

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

  archivoUrl: (id: string, nombre: string) => `${baseURL}/projects/${id}/files/${encodeURIComponent(nombre)}`,
  planoOriginalUrl: (id: string) => `${baseURL}/projects/${id}/plano-original`,
  descargarTodoUrl: (id: string) => `${baseURL}/projects/${id}/descargar-todo`,

  materiales: () => unwrap<MaterialKB[]>(client.get("/knowledge-base/materiales")),
  postprocesadores: () => unwrap<PostprocesadorKB[]>(client.get("/knowledge-base/postprocesadores")),
};
