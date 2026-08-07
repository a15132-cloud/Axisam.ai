import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "ok" | "warn" | "danger";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-[var(--color-surface-3)] text-[var(--color-text-muted)]",
  accent: "bg-[var(--color-accent-soft)] text-[var(--color-accent-2)]",
  ok: "bg-[var(--color-ok)]/15 text-[var(--color-ok)]",
  warn: "bg-[var(--color-warn)]/15 text-[var(--color-warn)]",
  danger: "bg-[var(--color-danger)]/15 text-[var(--color-danger)]",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}
