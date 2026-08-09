import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Box, ChevronDown, ChevronUp, X } from "lucide-react";
import { StlViewer } from "../viewer/StlViewer";
import { ErrorBoundary } from "../system/ErrorBoundary";
import { api } from "../../lib/api";
import type { Proyecto } from "../../lib/types";

/**
 * A small preview of the piece's STEP/STL that appears in the bottom-right
 * corner of the chat itself the moment Axiscam generates a 3D model - the
 * user shouldn't have to switch to "detalles" (mobile) or scroll the right
 * panel (desktop) to see the piece the agent just built for them. Only
 * mounted here, not in RightPanel, so there is exactly one place this
 * state (visto/colapsado) lives - the RightPanel's own "Vista 3D previa"
 * card stays as the persistent, scrollable copy for later reference.
 */
export function ModeloFlotante3D({ proyecto }: { proyecto: Proyecto }) {
  const [cerrado, setCerrado] = useState(false);
  const [colapsado, setColapsado] = useState(false);
  const stl = proyecto.archivos.find((a) => a.tipo === "stl");

  if (!stl || cerrado) return null;

  return (
    <div className="pointer-events-none absolute bottom-4 right-4 z-20 hidden sm:block">
      <AnimatePresence>
        <motion.div
          key={stl.nombre}
          initial={{ opacity: 0, y: 16, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.96 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-auto w-64 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl shadow-black/40"
        >
          <div className="flex items-center justify-between border-b border-[var(--color-border-soft)] px-3 py-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text)]">
              <Box className="h-3.5 w-3.5 text-[var(--color-accent)]" />
              Modelo 3D generado
            </div>
            <div className="flex items-center gap-0.5">
              <button
                onClick={() => setColapsado((c) => !c)}
                className="rounded p-1 text-[var(--color-text-faint)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
                title={colapsado ? "Expandir" : "Colapsar"}
              >
                {colapsado ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => setCerrado(true)}
                className="rounded p-1 text-[var(--color-text-faint)] hover:bg-[var(--color-danger)]/10 hover:text-[var(--color-danger)]"
                title="Cerrar"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          {!colapsado && (
            <ErrorBoundary compact>
              <StlViewer url={api.archivoUrl(proyecto.id, stl.nombre)} heightClassName="h-48" compact />
            </ErrorBoundary>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
