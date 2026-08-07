import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, EyeOff, KeyRound, Trash2, X } from "lucide-react";
import { Button } from "../common/Button";
import { borrarApiKey, guardarApiKey, obtenerApiKey } from "../../lib/apiKey";

interface ApiKeyModalProps {
  abierto: boolean;
  onCerrar: () => void;
  onGuardado: (tieneKey: boolean) => void;
}

export function ApiKeyModal({ abierto, onCerrar, onGuardado }: ApiKeyModalProps) {
  const [valor, setValor] = useState(() => obtenerApiKey() ?? "");
  const [mostrar, setMostrar] = useState(false);

  if (!abierto) return null;

  function guardar() {
    const limpio = valor.trim();
    if (!limpio) return;
    guardarApiKey(limpio);
    onGuardado(true);
    onCerrar();
  }

  function borrar() {
    borrarApiKey();
    setValor("");
    onGuardado(false);
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
        onClick={onCerrar}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 8 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-2xl"
        >
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-[var(--color-accent)]" />
              <h3 className="font-display text-sm font-semibold tracking-wide text-[var(--color-text)]">
                Tu API key de Anthropic
              </h3>
            </div>
            <button onClick={onCerrar} className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" aria-label="Cerrar">
              <X className="h-4 w-4" />
            </button>
          </div>

          <p className="mb-3 text-xs leading-relaxed text-[var(--color-text-muted)]">
            Axiscam usa Claude (Anthropic) como su motor de IA — sin una API key no hay chat ni
            lectura de planos real. Esta key es <strong className="text-[var(--color-text)]">tuya</strong>:
            se guarda solo en este navegador y se manda directo al backend en cada mensaje, nunca se
            almacena en ningún servidor de Axiscam. Consíguela en{" "}
            <a
              href="https://console.anthropic.com/settings/keys"
              target="_blank"
              rel="noreferrer"
              className="text-[var(--color-accent-2)] underline"
            >
              console.anthropic.com/settings/keys
            </a>{" "}
            (2 minutos, pago solo por lo que uses).
          </p>

          <div className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
            <input
              type={mostrar ? "text" : "password"}
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              placeholder="sk-ant-..."
              className="min-w-0 flex-1 bg-transparent font-mono text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] focus:outline-none"
              autoFocus
            />
            <button
              onClick={() => setMostrar((v) => !v)}
              className="shrink-0 text-[var(--color-text-faint)] hover:text-[var(--color-text)]"
              aria-label={mostrar ? "Ocultar" : "Mostrar"}
              type="button"
            >
              {mostrar ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>

          <div className="mt-4 flex items-center justify-between gap-2">
            <Button variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={borrar} type="button">
              Quitar
            </Button>
            <Button variant="primary" onClick={guardar} disabled={!valor.trim()} type="button">
              Guardar
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
