import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Paperclip, Send, X, FileText } from "lucide-react";
import type { ChatEntry } from "../../lib/types";
import { ChatMessage, type ChatMessageActions } from "./ChatMessage";
import { AxiscamLogo } from "../logo/AxiscamLogo";

interface ChatPanelProps {
  entries: ChatEntry[];
  actions: ChatMessageActions;
  onEnviarMensaje: (texto: string) => Promise<void>;
  onSubirArchivo: (archivo: File, instrucciones: string) => Promise<void>;
  enviando: boolean;
  subiendo: boolean;
  puedeChatear: boolean;
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-[var(--color-surface-2)] px-4 py-3">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-[var(--color-text-faint)]"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }}
        />
      ))}
    </div>
  );
}

export function ChatPanel({ entries, actions, onEnviarMensaje, onSubirArchivo, enviando, subiendo, puedeChatear }: ChatPanelProps) {
  const [texto, setTexto] = useState("");
  const [archivoPendiente, setArchivoPendiente] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [entries.length, enviando, subiendo]);

  async function enviar() {
    const t = texto.trim();
    if (!t && !archivoPendiente) return;
    const archivo = archivoPendiente;
    setTexto("");
    setArchivoPendiente(null);
    if (archivo) {
      await onSubirArchivo(archivo, t);
    } else {
      await onEnviarMensaje(t);
    }
  }

  function manejarArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    // Solo se selecciona aqui - no se sube nada todavia. La subida real
    // pasa cuando el usuario le pica a enviar, igual que un mensaje de texto.
    const archivo = e.target.files?.[0];
    e.target.value = "";
    if (!archivo) return;
    setArchivoPendiente(archivo);
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto scrollbar-thin px-4 py-4 sm:px-6">
        {entries.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex h-full flex-col items-center justify-center gap-3 py-16 text-center">
            <AxiscamLogo size={56} />
            <div>
              <p className="text-sm font-medium text-[var(--color-text)]">Sube el plano de tu pieza para comenzar</p>
              <p className="mt-1 max-w-sm text-xs text-[var(--color-text-muted)]">
                PDF, imagen (PNG/JPG) o DXF. Puedes agregar instrucciones como "aluminio 6061, tolerancia estándar".
              </p>
            </div>
          </motion.div>
        )}

        <AnimatePresence initial={false}>
          {entries.map((entry) => (
            <ChatMessage key={entry.id} entry={entry} actions={actions} />
          ))}
        </AnimatePresence>

        {(enviando || subiendo) && (
          <div className="flex gap-3">
            <AxiscamLogo size={28} animated={false} />
            <TypingIndicator />
          </div>
        )}
      </div>

      <div className="border-t border-[var(--color-border)] p-3 sm:p-4">
        {!puedeChatear && (
          <p className="mb-2 text-[11px] text-[var(--color-text-faint)]">
            El chat con IA no está disponible en este momento - las acciones del pipeline
            (confirmar, generar, aprobar) siguen funcionando desde las tarjetas de arriba.
          </p>
        )}
        {archivoPendiente && (
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
            <FileText className="h-4 w-4 shrink-0 text-[var(--color-accent)]" />
            <span className="min-w-0 flex-1 truncate text-xs text-[var(--color-text)]">{archivoPendiente.name}</span>
            <button
              type="button"
              onClick={() => setArchivoPendiente(null)}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--color-text-faint)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
              title="Quitar archivo"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="flex items-end gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
            title="Adjuntar archivo"
            disabled={subiendo}
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <input ref={fileInputRef} type="file" className="hidden" onChange={manejarArchivo} />
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                enviar();
              }
            }}
            rows={1}
            placeholder={archivoPendiente ? "Agrega instrucciones (opcional) y pica enviar..." : "Escribe un mensaje o adjunta un archivo..."}
            className="max-h-32 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm text-[var(--color-text)] outline-none placeholder:text-[var(--color-text-faint)]"
          />
          <motion.button
            type="button"
            whileTap={{ scale: 0.9 }}
            onClick={enviar}
            disabled={(!texto.trim() && !archivoPendiente) || enviando || subiendo}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent)] text-black disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </motion.button>
        </div>
        <p className="mt-2 text-center text-[10px] text-[var(--color-text-faint)]">
          Axiscam puede cometer errores. Verifica siempre las medidas, el modelo y el código G antes de fabricar.
        </p>
      </div>
    </div>
  );
}
