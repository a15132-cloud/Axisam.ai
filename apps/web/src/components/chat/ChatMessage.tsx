import { motion } from "framer-motion";
import { Paperclip, User } from "lucide-react";
import type { ChatEntry, Pieza } from "../../lib/types";
import { AxiscamLogo } from "../logo/AxiscamLogo";
import { PiezaCard } from "../pipeline/PiezaCard";
import { ModeloCard } from "../pipeline/ModeloCard";

function formatoHora(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export interface ChatMessageActions {
  proyectoId: string;
  onConfirmarExtraccion: () => void;
  onGuardarEdicionPieza: (pieza: Pieza) => Promise<void>;
  onBuscarMedidasFaltantes: () => void;
  onConfirmarModelo: () => void;
  onRechazar: (motivo: string) => Promise<void>;
  confirmandoExtraccion: boolean;
  confirmandoModelo: boolean;
  rechazando: boolean;
  buscandoMedidas: boolean;
  bridgeConectado: boolean;
}

export function ChatMessage({ entry, actions }: { entry: ChatEntry; actions: ChatMessageActions }) {
  const isUser = entry.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <div className="mt-0.5 shrink-0">
        {isUser ? (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-surface-3)] text-[var(--color-text-muted)]">
            <User className="h-3.5 w-3.5" />
          </div>
        ) : (
          <AxiscamLogo size={28} animated={false} />
        )}
      </div>

      <div className={`min-w-0 max-w-[85%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-[var(--color-text-muted)]">{isUser ? "Tú" : "Axiscam"}</span>
          <span className="text-[10px] text-[var(--color-text-faint)]">{formatoHora(entry.ts)}</span>
        </div>

        {entry.kind === "text" && (
          <div
            className={`whitespace-pre-line rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              isUser ? "rounded-tr-sm bg-[var(--color-accent)] text-black" : "rounded-tl-sm bg-[var(--color-surface-2)] text-[var(--color-text)]"
            }`}
          >
            {entry.texto}
          </div>
        )}

        {entry.kind === "upload" && (
          <div className="flex items-center gap-2 rounded-2xl rounded-tr-sm bg-[var(--color-accent)] px-4 py-2.5 text-sm text-black">
            <Paperclip className="h-3.5 w-3.5 shrink-0" />
            <div>
              <p>Subí un plano: {entry.archivoNombre}</p>
              {entry.instrucciones && <p className="mt-0.5 text-xs text-black/70">{entry.instrucciones}</p>}
            </div>
          </div>
        )}

        {entry.kind === "extraccion" && (
          <PiezaCard
            pieza={entry.pieza}
            readOnly={entry.confirmado}
            verificando={entry.verificando}
            confirming={actions.confirmandoExtraccion}
            onConfirmar={actions.onConfirmarExtraccion}
            onGuardarEdicion={actions.onGuardarEdicionPieza}
            onBuscarMedidasFaltantes={actions.onBuscarMedidasFaltantes}
            buscandoMedidas={actions.buscandoMedidas}
          />
        )}

        {entry.kind === "modelo" && (
          <ModeloCard
            proyectoId={actions.proyectoId}
            archivos={entry.archivos}
            advertencias={entry.advertencias}
            featuresOmitidos={entry.featuresOmitidos}
            readOnly={entry.confirmado}
            confirming={actions.confirmandoModelo}
            rechazando={actions.rechazando}
            onConfirmar={actions.onConfirmarModelo}
            onRechazar={actions.onRechazar}
            bridgeConectado={actions.bridgeConectado}
          />
        )}

        {entry.kind === "error" && (
          <div className="whitespace-pre-line rounded-2xl rounded-tl-sm border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-4 py-2.5 text-sm leading-relaxed text-[var(--color-danger)]">
            {entry.texto}
          </div>
        )}
      </div>
    </motion.div>
  );
}
