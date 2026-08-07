import { motion } from "framer-motion";
import { useId } from "react";

interface AxiscamLogoProps {
  size?: number;
  animated?: boolean;
  className?: string;
}

/**
 * Geometric "A" mark: orange leg + orange-to-white leg meeting at the
 * apex, with a small floating crossbar - black/orange/white, industrial
 * rather than a generic SaaS blue gradient. `animated` drives the
 * entrance draw-in and the slow shine sweep; set it false in dense UI
 * (sidebar rail icon) to keep motion budget for the hero spot.
 */
export function AxiscamLogo({ size = 40, animated = true, className }: AxiscamLogoProps) {
  const uid = useId().replace(/:/g, "");
  const gradId = `axc-grad-${uid}`;
  const shineId = `axc-shine-${uid}`;
  const glowId = `axc-glow-${uid}`;

  const legVariants = {
    hidden: { pathLength: 0, opacity: 0 },
    visible: (i: number) => ({
      pathLength: 1,
      opacity: 1,
      transition: {
        pathLength: { duration: 0.9, delay: i * 0.12, ease: [0.22, 1, 0.36, 1] as const },
        opacity: { duration: 0.3, delay: i * 0.12 },
      },
    }),
  };

  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      initial={animated ? "hiddenGroup" : undefined}
      animate={animated ? "visibleGroup" : undefined}
      whileHover={animated ? { scale: 1.06 } : undefined}
      transition={{ type: "spring", stiffness: 260, damping: 18 }}
    >
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#d97757" />
          <stop offset="55%" stopColor="#e8a988" />
          <stop offset="100%" stopColor="#ffffff" />
        </linearGradient>
        <linearGradient id={shineId} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="white" stopOpacity="0" />
          <stop offset="50%" stopColor="white" stopOpacity="0.55" />
          <stop offset="100%" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g filter={animated ? `url(#${glowId})` : undefined}>
        <motion.path
          d="M44,6 L50,6 L18,94 L10,94 Z"
          fill="#a85a3e"
          custom={0}
          variants={animated ? legVariants : undefined}
          initial={animated ? "hidden" : undefined}
          animate={animated ? "visible" : undefined}
        />
        <motion.path
          d="M50,6 L56,6 L90,94 L82,94 Z"
          fill={`url(#${gradId})`}
          custom={1}
          variants={animated ? legVariants : undefined}
          initial={animated ? "hidden" : undefined}
          animate={animated ? "visible" : undefined}
        />
        <motion.path
          d="M42,64 L58,64 L54,72 L46,72 Z"
          fill="#d97757"
          initial={animated ? { opacity: 0, y: -4 } : undefined}
          animate={animated ? { opacity: 1, y: 0 } : undefined}
          transition={{ delay: 0.55, duration: 0.4, ease: "easeOut" }}
        />
      </g>

      {animated && (
        <motion.rect
          x={-40}
          y={0}
          width={40}
          height={100}
          fill={`url(#${shineId})`}
          initial={{ x: -40 }}
          animate={{ x: 100 }}
          transition={{ delay: 1.6, duration: 1.6, repeat: Infinity, repeatDelay: 3.2, ease: "easeInOut" }}
        />
      )}
    </motion.svg>
  );
}
