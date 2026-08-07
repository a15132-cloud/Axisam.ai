import { useState } from "react";
import { ShieldCheck, XCircle } from "lucide-react";
import type { SimulacionResumen } from "../../lib/types";
import { Badge } from "../common/Badge";
import { Button } from "../common/Button";
import { WarningBanner } from "../common/WarningBanner";

interface SimulacionCardProps {
  simulacion: SimulacionResumen;
  readOnly?: boolean;
  onAprobar?: (aprobadoPor: string) => Promise<void>;
  onRechazar?: (motivo: string) => Promise<void>;
}

export function SimulacionCard({ simulacion, readOnly, onAprobar, onRechazar }: SimulacionCardProps) {
  const [nombre, setNombre] = useState("");
  const [aprobando, setAprobando] = useState(false);
  const [rechazando, setRechazando] = useState(false);

  return (
    <div className="w-full rounded-lg border border-[var(--color-warn)]/40 bg-[var(--color-surface-2)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-[var(--color-text)]">Simulación de maquinado (estimada)</h4>
        <Badge tone="warn">requiere aprobación humana</Badge>
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs">
        <Stat label="Tiempo estimado" value={simulacion.tiempo_estimado_min != null ? `~${simulacion.tiempo_estimado_min} min` : "N/A"} />
        <Stat label="Operaciones" value={String(simulacion.numero_operaciones)} />
        <Stat label="Cambios de herramienta" value={String(simulacion.cambios_herramienta)} />
      </div>

      <div className="mt-3 space-y-1">
        {simulacion.herramientas.map((h, i) => (
          <div key={i} className="flex items-center justify-between rounded-md bg-[var(--color-surface-3)] px-2.5 py-1.5 text-xs">
            <span className="text-[var(--color-text)]">{String(h.descripcion)}</span>
            <span className="text-[var(--color-text-muted)]">
              {String(h.rpm)} RPM · {String(h.avance_mm_min)} mm/min · {String(h.usos)}x
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <WarningBanner items={simulacion.advertencias} />
      </div>

      {!readOnly && (
        <div className="mt-4 space-y-2 border-t border-[var(--color-border-soft)] pt-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Tu nombre o usuario (queda registrado como responsable de la aprobación)
          </label>
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="p.ej. juan.perez@taller.com"
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="success"
              icon={<ShieldCheck className="h-3.5 w-3.5" />}
              disabled={!nombre.trim()}
              loading={aprobando}
              onClick={async () => {
                if (!onAprobar) return;
                setAprobando(true);
                try {
                  await onAprobar(nombre.trim());
                } finally {
                  setAprobando(false);
                }
              }}
            >
              Aprobar y generar código G
            </Button>
            <Button
              variant="danger"
              icon={<XCircle className="h-3.5 w-3.5" />}
              loading={rechazando}
              onClick={async () => {
                if (!onRechazar) return;
                setRechazando(true);
                try {
                  await onRechazar("Rechazado desde revisión de simulación");
                } finally {
                  setRechazando(false);
                }
              }}
            >
              Rechazar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--color-surface-3)] px-3 py-2">
      <p className="text-[var(--color-text-faint)]">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-[var(--color-text)]">{value}</p>
    </div>
  );
}
