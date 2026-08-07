import { motion, type HTMLMotionProps } from "framer-motion";
import type { ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";

interface ButtonProps extends Omit<HTMLMotionProps<"button">, "children"> {
  variant?: Variant;
  icon?: ReactNode;
  children: ReactNode;
  loading?: boolean;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-[var(--color-accent)] text-black font-semibold hover:bg-[var(--color-accent-2)] shadow-[0_0_0_1px_rgba(255,106,0,0.4)]",
  secondary: "bg-[var(--color-surface-3)] text-[var(--color-text)] hover:bg-[var(--color-border)] border border-[var(--color-border)]",
  ghost: "bg-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-2)]",
  danger: "bg-transparent text-[var(--color-danger)] border border-[var(--color-danger)]/40 hover:bg-[var(--color-danger)]/10",
  success: "bg-[var(--color-ok)] text-[#052e1f] hover:brightness-110",
};

export function Button({ variant = "secondary", icon, children, loading, className = "", disabled, ...props }: ButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      whileHover={{ y: -1 }}
      transition={{ type: "spring", stiffness: 400, damping: 22 }}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    >
      {loading ? (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        icon
      )}
      {children}
    </motion.button>
  );
}
