import { motion } from "framer-motion";
import type { EventoActividad } from "../../lib/types";

function formatoHora(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts;
  }
}

export function ActividadTimeline({ eventos }: { eventos: EventoActividad[] }) {
  if (eventos.length === 0) {
    return <p className="text-xs text-[var(--color-text-faint)]">Sin actividad todavía.</p>;
  }

  const ordenados = [...eventos].reverse();

  return (
    <div className="relative space-y-4 pl-4">
      <div className="absolute bottom-1 left-[3px] top-1 w-px bg-[var(--color-border)]" />
      {ordenados.map((ev, i) => (
        <motion.div
          key={`${ev.ts}-${i}`}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.03 }}
          className="relative"
        >
          <span
            className={`absolute -left-4 top-1 h-1.5 w-1.5 rounded-full ${i === 0 ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)]"}`}
          />
          <p className="text-[11px] text-[var(--color-text-faint)]">{formatoHora(ev.ts)}</p>
          <p className="text-xs font-medium text-[var(--color-text)]">{ev.titulo}</p>
          {ev.detalle && <p className="text-[11px] text-[var(--color-text-muted)]">{ev.detalle}</p>}
        </motion.div>
      ))}
    </div>
  );
}
