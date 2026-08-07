import { motion } from "framer-motion";
import { Check, CircleDot, FileCode2, FileText, ShieldCheck, Box, Route } from "lucide-react";
import type { Etapa } from "../../lib/types";

const STEPS: { key: string; label: string; icon: typeof FileText; etapas: Etapa[] }[] = [
  { key: "plano", label: "Plano", icon: FileText, etapas: ["plano_subido", "extrayendo", "esperando_confirmacion_extraccion"] },
  { key: "modelo", label: "Modelo 3D", icon: Box, etapas: ["modelando", "esperando_confirmacion_modelo"] },
  { key: "trayectorias", label: "Trayectorias", icon: Route, etapas: ["generando_trayectorias", "simulando"] },
  { key: "codigo_g", label: "Código G", icon: FileCode2, etapas: ["esperando_aprobacion_final"] },
  { key: "aprobacion", label: "Aprobación", icon: ShieldCheck, etapas: ["aprobado"] },
];

function stepStatus(index: number, etapa: Etapa): "done" | "active" | "pending" {
  const activeIndex = STEPS.findIndex((s) => s.etapas.includes(etapa));
  if (etapa === "rechazado" || etapa === "error") return index === 0 ? "active" : "pending";
  if (activeIndex === -1) return "pending";
  if (index < activeIndex) return "done";
  if (index === activeIndex) return "active";
  return "pending";
}

export function PipelineStepper({ etapa }: { etapa: Etapa }) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto scrollbar-thin px-1 py-1">
      {STEPS.map((step, i) => {
        const status = stepStatus(i, etapa);
        const Icon = step.icon;
        return (
          <div key={step.key} className="flex shrink-0 items-center">
            <div className="flex items-center gap-2">
              <motion.div
                animate={
                  status === "active"
                    ? { boxShadow: ["0 0 0 0 rgba(255,106,0,0.5)", "0 0 0 8px rgba(255,106,0,0)"] }
                    : {}
                }
                transition={status === "active" ? { duration: 1.6, repeat: Infinity, ease: "easeOut" } : {}}
                className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold transition-colors ${
                  status === "done"
                    ? "border-[var(--color-ok)] bg-[var(--color-ok)]/15 text-[var(--color-ok)]"
                    : status === "active"
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)] text-black"
                      : "border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-faint)]"
                }`}
              >
                {status === "done" ? <Check className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
              </motion.div>
              <span
                className={`whitespace-nowrap text-xs font-medium ${
                  status === "pending" ? "text-[var(--color-text-faint)]" : "text-[var(--color-text)]"
                }`}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className="mx-3 h-px w-8 shrink-0" style={{ background: status === "done" ? "var(--color-ok)" : "var(--color-border)" }} />
            )}
          </div>
        );
      })}
      {(etapa === "rechazado" || etapa === "error") && (
        <span className="ml-3 flex items-center gap-1 text-xs font-medium text-[var(--color-danger)]">
          <CircleDot className="h-3.5 w-3.5" /> {etapa === "rechazado" ? "Rechazado" : "Error"}
        </span>
      )}
    </div>
  );
}
