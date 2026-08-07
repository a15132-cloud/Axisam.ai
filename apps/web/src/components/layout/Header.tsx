import { motion } from "framer-motion";
import { Cpu, Wifi, WifiOff } from "lucide-react";
import { PipelineStepper } from "../pipeline/PipelineStepper";
import type { Etapa } from "../../lib/types";

interface HeaderProps {
  nombreProyecto: string;
  etapa: Etapa | null;
  anthropicConfigurado: boolean | null;
}

export function Header({ nombreProyecto, etapa, anthropicConfigurado }: HeaderProps) {
  return (
    <header className="flex flex-col gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-sm font-semibold text-[var(--color-text)]">{nombreProyecto}</h1>
          <p className="text-xs text-[var(--color-text-muted)]">Diseño CAD y manufactura CAM automatizados</p>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-xs"
        >
          <Cpu className="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
          <span className="text-[var(--color-text-muted)]">Agente:</span>
          {anthropicConfigurado === null ? (
            <span className="text-[var(--color-text-faint)]">verificando…</span>
          ) : anthropicConfigurado ? (
            <span className="flex items-center gap-1 text-[var(--color-ok)]">
              <Wifi className="h-3 w-3" /> conectado
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[var(--color-warn)]">
              <WifiOff className="h-3 w-3" /> sin ANTHROPIC_API_KEY
            </span>
          )}
        </motion.div>
      </div>

      {etapa && <PipelineStepper etapa={etapa} />}
    </header>
  );
}
