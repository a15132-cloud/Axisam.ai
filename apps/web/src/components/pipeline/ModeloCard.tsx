import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Download, ExternalLink, HelpCircle } from "lucide-react";
import { Button } from "../common/Button";
import { WarningBanner } from "../common/WarningBanner";
import { StlViewer } from "../viewer/StlViewer";
import { ErrorBoundary } from "../system/ErrorBoundary";
import type { ArchivoGenerado } from "../../lib/types";
import { api, ApiError } from "../../lib/api";

interface ModeloCardProps {
  proyectoId: string;
  archivos: ArchivoGenerado[];
  advertencias: string[];
  featuresOmitidos: string[];
  readOnly?: boolean;
  onConfirmar?: () => void;
  confirming?: boolean;
  bridgeConectado?: boolean;
  mastercamInstalado?: boolean;
}

export function ModeloCard({
  proyectoId,
  archivos,
  advertencias,
  featuresOmitidos,
  readOnly,
  onConfirmar,
  confirming,
  bridgeConectado,
  mastercamInstalado,
}: ModeloCardProps) {
  const stl = archivos.find((a) => a.tipo === "stl");
  const step = archivos.find((a) => a.tipo === "step");

  const esSimulacion = stl?.es_simulacion ?? step?.es_simulacion ?? true;

  const [activandoSw, setActivandoSw] = useState(false);
  const [abriendoMc, setAbriendoMc] = useState(false);
  const [errorBridge, setErrorBridge] = useState<string | null>(null);
  const [omisionesRevisadas, setOmisionesRevisadas] = useState(false);

  const hayOmisiones = featuresOmitidos.length > 0;
  const puedeConfirmar = !hayOmisiones || omisionesRevisadas;

  async function verEnSolidworks() {
    setErrorBridge(null);
    setActivandoSw(true);
    try {
      await api.activarSolidworks(proyectoId);
    } catch (err) {
      setErrorBridge(err instanceof ApiError ? err.message : "No se pudo activar SolidWorks.");
    } finally {
      setActivandoSw(false);
    }
  }

  async function abrirEnMastercam() {
    setErrorBridge(null);
    setAbriendoMc(true);
    try {
      await api.abrirMastercam(proyectoId);
    } catch (err) {
      setErrorBridge(err instanceof ApiError ? err.message : "No se pudo abrir Mastercam.");
    } finally {
      setAbriendoMc(false);
    }
  }

  return (
    <div className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-[var(--color-text)]">Modelo 3D generado</h4>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            esSimulacion
              ? "bg-[var(--color-surface-3)] text-[var(--color-text-faint)]"
              : "bg-[var(--color-ok)]/15 text-[var(--color-ok)]"
          }`}
          title={esSimulacion ? "Generado con el motor de geometría simulado (cadquery)" : "Generado con SolidWorks real via apps/windows-bridge"}
        >
          {esSimulacion ? "Motor simulado" : "SolidWorks real"}
        </span>
      </div>

      {stl && (
        <ErrorBoundary compact>
          <StlViewer url={api.archivoUrl(proyectoId, stl.nombre)} />
        </ErrorBoundary>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {step && (
          <a href={api.archivoUrl(proyectoId, step.nombre)} download>
            <Button variant="secondary" icon={<Download className="h-3.5 w-3.5" />}>
              Descargar STEP (SolidWorks / Mastercam)
            </Button>
          </a>
        )}
        {stl && (
          <a href={api.archivoUrl(proyectoId, stl.nombre)} download>
            <Button variant="ghost" icon={<Download className="h-3.5 w-3.5" />}>
              Descargar STL
            </Button>
          </a>
        )}
        {!esSimulacion && bridgeConectado && (
          <Button variant="secondary" icon={<ExternalLink className="h-3.5 w-3.5" />} onClick={verEnSolidworks} loading={activandoSw}>
            Ver en SolidWorks
          </Button>
        )}
        {step && bridgeConectado && mastercamInstalado && (
          <Button
            variant="ghost"
            icon={<ExternalLink className="h-3.5 w-3.5" />}
            onClick={abrirEnMastercam}
            loading={abriendoMc}
            title="Abre Mastercam y trata de cargar el STEP - Mastercam no genera nada automatico todavia, esto solo te ahorra importarlo a mano"
          >
            Abrir en Mastercam
          </Button>
        )}
      </div>

      {errorBridge && <p className="mt-2 text-xs text-[var(--color-danger)]">{errorBridge}</p>}

      {hayOmisiones && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-3 overflow-hidden rounded-lg border border-[var(--color-warn)]/30 bg-[var(--color-warn)]/10 px-3 py-2.5"
        >
          <div className="flex items-start gap-2">
            <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-warn)]" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-[var(--color-warn)]">
                Estas features NO quedaron en el modelo - antes de continuar, revisa si alguna es importante:
              </p>
              <ul className="mt-1.5 space-y-1 text-xs text-[var(--color-text-muted)]">
                {featuresOmitidos.map((item, i) => (
                  <li key={i} className="leading-relaxed">
                    <span className="text-[var(--color-warn)]">·</span> {item}
                  </li>
                ))}
              </ul>
              {!readOnly && (
                <label className="mt-2.5 flex cursor-pointer items-start gap-2 text-xs text-[var(--color-text)]">
                  <input
                    type="checkbox"
                    checked={omisionesRevisadas}
                    onChange={(e) => setOmisionesRevisadas(e.target.checked)}
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[var(--color-accent)]"
                  />
                  Ya revisé esta lista - confirmo que quiero continuar así, aunque falten esas features del modelo.
                </label>
              )}
            </div>
          </div>
        </motion.div>
      )}
      {advertencias.length > 0 && (
        <div className="mt-3">
          <WarningBanner title="Advertencias del motor de geometría" items={advertencias} />
        </div>
      )}

      {!readOnly && (
        <div className="mt-4">
          <Button
            variant="primary"
            icon={<Check className="h-3.5 w-3.5" />}
            onClick={onConfirmar}
            loading={confirming}
            disabled={!puedeConfirmar}
            title={puedeConfirmar ? undefined : "Marca la casilla de arriba antes de confirmar el modelo"}
          >
            Confirmar modelo y continuar a trayectorias
          </Button>
        </div>
      )}
    </div>
  );
}
