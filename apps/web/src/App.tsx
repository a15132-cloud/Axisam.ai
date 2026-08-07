import { useEffect, useState } from "react";
import { Sidebar } from "./components/layout/Sidebar";
import { Header, type VistaMobile } from "./components/layout/Header";
import { ChatPanel } from "./components/chat/ChatPanel";
import { RightPanel } from "./components/pipeline/RightPanel";
import { ApiKeyModal } from "./components/settings/ApiKeyModal";
import { api, ApiError } from "./lib/api";
import { obtenerApiKey } from "./lib/apiKey";
import { derivarEntriesPipeline } from "./lib/deriveEntries";
import type { BridgeWindowsStatus, ChatEntry, Pieza, Proyecto } from "./lib/types";

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
  const [tieneApiKeyPropia, setTieneApiKeyPropia] = useState(() => !!obtenerApiKey());
  const [configuracionAbierta, setConfiguracionAbierta] = useState(false);
  const [cargandoInicial, setCargandoInicial] = useState(true);
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [vistaMobile, setVistaMobile] = useState<VistaMobile>("chat");

  const [creando, setCreando] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [confirmandoExtraccion, setConfirmandoExtraccion] = useState(false);
  const [confirmandoModelo, setConfirmandoModelo] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setAnthropicConfigurado(h.anthropic_configurado);
        setBackendAlcanzable(true);
        setBridgeWindows(h.bridge_windows);
      })
      .catch(() => {
        setAnthropicConfigurado(false);
        setBackendAlcanzable(false);
      });

    api
      .listarProyectos()
      .then((lista) => {
        setProyectos(lista);
        if (lista.length > 0) setProyecto(lista[0]);
      })
      .catch(() => {})
      .finally(() => setCargandoInicial(false));
  }, []);

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
    }
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

  async function subirArchivo(archivo: File, instrucciones: string) {
    if (!proyecto) return;
    setSubiendo(true);
    try {
      const actualizado = await api.subirPlano(proyecto.id, archivo, instrucciones || undefined);
      aplicarProyecto(actualizado);
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

  async function confirmarModelo() {
    if (!proyecto) return;
    setConfirmandoModelo(true);
    try {
      await api.confirmarModelo(proyecto.id);
      await api.generarTrayectorias(proyecto.id);
      const resultado = await api.simularMaquinado(proyecto.id);
      aplicarProyecto(resultado.proyecto);
    } catch (err) {
      setMensajesLibres((prev) => [...prev, errorEntry(err, "No se pudieron generar las trayectorias o la simulacion.")]);
    } finally {
      setConfirmandoModelo(false);
    }
  }

  async function aprobarFinal(aprobadoPor: string) {
    if (!proyecto) return;
    await api.aprobarFinal(proyecto.id, aprobadoPor);
    const resultado = await api.exportarCodigoG(proyecto.id);
    aplicarProyecto(resultado.proyecto);
  }

  async function rechazar(motivo: string) {
    if (!proyecto) return;
    const actualizado = await api.rechazar(proyecto.id, motivo);
    aplicarProyecto(actualizado);
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
        creando={creando}
        abierto={menuAbierto}
        onCerrar={() => setMenuAbierto(false)}
        bridgeWindows={bridgeWindows}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          nombreProyecto={proyecto?.nombre ?? "Axiscam"}
          etapa={proyecto?.etapa ?? null}
          anthropicConfigurado={anthropicConfigurado}
          tieneApiKeyPropia={tieneApiKeyPropia}
          onAbrirMenu={() => setMenuAbierto(true)}
          onAbrirConfiguracion={() => setConfiguracionAbierta(true)}
          vistaMobile={vistaMobile}
          onCambiarVistaMobile={setVistaMobile}
          mostrarSwitchMobile={!!proyecto}
        />

        <ApiKeyModal
          abierto={configuracionAbierta}
          onCerrar={() => setConfiguracionAbierta(false)}
          onGuardado={setTieneApiKeyPropia}
        />

        {backendAlcanzable === false && (
          <div className="border-b border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-4 py-3 text-center text-xs text-[var(--color-danger)]">
            No se pudo conectar con el backend — esta pantalla solo es la interfaz, y todavía no
            encuentra el servicio que hace el trabajo real. Lo más probable es que el backend
            (<code className="font-mono">apps/orchestrator</code>) no esté desplegado todavía, o que{" "}
            <code className="font-mono">VITE_API_BASE_URL</code> en Vercel no apunte a su URL
            correcta. Sigue la sección "Desplegar a producción" del README del proyecto — son 2
            pasos.
          </div>
        )}

        <div className="flex min-h-0 flex-1">
          <div
            className={`min-w-0 flex-1 flex-col border-r border-[var(--color-border)] ${
              vistaMobile === "chat" ? "flex" : "hidden"
            } lg:flex`}
          >
            {cargandoInicial ? null : !proyecto ? (
              <EmptyState onNuevoProyecto={crearProyecto} creando={creando} />
            ) : (
              <ChatPanel
                entries={entries}
                puedeChatear={!!anthropicConfigurado || tieneApiKeyPropia}
                enviando={enviando}
                subiendo={subiendo}
                onEnviarMensaje={enviarMensaje}
                onSubirArchivo={subirArchivo}
                actions={{
                  proyectoId: proyecto.id,
                  onConfirmarExtraccion: confirmarExtraccion,
                  onGuardarEdicionPieza: guardarEdicionPieza,
                  onConfirmarModelo: confirmarModelo,
                  onAprobarFinal: aprobarFinal,
                  onRechazar: rechazar,
                  confirmandoExtraccion,
                  confirmandoModelo,
                }}
              />
            )}
          </div>

          <div className={`w-full shrink-0 overflow-hidden lg:w-[380px] ${vistaMobile === "detalles" ? "block" : "hidden"} lg:block`}>
            {proyecto && <RightPanel proyecto={proyecto} />}
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onNuevoProyecto, creando }: { onNuevoProyecto: () => void; creando: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <p className="text-sm text-[var(--color-text-muted)]">No tienes proyectos todavía.</p>
      <button
        onClick={onNuevoProyecto}
        disabled={creando}
        className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black hover:bg-[var(--color-accent-2)] disabled:opacity-60"
      >
        Crear tu primer proyecto
      </button>
    </div>
  );
}
