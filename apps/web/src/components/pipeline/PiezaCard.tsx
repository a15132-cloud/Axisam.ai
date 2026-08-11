import { useState } from "react";
import { motion } from "framer-motion";
import { Check, HelpCircle, Pencil, X } from "lucide-react";
import type { Pieza } from "../../lib/types";
import { Badge } from "../common/Badge";
import { Button } from "../common/Button";

interface PiezaCardProps {
  pieza: Pieza;
  readOnly?: boolean;
  onConfirmar?: () => void;
  onGuardarEdicion?: (pieza: Pieza) => Promise<void>;
  confirming?: boolean;
}

function ConfidenceBadge({ confianza }: { confianza: number }) {
  const tone = confianza >= 0.85 ? "ok" : confianza >= 0.6 ? "warn" : "danger";
  return <Badge tone={tone}>confianza {(confianza * 100).toFixed(0)}%</Badge>;
}

export function PiezaCard({ pieza, readOnly, onConfirmar, onGuardarEdicion, confirming }: PiezaCardProps) {
  const [editando, setEditando] = useState(false);
  const [borrador, setBorrador] = useState(() => JSON.stringify(pieza, null, 2));
  const [errorJson, setErrorJson] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [preguntasRevisadas, setPreguntasRevisadas] = useState(false);

  const d = pieza.dimensiones;
  const preguntasPendientes = pieza.extraccion.campos_baja_confianza;
  const tienePreguntas = preguntasPendientes.length > 0;
  const puedeConfirmar = !tienePreguntas || preguntasRevisadas;

  async function guardar() {
    setErrorJson(null);
    let parsed: Pieza;
    try {
      parsed = JSON.parse(borrador);
    } catch {
      setErrorJson("El JSON no es valido - revisa comas/llaves.");
      return;
    }
    if (!onGuardarEdicion) return;
    setGuardando(true);
    try {
      await onGuardarEdicion(parsed);
      setEditando(false);
    } catch (err) {
      setErrorJson(err instanceof Error ? err.message : "No se pudo guardar la edicion.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-[var(--color-text)]">Resumen extraído del plano</h4>
        <ConfidenceBadge confianza={pieza.extraccion.confianza_global} />
      </div>

      {editando ? (
        <div className="space-y-2">
          <textarea
            value={borrador}
            onChange={(e) => setBorrador(e.target.value)}
            spellCheck={false}
            className="h-72 w-full resize-y rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 font-mono text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
          />
          {errorJson && <p className="text-xs text-[var(--color-danger)]">{errorJson}</p>}
          <div className="flex gap-2">
            <Button variant="primary" icon={<Check className="h-3.5 w-3.5" />} onClick={guardar} loading={guardando}>
              Guardar cambios
            </Button>
            <Button variant="ghost" icon={<X className="h-3.5 w-3.5" />} onClick={() => setEditando(false)}>
              Cancelar
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
            <Field label="Pieza" value={pieza.pieza} />
            <Field label="Material" value={pieza.material.nombre} />
            <Field label="Cantidad" value={String(pieza.cantidad)} />
            <Field label="Tolerancia general" value={`±${pieza.tolerancia_general.valor_mm} mm`} />
            {d.forma_base === "rectangular" ? (
              <>
                <Field label="Largo" value={`${d.largo_mm} mm`} />
                <Field label="Ancho" value={`${d.ancho_mm} mm`} />
              </>
            ) : (
              <Field label="Diámetro" value={`${d.diametro_mm} mm`} />
            )}
            <Field label="Espesor" value={`${d.espesor_mm} mm`} />
            <Field label="Acabado" value={pieza.acabado_superficial || "N/A"} />
          </div>

          {pieza.features.length > 0 && (
            <div className="mt-4 overflow-x-auto scrollbar-thin">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-[var(--color-text-faint)]">
                    <th className="pb-2 pr-3 font-medium">#</th>
                    <th className="pb-2 pr-3 font-medium">Tipo</th>
                    <th className="pb-2 pr-3 font-medium">Diámetro/Medida</th>
                    <th className="pb-2 pr-3 font-medium">Posición</th>
                    <th className="pb-2 font-medium">Tolerancia</th>
                  </tr>
                </thead>
                <tbody>
                  {pieza.features.map((f, i) => (
                    <tr key={f.id || i} className="border-t border-[var(--color-border-soft)] text-[var(--color-text-muted)]">
                      <td className="py-1.5 pr-3">{i + 1}</td>
                      <td className="py-1.5 pr-3 capitalize text-[var(--color-text)]">{f.tipo.replace(/_/g, " ")}</td>
                      <td className="py-1.5 pr-3">
                        {f.diametro_mm
                          ? `Ø${f.diametro_mm} mm`
                          : f.radio_mm
                            ? `R${f.radio_mm} mm`
                            : f.ancho_mm && f.largo_mm
                              ? `${f.ancho_mm}×${f.largo_mm} mm`
                              : f.ancho_mm
                                ? `${f.ancho_mm} mm${f.cara ? ` (${f.cara})` : ""}`
                                : "—"}
                      </td>
                      <td className="py-1.5 pr-3">
                        {f.posiciones?.length
                          ? `${f.posiciones.length} posiciones`
                          : f.posicion
                            ? `(${f.posicion.x}, ${f.posicion.y})`
                            : "—"}
                      </td>
                      <td className="py-1.5">{f.tolerancia_mm ? `±${f.tolerancia_mm} mm` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tienePreguntas && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              className="mt-3 overflow-hidden rounded-lg border border-[var(--color-warn)]/30 bg-[var(--color-warn)]/10 px-3 py-2.5"
            >
              <div className="flex items-start gap-2">
                <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-warn)]" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-[var(--color-warn)]">
                    Axiscam no encontró esto en el plano - antes de continuar, dime qué hacer:
                  </p>
                  <ul className="mt-1.5 space-y-1 text-xs text-[var(--color-text-muted)]">
                    {preguntasPendientes.map((item, i) => (
                      <li key={i} className="leading-relaxed">
                        <span className="text-[var(--color-warn)]">·</span> {item}
                      </li>
                    ))}
                  </ul>
                  {pieza.extraccion.notas && (
                    <p className="mt-2 whitespace-pre-line rounded-md bg-[var(--color-bg)]/40 px-2 py-1.5 text-xs italic leading-relaxed text-[var(--color-text-muted)]">
                      {pieza.extraccion.notas}
                    </p>
                  )}
                  {!readOnly && (
                    <label className="mt-2.5 flex cursor-pointer items-start gap-2 text-xs text-[var(--color-text)]">
                      <input
                        type="checkbox"
                        checked={preguntasRevisadas}
                        onChange={(e) => setPreguntasRevisadas(e.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[var(--color-accent)]"
                      />
                      Ya revisé estos puntos - confirmo que quiero continuar así, o los voy a corregir con "Editar información".
                    </label>
                  )}
                </div>
              </div>
            </motion.div>
          )}
          {!tienePreguntas && pieza.extraccion.notas && (
            <p className="mt-2 whitespace-pre-line text-xs italic leading-relaxed text-[var(--color-text-faint)]">
              Nota del extractor: {pieza.extraccion.notas}
            </p>
          )}

          {!readOnly && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }} className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="primary"
                icon={<Check className="h-3.5 w-3.5" />}
                onClick={onConfirmar}
                loading={confirming}
                disabled={!puedeConfirmar}
                title={puedeConfirmar ? undefined : "Marca la casilla de arriba, o edita la información, antes de confirmar"}
              >
                Confirmar y continuar
              </Button>
              <Button variant="secondary" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditando(true)}>
                Editar información
              </Button>
            </motion.div>
          )}
        </>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[var(--color-text-faint)]">{label}</p>
      <p className="font-mono mt-0.5 break-words font-medium text-[var(--color-text)]">{value}</p>
    </div>
  );
}
