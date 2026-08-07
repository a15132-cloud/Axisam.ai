import { motion } from "framer-motion";
import { AlertOctagon, Download, PackageCheck, PartyPopper } from "lucide-react";
import { api } from "../../lib/api";
import { Button } from "../common/Button";
import { WarningBanner } from "../common/WarningBanner";
import type { ArchivoGenerado } from "../../lib/types";

export function CodigoGCard({
  proyectoId,
  archivos,
  operacionesConMovimientoReal,
  operacionesSoloPlaneadas,
  advertencias,
}: {
  proyectoId: string;
  archivos: ArchivoGenerado[];
  operacionesConMovimientoReal: number;
  operacionesSoloPlaneadas: number;
  advertencias: string[];
}) {
  const gcode = [...archivos].reverse().find((a) => a.tipo === "gcode");

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      className="w-full rounded-lg border border-[var(--color-ok)]/40 bg-[var(--color-surface-2)] p-4"
    >
      <div className="mb-3 flex items-center gap-2">
        <PartyPopper className="h-4 w-4 text-[var(--color-ok)]" />
        <h4 className="text-sm font-semibold text-[var(--color-text)]">Código G exportado</h4>
      </div>

      <div className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2.5 text-xs text-[var(--color-danger)]">
        <div className="flex items-start gap-2">
          <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Simulación pendiente de verificar con Mastercam real. {operacionesConMovimientoReal} operación(es) tienen
            trayectoria de corte real calculada (taladrado, cajeras, contornos); {operacionesSoloPlaneadas} quedaron
            solo planeadas (geometría no soportada aún - requieren Mastercam real). Sin chequeo de colisiones entre
            features simultáneos. Un maquinista debe revisar el archivo completo antes de cargarlo en la máquina CNC.
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <a href={api.descargarTodoUrl(proyectoId)} download>
          <Button variant="primary" icon={<PackageCheck className="h-3.5 w-3.5" />}>
            Descargar todo (.zip)
          </Button>
        </a>
        {gcode && (
          <a href={api.archivoUrl(proyectoId, gcode.nombre)} download>
            <Button variant="secondary" icon={<Download className="h-3.5 w-3.5" />}>
              Solo {gcode.nombre}
            </Button>
          </a>
        )}
      </div>

      {advertencias.length > 0 && (
        <div className="mt-3">
          <WarningBanner items={advertencias} />
        </div>
      )}
    </motion.div>
  );
}
