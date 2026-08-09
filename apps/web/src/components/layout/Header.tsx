import { Menu } from "lucide-react";
import { PipelineStepper } from "../pipeline/PipelineStepper";
import type { Etapa } from "../../lib/types";

export type VistaMobile = "chat" | "detalles";

interface HeaderProps {
  nombreProyecto: string;
  etapa: Etapa | null;
  onAbrirMenu: () => void;
  vistaMobile: VistaMobile;
  onCambiarVistaMobile: (vista: VistaMobile) => void;
  mostrarSwitchMobile: boolean;
}

export function Header({
  nombreProyecto,
  etapa,
  onAbrirMenu,
  vistaMobile,
  onCambiarVistaMobile,
  mostrarSwitchMobile,
}: HeaderProps) {
  return (
    <header className="flex flex-col border-b border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="hazard-stripe h-1 w-full opacity-80" />
      <div className="flex flex-col gap-3 px-3 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <button
              onClick={onAbrirMenu}
              className="shrink-0 rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)] lg:hidden"
              aria-label="Abrir menú de proyectos"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <h1 className="font-display truncate text-base font-semibold tracking-wide text-[var(--color-text)]">{nombreProyecto}</h1>
              <p className="hidden text-xs text-[var(--color-text-muted)] sm:block">Diseño CAD y manufactura CAM automatizados</p>
            </div>
          </div>
        </div>

        {etapa && <PipelineStepper etapa={etapa} />}

        {mostrarSwitchMobile && (
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-[var(--color-surface-2)] p-1 lg:hidden">
            {(["chat", "detalles"] as const).map((v) => (
              <button
                key={v}
                onClick={() => onCambiarVistaMobile(v)}
                className={`rounded-md py-2 text-sm font-medium capitalize transition-colors ${
                  vistaMobile === v ? "bg-[var(--color-accent)] text-black" : "text-[var(--color-text-muted)]"
                }`}
              >
                {v === "chat" ? "Chat" : "Detalles"}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
