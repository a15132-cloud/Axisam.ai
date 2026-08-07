import { motion } from "framer-motion";
import { Cpu, KeyRound, Menu, Wifi, WifiOff } from "lucide-react";
import { PipelineStepper } from "../pipeline/PipelineStepper";
import type { Etapa } from "../../lib/types";

export type VistaMobile = "chat" | "detalles";

interface HeaderProps {
  nombreProyecto: string;
  etapa: Etapa | null;
  anthropicConfigurado: boolean | null;
  tieneApiKeyPropia: boolean;
  onAbrirMenu: () => void;
  onAbrirConfiguracion: () => void;
  vistaMobile: VistaMobile;
  onCambiarVistaMobile: (vista: VistaMobile) => void;
  mostrarSwitchMobile: boolean;
}

export function Header({
  nombreProyecto,
  etapa,
  anthropicConfigurado,
  tieneApiKeyPropia,
  onAbrirMenu,
  onAbrirConfiguracion,
  vistaMobile,
  onCambiarVistaMobile,
  mostrarSwitchMobile,
}: HeaderProps) {
  const agenteListo = !!anthropicConfigurado || tieneApiKeyPropia;
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

          <div className="flex shrink-0 items-center gap-2">
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              onClick={onAbrirConfiguracion}
              className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-xs hover:bg-[var(--color-surface-3)]"
              title="Configurar tu API key de Anthropic"
            >
              <Cpu className="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
              <span className="hidden text-[var(--color-text-muted)] sm:inline">Agente:</span>
              {anthropicConfigurado === null ? (
                <span className="text-[var(--color-text-faint)]">verificando…</span>
              ) : agenteListo ? (
                <span className="flex items-center gap-1 text-[var(--color-ok)]">
                  <Wifi className="h-3 w-3" /> conectado
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[var(--color-warn)]">
                  <WifiOff className="h-3 w-3" /> sin API key
                </span>
              )}
            </motion.button>
            <button
              onClick={onAbrirConfiguracion}
              className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
              title="Configuración"
              aria-label="Configuración"
            >
              <KeyRound className="h-4 w-4" />
            </button>
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
