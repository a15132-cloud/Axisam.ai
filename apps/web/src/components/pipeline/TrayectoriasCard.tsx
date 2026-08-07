import type { ToolpathPlan } from "../../lib/types";
import { WarningBanner } from "../common/WarningBanner";
import { Badge } from "../common/Badge";

export function TrayectoriasCard({ plan, postprocesador }: { plan: ToolpathPlan; postprocesador?: string | null }) {
  return (
    <div className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-[var(--color-text)]">Plan de trayectorias</h4>
        <div className="flex items-center gap-2">
          {postprocesador && <Badge tone="accent">{postprocesador}</Badge>}
          {plan.tiempo_estimado_min != null && <Badge tone="neutral">~{plan.tiempo_estimado_min} min estimados</Badge>}
        </div>
      </div>

      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-[var(--color-text-faint)]">
              <th className="pb-2 pr-3 font-medium">Feature</th>
              <th className="pb-2 pr-3 font-medium">Estrategia</th>
              <th className="pb-2 pr-3 font-medium">Herramienta</th>
              <th className="pb-2 pr-3 font-medium">RPM</th>
              <th className="pb-2 font-medium">Avance</th>
            </tr>
          </thead>
          <tbody>
            {plan.operaciones.map((op, i) => (
              <tr key={i} className="border-t border-[var(--color-border-soft)] text-[var(--color-text-muted)]">
                <td className="py-1.5 pr-3 text-[var(--color-text)]">{op.feature_id || `#${i + 1}`}</td>
                <td className="py-1.5 pr-3">{op.estrategia}</td>
                <td className="py-1.5 pr-3">{op.herramienta}</td>
                <td className="py-1.5 pr-3">{op.rpm.toLocaleString()}</td>
                <td className="py-1.5">{op.avance_mm_min.toLocaleString()} mm/min</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {plan.advertencias.length > 0 && (
        <div className="mt-3">
          <WarningBanner items={plan.advertencias} />
        </div>
      )}
    </div>
  );
}
