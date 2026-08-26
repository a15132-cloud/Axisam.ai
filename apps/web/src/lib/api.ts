import axios from "axios";
import type { AlmacenamientoStatus, BridgeWindowsStatus, MaterialKB, Pieza, PostprocesadorKB, Proyecto } from "./types";

// In local dev, Vite's proxy (vite.config.ts) forwards "/api" to the backend
// on :8001, so the default same-origin path works with no configuration.
// The desktop build (apps/desktop) bakes VITE_API_BASE_URL to its local
// backend process (http://127.0.0.1:8731/api) at build time - see
// apps/desktop/scripts/build-web.mjs. Self-hosting this as a plain web app
// (advanced/optional path, see README) also needs VITE_API_BASE_URL set to
// wherever that separately-deployed backend lives.
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";

if (import.meta.env.PROD && !import.meta.env.VITE_API_BASE_URL) {
  // eslint-disable-next-line no-console
  console.warn(
    "VITE_API_BASE_URL no está definida - la app intentará llamar a /api en este mismo dominio, " +
      "que no tiene backend. Define VITE_API_BASE_URL con la URL del backend desplegado."
  );
}

// El caso mas comun hoy es el backend local que arranca apps/desktop - un
// timeout generoso igual protege contra el primer arranque en una compu
// lenta (el motor de geometria tarda un momento en cargar) sin dejar un
// boton "colgado" para siempre si de verdad algo esta mal.
const client = axios.create({ baseURL, timeout: 90000 });

// subirPlano y chat hacen una o dos llamadas REALES a Claude en el backend
// (extraccion + verificacion, o el loop del agente) antes de responder -
// cada intento ahi ahora tiene su propio limite de 60s en el backend (ver
// app/vision/extractor.py y app/agent/orchestrator.py), asi que el timeout
// del lado del navegador tiene que ser mayor a eso o corta la espera justo
// cuando el backend sigue trabajando de verdad - eso es lo que se veia como
// "no carga el plano" sin ser realmente un error.
const TIMEOUT_LLAMADA_CLAUDE_MS = 180000;

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

// Browsers deliberately hide the REASON a cross-origin request failed from
// JavaScript (a security feature, not a bug) - axios/fetch both just see
// "Network Error" whether the backend is genuinely unreachable or briefly
// mid-restart (the in-flight request dropped, but a follow-up probe fired a
// moment later lands on the already-answering process again). In the
// desktop build (apps/desktop) that backend is a local child process on
// 127.0.0.1 - "genuinely unreachable" there almost always means it hasn't
// finished starting yet or was closed, not a remote outage. CORS used to be
// a third possibility here, but the backend now sends
// allow_origins=["*"] unconditionally (see app/main.py) - a real CORS block
// from THIS backend is no longer possible.
//
// The workaround: a `mode: "no-cors"` fetch to the SAME url still performs
// the real network request (DNS/TCP/TLS, or a local socket connect for
// 127.0.0.1) - it only refuses to let JS read the response body/headers. So
// it resolves if the backend answers at all, and rejects only if the
// connection itself failed right now too.
async function diagnosticarNetworkError(): Promise<string> {
  try {
    await fetch(`${baseURL}/health`, { mode: "no-cors", signal: AbortSignal.timeout(6000) });
    return (
      "El backend de Axiscam respondió en este momento, pero la petición anterior se cortó a medio camino - " +
      "probablemente se reinició justo en ese instante (por ejemplo, si Axiscam recién se abrió y el motor local " +
      "todavía estaba arrancando). No es tu internet ni tu proyecto se perdió - intenta de nuevo."
    );
  } catch {
    return (
      "No se pudo contactar al backend de Axiscam en absoluto. Si estás usando la app de escritorio, cierra " +
      "Axiscam por completo (no solo la ventana) y vuelve a abrirlo - el motor local puede haberse cerrado o " +
      "haber tardado más de lo normal en arrancar. Si el problema sigue después de reabrir, reinstala Axiscam."
    );
  }
}

function unwrap<T>(fn: () => Promise<{ data: T }>, reintentosRestantes = 1): Promise<T> {
  return fn()
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
    .catch(async (err) => {
      if (err instanceof ApiError) throw err;
      if (err?.code === "ECONNABORTED" || /timeout/i.test(err?.message ?? "")) {
        throw new ApiError(
          "El backend de Axiscam está tardando más de lo normal en responder. Intenta de nuevo en unos segundos."
        );
      }
      if (err?.message === "Network Error") {
        if (reintentosRestantes > 0) {
          // Mismo caso que el 503 de abajo: un "Network Error" que resulta
          // ser un reinicio breve del backend (ver diagnosticarNetworkError)
          // se resuelve solo en un par de segundos - reintentar antes de
          // mostrar cualquier mensaje evita que el usuario vea un error por
          // algo que ya no es cierto para cuando lo lee.
          await new Promise((resolve) => setTimeout(resolve, 3000));
          return unwrap(fn, reintentosRestantes - 1);
        }
        throw new ApiError(await diagnosticarNetworkError());
      }
      const status = err?.response?.status;
      // 502/503/504 son errores de gateway/proxy (un reinicio breve del
      // backend, o un proxy intermedio saturado momentaneamente) - el
      // cuerpo de esa respuesta suele ser una pagina de error cruda de la
      // infraestructura de por medio (texto plano/HTML, nunca algo que esta
      // app haya escrito). Ese texto crudo nunca debe llegar tal cual al
      // chat - un usuario no tecnico no puede actuar sobre eso - asi que
      // estos tres codigos siempre reciben el mismo mensaje claro y
      // accionable sin importar que traiga el cuerpo de la respuesta.
      if (status === 503 && reintentosRestantes > 0) {
        // 503 aqui siempre significa una condicion que el backend mismo ya
        // identifico como transitoria (ver _obtener_o_404 en
        // routes_projects.py). Un reintento automatico despues de una pausa
        // corta resuelve la enorme mayoria sin que el usuario vea nada, en
        // vez de un error confuso por algo que se arregla solo en un par de
        // segundos. Nunca se reintenta en 502/504 (timeouts genuinos de un
        // intento que de verdad tardo demasiado - reintentar de inmediato
        // ahi solo duplicaria la espera).
        await new Promise((resolve) => setTimeout(resolve, 3000));
        return unwrap(fn, reintentosRestantes - 1);
      }
      if (status === 502 || status === 503 || status === 504) {
        throw new ApiError(
          "El backend de Axiscam no respondió a tiempo (puede haberse reiniciado justo ahora). Espera unos segundos y vuelve a intentar - tu plano/proyecto no se perdió.",
          status
        );
      }
      const detail = err?.response?.data?.detail;
      throw new ApiError(typeof detail === "string" ? detail : err.message, status);
    });
}

export const api = {
  health: () =>
    unwrap<{
      status: string;
      anthropic_configurado: boolean;
      capa4_solidworks: string;
      bridge_windows: BridgeWindowsStatus | null;
      almacenamiento: AlmacenamientoStatus;
    }>(() => client.get("/health")),

  crearProyecto: (nombre: string) => unwrap<Proyecto>(() => client.post("/projects", { nombre })),
  listarProyectos: () => unwrap<Proyecto[]>(() => client.get("/projects")),
  obtenerProyecto: (id: string) => unwrap<Proyecto>(() => client.get(`/projects/${id}`)),
  eliminarProyecto: (id: string) => unwrap<{ eliminado: boolean }>(() => client.delete(`/projects/${id}`)),
  renombrarProyecto: (id: string, nombre: string) => unwrap<Proyecto>(() => client.put(`/projects/${id}/nombre`, { nombre })),

  // Dos peticiones, no una - ver el docstring de extraer_primera_pasada en
  // el backend (app/vision/extractor.py). subirPlano hace solo la primera
  // pasada de Claude; verificarExtraccion hace la segunda (auditoria) por
  // separado, para que ninguna peticion individual se acerque al limite de
  // proxy de la plataforma de hosting.
  subirPlano: (id: string, archivo: File, instrucciones?: string) => {
    const form = new FormData();
    form.append("archivo", archivo);
    if (instrucciones) form.append("instrucciones", instrucciones);
    return unwrap<Proyecto>(() =>
      client.post(`/projects/${id}/plano`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: TIMEOUT_LLAMADA_CLAUDE_MS,
      })
    );
  },
  verificarExtraccion: (id: string) =>
    unwrap<Proyecto>(() => client.post(`/projects/${id}/plano/verificar`, undefined, { timeout: TIMEOUT_LLAMADA_CLAUDE_MS })),

  // El usuario pidio explicitamente poder decirle a Axiscam "busca de nuevo
  // las medidas que no encontraste" en vez de solo tener que llenarlas a
  // mano - ver el docstring de buscar_campos_faltantes en el backend.
  buscarMedidasFaltantes: (id: string) =>
    unwrap<Proyecto>(() => client.post(`/projects/${id}/plano/buscar-medidas-faltantes`, undefined, { timeout: TIMEOUT_LLAMADA_CLAUDE_MS })),

  editarPiezaExtraida: (id: string, pieza: Pieza) => unwrap<Proyecto>(() => client.put(`/projects/${id}/pieza-extraida`, pieza)),
  // reintentosRestantes=2 (en vez del default de 1) en la cadena
  // confirmar-extraccion -> generar-modelo-3d especificamente: es exactamente
  // la secuencia donde se vio en vivo el "Proyecto no encontrado" reportado
  // por un usuario real, justo despues de una actualizacion del servidor
  // mientras seguia usando la app (ver _obtener_o_404 en el backend).
  confirmarExtraccion: (id: string) => unwrap<Proyecto>(() => client.post(`/projects/${id}/confirmar-extraccion`), 2),

  generarModelo3D: (id: string) =>
    unwrap<{ proyecto: Proyecto; propiedades_geometricas: Record<string, unknown>; advertencias: string[]; features_omitidos: string[]; archivos_generados: string[] }>(
      () => client.post(`/projects/${id}/generar-modelo-3d`),
      2
    ),
  // Ultimo checkpoint - Axiscam es CAD-only ahora (plano -> STEP/STL), ya
  // no planea trayectorias ni genera codigo G (ver el docstring de
  // approval.confirmar_modelo en el backend). El motor de simulacion
  // sigue existiendo, pero como una vista independiente donde el usuario
  // sube SU PROPIO archivo .nc - ver SimulacionEstandaloneView.
  confirmarModelo: (id: string) => unwrap<Proyecto>(() => client.post(`/projects/${id}/confirmar-modelo`), 2),

  activarSolidworks: (id: string) => unwrap<{ activado: boolean }>(() => client.post(`/projects/${id}/activar-solidworks`)),

  rechazar: (id: string, motivo?: string) => unwrap<Proyecto>(() => client.post(`/projects/${id}/rechazar`, { motivo })),

  chat: (id: string, mensaje: string) =>
    unwrap<{ proyecto: Proyecto; respuesta: string; herramientas_ejecutadas: string[] }>(() =>
      client.post(`/projects/${id}/chat`, { mensaje }, { timeout: TIMEOUT_LLAMADA_CLAUDE_MS })
    ),

  archivoUrl: (id: string, nombre: string) => `${baseURL}/projects/${id}/files/${encodeURIComponent(nombre)}`,
  planoOriginalUrl: (id: string) => `${baseURL}/projects/${id}/plano-original`,
  descargarTodoUrl: (id: string) => `${baseURL}/projects/${id}/descargar-todo`,

  // Fetches the plano as a blob through the same axios client/error handling
  // as everything else, instead of handing its raw URL straight to an
  // <iframe>/<img src>. A direct src= is a native browser request that
  // completely bypasses unwrap()/diagnosticarNetworkError() - if the backend
  // 502s (a brief restart) an <iframe> just renders the raw error page from
  // whatever infra sits in front of it as if it were the plano's content,
  // exactly where the user expects to see the file they uploaded. Fetching
  // it as a blob first means a failure surfaces as the same clean,
  // actionable ApiError message used everywhere else, never raw HTML in the
  // one place it's most confusing.
  obtenerPlanoOriginalBlob: async (id: string): Promise<Blob> => {
    try {
      const res = await client.get(`/projects/${id}/plano-original`, { responseType: "blob" });
      return res.data as Blob;
    } catch (err) {
      const axiosErr = err as { response?: { data?: unknown; status?: number }; message?: string; code?: string };
      const status = axiosErr.response?.status;
      if (axiosErr.code === "ECONNABORTED" || /timeout/i.test(axiosErr.message ?? "")) {
        throw new ApiError("El backend de Axiscam está tardando más de lo normal en responder. Intenta de nuevo en unos segundos.");
      }
      if (axiosErr.message === "Network Error") {
        throw new ApiError(await diagnosticarNetworkError());
      }
      if (status === 502 || status === 503 || status === 504) {
        throw new ApiError(
          "El backend de Axiscam no respondió a tiempo (puede haberse reiniciado justo ahora). Espera unos segundos y vuelve a intentar.",
          status
        );
      }
      let detalle: string | undefined;
      if (axiosErr.response?.data instanceof Blob) {
        try {
          detalle = JSON.parse(await axiosErr.response.data.text())?.detail;
        } catch {
          /* not JSON - fall through to generic message */
        }
      }
      throw new ApiError(detalle ?? "No se pudo cargar el plano original.", status);
    }
  },

  materiales: () => unwrap<MaterialKB[]>(() => client.get("/knowledge-base/materiales")),
  postprocesadores: () => unwrap<PostprocesadorKB[]>(() => client.get("/knowledge-base/postprocesadores")),

  convertirStepAStl: async (archivo: File): Promise<Blob> => {
    const form = new FormData();
    form.append("archivo", archivo);
    try {
      const res = await client.post("/convertir/step-a-stl", form, {
        headers: { "Content-Type": "multipart/form-data" },
        responseType: "blob",
      });
      return res.data as Blob;
    } catch (err) {
      const axiosErr = err as { response?: { data?: unknown; status?: number } };
      let detalle: string | undefined;
      if (axiosErr.response?.data instanceof Blob) {
        try {
          const texto = await axiosErr.response.data.text();
          detalle = JSON.parse(texto)?.detail;
        } catch {
          /* not JSON - fall through to generic message */
        }
      }
      throw new ApiError(detalle ?? "No se pudo convertir el archivo STEP a un modelo para vista previa.", axiosErr.response?.status);
    }
  },
};
