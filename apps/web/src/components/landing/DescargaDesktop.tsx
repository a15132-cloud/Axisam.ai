import { motion } from "framer-motion";
import { Cpu, ExternalLink, FileBox, Lock, Ruler, Wrench } from "lucide-react";
import { AxiscamLogo } from "../logo/AxiscamLogo";

// Se muestra cuando este mismo build de apps/web se abre en un navegador
// normal (Vercel) en vez de dentro de la app de escritorio (apps/desktop) -
// ver src/lib/isElectron.ts. Axiscam ya no es "una pagina web que usas" -
// es una app que se descarga; esta pantalla es solo el punto de entrada
// para conseguirla, no el producto en si.
const URL_RELEASES = "https://github.com/a15132-cloud/Axisam.ai/releases";

const CARACTERISTICAS = [
  {
    icon: FileBox,
    titulo: "De un plano a un STEP real",
    texto:
      "Lee PDF, imagen o boceto a mano y genera un modelo 3D real con un kernel de geometría real (OpenCascade) - STEP/STL que abres directo en SolidWorks, no una aproximación.",
  },
  {
    icon: Lock,
    titulo: "Tus planos no salen de tu compu",
    texto:
      "El modelado, el guardado de proyectos y la simulación de trayectorias corren 100% local. Lo único que sale a internet es la lectura del plano y el chat con Claude - nunca dependes de que un servidor remoto esté despierto.",
  },
  {
    icon: Ruler,
    titulo: "Calcula lo que el plano no acota directo",
    texto:
      "Cadenas de cotas, simetría, trigonometría - antes de dejar una medida en blanco, Axiscam intenta calcularla con los números reales del plano, y explica la cuenta para que la confirmes en segundos.",
  },
  {
    icon: Wrench,
    titulo: "SolidWorks/Mastercam reales cuando los tienes",
    texto:
      "Si corres el conector opcional en tu PC con licencia, Axiscam usa tu instalación real en vez del motor simulado - automáticamente, sin configurar nada.",
  },
];

export function DescargaDesktop() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      <div className="hazard-stripe h-1 w-full opacity-80" />

      <main className="mx-auto flex max-w-4xl flex-col items-center px-6 py-16 text-center sm:py-24">
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <AxiscamLogo size={72} />
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="font-display mt-6 text-3xl font-semibold tracking-wide sm:text-5xl"
        >
          Axiscam
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-4 max-w-2xl text-base text-[var(--color-text-muted)] sm:text-lg"
        >
          El agente de IA que lee el plano de una pieza y genera su modelo 3D real - como una app de
          escritorio normal, sin depender de ningún servidor.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mt-8 flex flex-col items-center gap-3 sm:flex-row"
        >
          <a
            href={URL_RELEASES}
            className="rounded-lg bg-[var(--color-accent)] px-6 py-3 text-sm font-semibold text-[var(--color-bg)] transition-transform hover:scale-[1.03]"
          >
            Descargar Axiscam para Windows
          </a>
          <a
            href={URL_RELEASES}
            className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-5 py-3 text-sm text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
          >
            <ExternalLink className="h-4 w-4" />
            Ver todas las versiones
          </a>
        </motion.div>
        <p className="mt-3 text-xs text-[var(--color-text-faint)]">
          Windows por ahora - Mac y Linux, próximamente.
        </p>

        <div className="mt-20 grid w-full gap-6 text-left sm:grid-cols-2">
          {CARACTERISTICAS.map(({ icon: Icon, titulo, texto }, i) => (
            <motion.div
              key={titulo}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.25 + i * 0.06 }}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
            >
              <Icon className="h-5 w-5 text-[var(--color-accent)]" />
              <h3 className="font-display mt-3 text-sm font-semibold tracking-wide text-[var(--color-text)]">
                {titulo}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--color-text-muted)]">{texto}</p>
            </motion.div>
          ))}
        </div>

        <div className="mt-16 flex items-center gap-2 text-xs text-[var(--color-text-faint)]">
          <Cpu className="h-3.5 w-3.5" />
          <span>El motor de geometría corre en tu computadora - no en la nuestra.</span>
        </div>
      </main>
    </div>
  );
}
