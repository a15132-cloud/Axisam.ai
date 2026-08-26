import { useEffect, useState } from "react";
import { Sidebar, BotonNuevoProyecto } from "./components/layout/Sidebar";
import { Header, type VistaMobile } from "./components/layout/Header";
import { ChatPanel } from "./components/chat/ChatPanel";
import { RightPanel } from "./components/pipeline/RightPanel";
import { AxiscamLogo } from "./components/logo/AxiscamLogo";
import { ModeloFlotante3D } from "./components/pipeline/ModeloFlotante3D";
import { SimulacionEstandaloneView } from "./components/simulation/SimulacionEstandaloneView";
import { api, ApiError } from "./lib/api";
import { esElectron } from "./lib/isElectron";
import { derivarEntriesPipeline } from "./lib/deriveEntries";
import type { AlmacenamientoStatus, BridgeWindowsStatus, ChatEntry, Pieza, Proyecto } from "./lib/types";

type Seccion = "proyectos" | "simulacion";

function uid() {
  return Math.random().toString(36).slice(2);
}

function textoEntry(role: "user" | "assistant", texto: string): ChatEntry {
  return { id: uid(), role, kind: "text", ts: new Date().toISOString(), texto };
}

function errorEntry(err: unknown, fallback: string): ChatEntry {
  return { id: uid(), role: "assistant", kind: "error", ts: new Date().toISOString(), texto: err instanceof ApiError ? err.message : fallback };
}

export default function App() {
  const [proyectos, setProyectos] = useState<Proyecto[]>([]);
  const [proyecto, setProyecto] = useState<Proyecto | null>(null);
  const [mensajesLibres, setMensajesLibres] = useState<ChatEntry[]>([]);
  const [anthropicConfigurado, setAnthropicConfigurado] = useState<boolean | null>(null);
  const [backendAlcanzable, setBackendAlcanzable] = useState<boolean | null>(null);
  const [bridgeWindows, setBridgeWindows] = useState<BridgeWindowsStatus | null>(null);
  const [almacenamiento, setAlmacenamiento] = useState<AlmacenamientoStatus | null>(null);
  const [cargandoInicial, setCargandoInicial] = useState(true);
  const [errorListaProyectos, setErrorListaProyectos] = useState(false);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [vistaMobile, setVistaMobile] = useState<VistaMobile>("chat");
  const [seccion, setSeccion] = useState<Seccion>("proyectos");

  const [creando, setCreando] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [confirmandoExtraccion, setConfirmandoExtraccion] = useState(false);
  const [confirmandoModelo, setConfirmandoModelo] = useState(false);
  const [rechazando, setRechazando] = useState(false);
  const [buscandoMedidas, setBuscandoMedidas] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setAnthropicConfigurado(h.anthropic_configurado);
        setBackendAlcanzable(true);
        setBridgeWindows(h.bridge_windows);
        setAlmacenamiento(h.almacenamiento);
      })
      .catch(() => {
        setAnthropicConfigurado(false);
        setBackendAlcanzable(false);
      });

    cargarProyectos();
  }, []);

  function cargarProyectos() {
    setErrorListaProyectos(false);
    return api
      .listarProyectos()
      .then((lista) => {
        setProyectos(lista);
        if (lista.length > 0) setProyecto((actual) => actual ?? lista[0]);
      })
      .catch(() => setErrorListaProyectos(true))
      .finally(() => setCargandoInicial(false));
  }

  function actualizarListaProyecto(actualizado: Proyecto) {
    setProyectos((prev) => {
      const existe = prev.some((p) => p.id === actualizado.id);
      return existe ? prev.map((p) => (p.id === actualizado.id ? actualizado : p)) : [actualizado, ...prev];
    });
  }

  function aplicarProyecto(actualizado: Proyecto) {
    setProyecto(actualizado);
    actualizarListaProyecto(actualizado);
  }

  async function crearProyecto() {
    setCreando(true);
    try {
      const nuevo = await api.crearProyecto(`Pieza ${new Date().toLocaleDateString("es-MX")} ${new Date().toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })}`);
      setProyectos((prev) => [nuevo, ...prev]);
      setProyecto(nuevo);
      setMensajesLibres([]);
      setVistaMobile("chat");
      setSeccion("proyectos");
      setMenuAbierto(false);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "No se pudo crear el proyecto.");
    } finally {
      setCreando(false);
    }
  }

  function seleccionarProyecto(id: string) {
    const p = proyectos.find((pr) => pr.id === id);
    if (p) {
      setProyecto(p);
      setMensajesLibres([]);
      setVistaMobile("chat");
      setSeccion("proyectos");
    }
    setMenuAbierto(false);
  }

  function cambiarSeccion(s: Seccion) {
    setSeccion(s);
    setMenuAbierto(false);
  }

  async function eliminarProyecto(id: string) {
    if (!window.confirm("¿Eliminar este proyecto y todos sus archivos generados? Esta acción no se puede deshacer.")) return;
    await api.eliminarProyecto(id);
    setProyectos((prev) => prev.filter((p) => p.id !== id));
    if (proyecto?.id === id) {
      setProyecto(null);
      setMensajesLibres([]);
    }
  }

  async function renombrarProyecto(id: string, nombre: string) {
    try {
      const actualizado = await api.renombrarProyecto(id, nombre);
      actualizarListaProyecto(actualizado);
      if (proyecto?.id === id) setProyecto(actualizado);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "No se pudo renombrar el proyecto.");
    }
  }

  async function subirArchivo(archivo: File, instrucciones: string) {
    if (!proyecto) return;
    const proyectoId = proyecto.id;
    setSubiendo(true);
    try {
      // Dos peticiones seguidas, no una - ver api.ts. La primera (primera
      // pasada de Claude) y la segunda (verificacion/auditoria) se muestran
      // como un solo "trabajando" continuo para el usuario; si la segunda
      // falla, el backend ya cae de vuelta a la primera pasada en vez de
      // perder la extraccion completa (ver verificar_plano en el backend).
      const primeraPasada = await api.subirPlano(proyectoId, archivo, instrucciones || undefined);
      aplicarProyecto(primeraPasada);
      const verificado = await api.verificarExtraccion(proyectoId);
      aplicarProyecto(verificado);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudo extraer la informacion del plano.")]);
    } finally {
      setSubiendo(false);
    }
  }

  async function confirmarExtraccion() {
    if (!proyecto) return;
    setConfirmandoExtraccion(true);
    try {
      await api.confirmarExtraccion(proyecto.id);
      const resultado = await api.generarModelo3D(proyecto.id);
      aplicarProyecto(resultado.proyecto);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudo generar el modelo 3D.")]);
    } finally {
      setConfirmandoExtraccion(false);
    }
  }

  async function guardarEdicionPieza(pieza: Pieza) {
    if (!proyecto) return;
    const actualizado = await api.editarPiezaExtraida(proyecto.id, pieza);
    aplicarProyecto(actualizado);
  }

  async function buscarMedidasFaltantes() {
    if (!proyecto) return;
    setBuscandoMedidas(true);
    try {
      const actualizado = await api.buscarMedidasFaltantes(proyecto.id);
      aplicarProyecto(actualizado);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudo volver a revisar el plano.")]);
    } finally {
      setBuscandoMedidas(false);
    }
  }

  async function confirmarModelo() {
    if (!proyecto) return;
    setConfirmandoModelo(true);
    try {
      const actualizado = await api.confirmarModelo(proyecto.id);
      aplicarProyecto(actualizado);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudo confirmar el modelo.")]);
    } finally {
      setConfirmandoModelo(false);
    }
  }

  async function rechazar(motivo: string) {
    if (!proyecto) return;
    setRechazando(true);
    try {
      const actualizado = await api.rechazar(proyecto.id, motivo);
      aplicarProyecto(actualizado);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudo rechazar el proyecto.")]);
    } finally {
      setRechazando(false);
    }
  }

  async function enviarMensaje(texto: string) {
    if (!proyecto) return;
    setMensajesLibres((prev) => [...prev, textoEntry("user", texto)]);
    setEnviando(true);
    try {
      const resultado = await api.chat(proyecto.id, texto);
      aplicarProyecto(resultado.proyecto);
      setMensajesLibres((prev) => [...prev, textoEntry("assistant", resultado.respuesta || "(sin respuesta de texto)")]);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudo contactar al agente.")]);
    } finally {
      setEnviando(false);
    }
  }

  const entries: ChatEntry[] = proyecto ? [...derivarEntriesPipeline(proyecto), ...mensajesLibres] : [];

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-[var(--color-bg)]">
      <Sidebar
        proyectos={proyectos}
        proyectoActualId={proyecto?.id ?? null}
        onSeleccionar={seleccionarProyecto}
        onNuevoProyecto={crearProyecto}
        onEliminar={eliminarProyecto}
        onRenombrar={renombrarProyecto}
        creando={creando}
        abierto={menuAbierto}
        onCerrar={() => setMenuAbierto(false)}
        bridgeWindows={bridgeWindows}
        seccion={seccion}
        onCambiarSeccion={cambiarSeccion}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          nombreProyecto={seccion === "simulacion" ? "Simulación" : (proyecto?.nombre ?? "Axiscam")}
          etapa={seccion === "proyectos" ? (proyecto?.etapa ?? null) : null}
          onAbrirMenu={() => setMenuAbierto(true)}
          vistaMobile={vistaMobile}
          onCambiarVistaMobile={setVistaMobile}
          mostrarSwitchMobile={seccion === "proyectos" && !!proyecto}
        />

        {backendAlcanzable === false && (
          <div className="border-b border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-4 py-3 text-center text-xs text-[var(--color-danger)]">
            {esElectron() ? (
              // Dentro de Electron, main.js ya espera a que el backend local
              // responda antes de abrir esta ventana - llegar a este estado
              // solo pasa si el proceso local murió DESPUES de abrir (p.ej.
              // el antivirus lo cerró a medio uso). El texto de "revisa el
              // despliegue en Vercel/Render" de abajo seria una instruccion
              // sin sentido aqui - un usuario de escritorio nunca desplegó
              // nada.
              <>No se pudo conectar con el motor local de Axiscam. Cierra Axiscam por completo y vuelve a
              abrirlo - si el problema sigue, revisa que tu antivirus no lo esté bloqueando.</>
            ) : (
              <>
                No se pudo conectar con el backend — esta pantalla solo es la interfaz, y todavía no
                encuentra el servicio que hace el trabajo real. Lo más probable es que el backend
                (<code className="font-mono">apps/orchestrator</code>) no esté desplegado todavía, o que{" "}
                <code className="font-mono">VITE_API_BASE_URL</code> en Vercel no apunte a su URL
                correcta. Sigue la sección "Modo avanzado" del README del proyecto — son 2 pasos.
              </>
            )}
          </div>
        )}

        {almacenamiento?.advertencia && (
          // El backend (app/storage/files.py::diagnostico_almacenamiento) ya
          // decide si "no es un punto de montaje separado" es realmente un
          // problema - eso SOLO importa en un deploy que espera un disco
          // persistente real (Render con AXISCAM_STORAGE_PERSISTENTE=true).
          // En la app de escritorio o en dev local, `advertencia` viene null
          // a propósito (una carpeta normal en el disco del usuario nunca es
          // un punto de montaje separado, y eso es completamente normal ahí)
          // - mostrar este banner solo cuando el backend mismo dice que sí
          // aplica evita el bug real que hubo: la app de escritorio mostraba
          // "confirma tu plan en Render" a alguien que nunca tocó Render.
          <div className="border-b border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-4 py-3 text-center text-xs text-[var(--color-danger)]">
            ⚠ {almacenamiento.advertencia}
          </div>
        )}

        {seccion === "simulacion" ? (
          <div className="min-h-0 flex-1">
            <SimulacionEstandaloneView />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1">
            <div
              className={`relative min-w-0 flex-1 flex-col border-r border-[var(--color-border)] ${
                vistaMobile === "chat" ? "flex" : "hidden"
              } lg:flex`}
            >
              {cargandoInicial ? null : !proyecto ? (
                <EmptyState
                  onNuevoProyecto={crearProyecto}
                  creando={creando}
                  errorAlCargar={errorListaProyectos}
                  onReintentar={cargarProyectos}
                />
              ) : (
                <>
                  <ChatPanel
                    entries={entries}
                    puedeChatear={!!anthropicConfigurado}
                    enviando={enviando}
                    subiendo={subiendo}
                    generandoModelo={confirmandoExtraccion}
                    confirmandoModelo={confirmandoModelo}
                    onEnviarMensaje={enviarMensaje}
                    onSubirArchivo={subirArchivo}
                    actions={{
                      proyectoId: proyecto.id,
                      onConfirmarExtraccion: confirmarExtraccion,
                      onGuardarEdicionPieza: guardarEdicionPieza,
                      onBuscarMedidasFaltantes: buscarMedidasFaltantes,
                      onConfirmarModelo: confirmarModelo,
                      onRechazar: rechazar,
                      confirmandoExtraccion,
                      confirmandoModelo,
                      rechazando,
                      buscandoMedidas,
                      bridgeConectado: !!bridgeWindows,
                    }}
                  />
                  <ModeloFlotante3D proyecto={proyecto} />
                </>
              )}
            </div>

            <div className={`w-full shrink-0 overflow-hidden lg:w-[380px] ${vistaMobile === "detalles" ? "block" : "hidden"} lg:block`}>
              {proyecto && <RightPanel proyecto={proyecto} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({
  onNuevoProyecto,
  creando,
  errorAlCargar,
  onReintentar,
}: {
  onNuevoProyecto: () => void;
  creando: boolean;
  errorAlCargar: boolean;
  onReintentar: () => void;
}) {
  if (errorAlCargar) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm text-[var(--color-danger)]">
          No se pudo cargar tu lista de proyectos. Puede que ya tengas proyectos guardados - no se
          perdieron, solo no se pudieron traer ahora.
        </p>
        <button
          onClick={onReintentar}
          className="rounded-lg bg-[var(--color-surface-3)] px-4 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <AxiscamLogo size={64} />
      <p className="text-sm text-[var(--color-text-muted)]">No tienes proyectos todavía.</p>
      <div className="w-full max-w-xs">
        <BotonNuevoProyecto creando={creando} onClick={onNuevoProyecto} />
      </div>
    </div>
  );
}
