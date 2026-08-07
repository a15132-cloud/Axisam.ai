import { AnimatePresence, motion } from "framer-motion";
import { Plus, MessageSquare, Trash2, X } from "lucide-react";
import { AxiscamLogo } from "../logo/AxiscamLogo";
import type { Proyecto } from "../../lib/types";

const ETAPA_DOT: Record<Proyecto["etapa"], string> = {
  plano_subido: "bg-[var(--color-text-faint)]",
  extrayendo: "bg-[var(--color-accent)]",
  esperando_confirmacion_extraccion: "bg-[var(--color-warn)]",
  modelando: "bg-[var(--color-accent)]",
  esperando_confirmacion_modelo: "bg-[var(--color-warn)]",
  generando_trayectorias: "bg-[var(--color-accent)]",
  simulando: "bg-[var(--color-accent)]",
  esperando_aprobacion_final: "bg-[var(--color-warn)]",
  aprobado: "bg-[var(--color-ok)]",
  rechazado: "bg-[var(--color-danger)]",
  error: "bg-[var(--color-danger)]",
};

interface SidebarProps {
  proyectos: Proyecto[];
  proyectoActualId: string | null;
  onSeleccionar: (id: string) => void;
  onNuevoProyecto: () => void;
  onEliminar: (id: string) => void;
  creando: boolean;
  abierto: boolean;
  onCerrar: () => void;
}

export function Sidebar({ proyectos, proyectoActualId, onSeleccionar, onNuevoProyecto, onEliminar, creando, abierto, onCerrar }: SidebarProps) {
  return (
    <>
      {/* Backdrop - mobile only, closes the drawer on tap outside */}
      <AnimatePresence>
        {abierto && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCerrar}
            className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          />
        )}
      </AnimatePresence>

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-full w-72 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-transform duration-300 ease-out lg:static lg:z-auto lg:w-64 lg:translate-x-0 ${
          abierto ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between gap-2.5 px-4 py-4">
          <div className="flex items-center gap-2.5">
            <AxiscamLogo size={32} />
            <span className="font-display text-xl font-semibold tracking-wide text-gradient-brand">AXISCAM</span>
          </div>
          <button onClick={onCerrar} className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] lg:hidden" aria-label="Cerrar menú">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-3">
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={onNuevoProyecto}
            disabled={creando}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-3 py-3 text-sm font-semibold text-black transition-colors hover:bg-[var(--color-accent-2)] disabled:opacity-60 lg:py-2.5"
          >
            <Plus className="h-4 w-4" /> Nuevo proyecto
          </motion.button>
        </div>

        <div className="mt-4 flex items-center gap-2 px-4 text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-faint)]">
          <MessageSquare className="h-3.5 w-3.5" /> Proyectos recientes
        </div>

        <div className="mt-2 flex-1 space-y-0.5 overflow-y-auto scrollbar-thin px-2 pb-4">
          {proyectos.length === 0 && <p className="px-2 py-4 text-xs text-[var(--color-text-faint)]">Aún no hay proyectos.</p>}
          {proyectos.map((p) => (
            <div key={p.id} className="group relative">
              <button
                onClick={() => onSeleccionar(p.id)}
                className={`flex w-full items-center gap-2 rounded-lg px-3 py-3 text-left text-sm transition-colors lg:py-2.5 ${
                  p.id === proyectoActualId ? "bg-[var(--color-surface-3)] text-[var(--color-text)]" : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                }`}
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${ETAPA_DOT[p.etapa]}`} />
                <span className="min-w-0 flex-1 truncate pr-6">{p.nombre}</span>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEliminar(p.id);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-[var(--color-text-faint)] opacity-100 hover:text-[var(--color-danger)] lg:opacity-0 lg:group-hover:opacity-100"
                title="Eliminar proyecto"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
