import { motion } from "framer-motion";
import logoMark from "../../assets/axiscam-mark.png";

interface AxiscamLogoProps {
  size?: number;
  animated?: boolean;
  className?: string;
}

/**
 * The real Axiscam "A" mark (orange leg + white leg + floating crossbar),
 * rendered from the actual brand asset rather than a hand-drawn approximation.
 * `animated` drives the entrance scale-in and a shine sweep clipped to the
 * mark's own alpha (via `mask-image`, so it never bleeds into the transparent
 * gaps between the legs) - set it false in dense UI (sidebar rail icon) to
 * keep motion budget for the hero spot.
 */
export function AxiscamLogo({ size = 40, animated = true, className }: AxiscamLogoProps) {
  const aspect = 416 / 480;
  const height = size * aspect;

  return (
    <motion.div
      className={className}
      style={{ position: "relative", width: size, height, display: "inline-block" }}
      initial={animated ? { opacity: 0, scale: 0.85, rotate: -4 } : undefined}
      animate={animated ? { opacity: 1, scale: 1, rotate: 0 } : undefined}
      whileHover={animated ? { scale: 1.06 } : undefined}
      transition={{ type: "spring", stiffness: 260, damping: 18 }}
    >
      <img src={logoMark} alt="Axiscam" width={size} height={height} style={{ width: size, height, display: "block" }} draggable={false} />
      {animated && (
        <motion.div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: "linear-gradient(115deg, transparent 40%, rgba(255,255,255,0.65) 50%, transparent 60%)",
            backgroundSize: "300% 100%",
            backgroundRepeat: "no-repeat",
            WebkitMaskImage: `url(${logoMark})`,
            maskImage: `url(${logoMark})`,
            WebkitMaskSize: "100% 100%",
            maskSize: "100% 100%",
            WebkitMaskRepeat: "no-repeat",
            maskRepeat: "no-repeat",
          }}
          initial={{ backgroundPositionX: "-100%" }}
          animate={{ backgroundPositionX: "200%" }}
          transition={{ delay: 1.6, duration: 1.6, repeat: Infinity, repeatDelay: 3.2, ease: "easeInOut" }}
        />
      )}
    </motion.div>
  );
}
