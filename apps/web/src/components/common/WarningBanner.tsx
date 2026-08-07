import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";

export function WarningBanner({ items, title = "Advertencias" }: { items: string[]; title?: string }) {
  if (items.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      className="overflow-hidden rounded-lg border border-[var(--color-warn)]/30 bg-[var(--color-warn)]/10 px-3 py-2.5"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-warn)]" />
        <div className="min-w-0">
          <p className="text-xs font-semibold text-[var(--color-warn)]">{title}</p>
          <ul className="mt-1 space-y-1 text-xs text-[var(--color-text-muted)]">
            {items.map((item, i) => (
              <li key={i} className="leading-relaxed">
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </motion.div>
  );
}
