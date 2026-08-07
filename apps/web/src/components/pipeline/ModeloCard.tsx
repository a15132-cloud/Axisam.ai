import { Check, Download } from "lucide-react";
import { Button } from "../common/Button";
import { WarningBanner } from "../common/WarningBanner";
import { StlViewer } from "../viewer/StlViewer";
import type { ArchivoGenerado } from "../../lib/types";
import { api } from "../../lib/api";

interface ModeloCardProps {
  proyectoId: string;
  archivos: ArchivoGenerado[];
  advertencias: string[];
  featuresOmitidos: string[];
  readOnly?: boolean;
  onConfirmar?: () => void;
  confirming?: boolean;
}

export function ModeloCard({ proyectoId, archivos, advertencias, featuresOmitidos, readOnly, onConfirmar, confirming }: ModeloCardProps) {
  const stl = archivos.find((a) => a.tipo === "stl");
  const step = archivos.find((a) => a.tipo === "step");

  return (
    <div className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <h4 className="mb-3 text-sm font-semibold text-[var(--color-text)]">Modelo 3D generado</h4>

      {stl && <StlViewer url={api.archivoUrl(proyectoId, stl.nombre)} />}

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
      </div>

      {featuresOmitidos.length > 0 && (
        <div className="mt-3">
          <WarningBanner title="Features no modelados automáticamente" items={featuresOmitidos} />
        </div>
      )}
      {advertencias.length > 0 && (
        <div className="mt-3">
          <WarningBanner title="Advertencias del motor de geometría" items={advertencias} />
        </div>
      )}

      {!readOnly && (
        <div className="mt-4">
          <Button variant="primary" icon={<Check className="h-3.5 w-3.5" />} onClick={onConfirmar} loading={confirming}>
            Confirmar modelo y continuar a trayectorias
          </Button>
        </div>
      )}
    </div>
  );
}
