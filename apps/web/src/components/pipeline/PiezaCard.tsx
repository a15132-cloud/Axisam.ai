import { useState } from "react";
import { motion } from "framer-motion";
import { Braces, Check, HelpCircle, Pencil, Plus, RefreshCw, Trash2, X } from "lucide-react";
import type { Feature, Pieza } from "../../lib/types";
import { Badge } from "../common/Badge";
import { Button } from "../common/Button";

interface PiezaCardProps {
  pieza: Pieza;
  readOnly?: boolean;
  onConfirmar?: () => void;
  onGuardarEdicion?: (pieza: Pieza) => Promise<void>;
  onBuscarMedidasFaltantes?: () => void;
  confirming?: boolean;
  buscandoMedidas?: boolean;
}

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]";

function clonar<T>(valor: T): T {
  return JSON.parse(JSON.stringify(valor));
}

// "" en un <input type=number> vacio debe volverse null (campo sin medida),
// nunca 0 - un 0 real y un campo vacio significan cosas muy distintas para
// una medida ("mide cero" vs "no se puso nada").
function numeroONulo(valor: string): number | null {
  if (valor.trim() === "") return null;
  const n = Number(valor);
  return Number.isNaN(n) ? null : n;
}

function ConfidenceBadge({ confianza }: { confianza: number }) {
  const tone = confianza >= 0.85 ? "ok" : confianza >= 0.6 ? "warn" : "danger";
  return <Badge tone={tone}>confianza {(confianza * 100).toFixed(0)}%</Badge>;
}

export function PiezaCard({ pieza, readOnly, onConfirmar, onGuardarEdicion, onBuscarMedidasFaltantes, confirming, buscandoMedidas }: PiezaCardProps) {
  const [editando, setEditando] = useState(false);
  const [modoJson, setModoJson] = useState(false);
  const [borrador, setBorrador] = useState<Pieza>(() => clonar(pieza));
  const [borradorJson, setBorradorJson] = useState(() => JSON.stringify(pieza, null, 2));
  const [errorJson, setErrorJson] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [preguntasRevisadas, setPreguntasRevisadas] = useState(false);

  const d = pieza.dimensiones;
  const preguntasPendientes = pieza.extraccion.campos_baja_confianza;
  const tienePreguntas = preguntasPendientes.length > 0;
  const puedeConfirmar = !tienePreguntas || preguntasRevisadas;

  function empezarEdicion() {
    const copia = clonar(pieza);
    setBorrador(copia);
    setBorradorJson(JSON.stringify(copia, null, 2));
    setErrorJson(null);
    setModoJson(false);
    setEditando(true);
  }

  function actualizar(mutador: (p: Pieza) => void) {
    setBorrador((actual) => {
      const copia = clonar(actual);
      mutador(copia);
      return copia;
    });
  }

  function actualizarFeature(i: number, cambios: Partial<Feature>) {
    actualizar((p) => {
      p.features[i] = { ...p.features[i], ...cambios };
    });
  }

  function eliminarFeature(i: number) {
    actualizar((p) => {
      p.features.splice(i, 1);
    });
  }

  function agregarFeature() {
    actualizar((p) => {
      p.features.push({ tipo: "barreno", pasante: true, cantidad: 1, gdt: [] });
    });
  }

  function cambiarAJson() {
    setBorradorJson(JSON.stringify(borrador, null, 2));
    setModoJson(true);
  }

  function cambiarAFormulario() {
    try {
      setBorrador(JSON.parse(borradorJson));
      setErrorJson(null);
      setModoJson(false);
    } catch {
      setErrorJson("El JSON no es valido - revisa comas/llaves antes de volver al formulario.");
    }
  }

  async function guardar() {
    setErrorJson(null);
    let final: Pieza = borrador;
    if (modoJson) {
      try {
        final = JSON.parse(borradorJson);
      } catch {
        setErrorJson("El JSON no es valido - revisa comas/llaves.");
        return;
      }
    }
    if (!onGuardarEdicion) return;
    setGuardando(true);
    try {
      await onGuardarEdicion(final);
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
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-[var(--color-text-faint)]">
              {modoJson ? "Editando el JSON completo (avanzado)." : "Edita los campos directamente - no hace falta tocar JSON."}
            </p>
            <Button
              variant="ghost"
              icon={<Braces className="h-3.5 w-3.5" />}
              onClick={modoJson ? cambiarAFormulario : cambiarAJson}
              className="!px-2 !py-1 text-xs"
            >
              {modoJson ? "Volver al formulario" : "Editar como JSON (avanzado)"}
            </Button>
          </div>

          {modoJson ? (
            <textarea
              value={borradorJson}
              onChange={(e) => setBorradorJson(e.target.value)}
              spellCheck={false}
              className="h-72 w-full resize-y rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 font-mono text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
            />
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <CampoTexto label="Pieza" value={borrador.pieza} onChange={(v) => actualizar((p) => (p.pieza = v))} />
                <CampoTexto label="Material" value={borrador.material.nombre} onChange={(v) => actualizar((p) => (p.material.nombre = v))} />
                <CampoNumero label="Cantidad" value={borrador.cantidad} onChange={(v) => actualizar((p) => (p.cantidad = v ?? 1))} />
                <CampoNumero
                  label="Tolerancia general (mm)"
                  value={borrador.tolerancia_general.valor_mm}
                  onChange={(v) => actualizar((p) => (p.tolerancia_general.valor_mm = v ?? 0.1))}
                />
                {borrador.dimensiones.forma_base === "rectangular" ? (
                  <>
                    <CampoNumero label="Largo (mm)" value={borrador.dimensiones.largo_mm} onChange={(v) => actualizar((p) => (p.dimensiones.largo_mm = v))} />
                    <CampoNumero label="Ancho (mm)" value={borrador.dimensiones.ancho_mm} onChange={(v) => actualizar((p) => (p.dimensiones.ancho_mm = v))} />
                  </>
                ) : (
                  <CampoNumero
                    label="Diámetro (mm)"
                    value={borrador.dimensiones.diametro_mm}
                    onChange={(v) => actualizar((p) => (p.dimensiones.diametro_mm = v))}
                  />
                )}
                <CampoNumero label="Espesor (mm)" value={borrador.dimensiones.espesor_mm} onChange={(v) => actualizar((p) => (p.dimensiones.espesor_mm = v ?? 0))} />
                <CampoTexto
                  label="Acabado superficial"
                  value={borrador.acabado_superficial || ""}
                  onChange={(v) => actualizar((p) => (p.acabado_superficial = v || null))}
                />
              </div>

              {borrador.features.length > 0 && (
                <div className="overflow-x-auto scrollbar-thin">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-[var(--color-text-faint)]">
                        <th className="pb-2 pr-2 font-medium">#</th>
                        <th className="pb-2 pr-2 font-medium">Tipo</th>
                        <th className="pb-2 pr-2 font-medium">Ø (mm)</th>
                        <th className="pb-2 pr-2 font-medium">Largo (mm)</th>
                        <th className="pb-2 pr-2 font-medium">Ancho (mm)</th>
                        <th className="pb-2 pr-2 font-medium">Profund. (mm)</th>
                        <th className="pb-2 pr-2 font-medium">X</th>
                        <th className="pb-2 pr-2 font-medium">Y</th>
                        <th className="pb-2 pr-2 font-medium">Toler. (mm)</th>
                        <th className="pb-2 font-medium"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {borrador.features.map((f, i) => (
                        <tr key={f.id || i} className="border-t border-[var(--color-border-soft)] align-top">
                          <td className="py-1.5 pr-2 text-[var(--color-text-muted)]">{i + 1}</td>
                          <td className="py-1.5 pr-2 capitalize text-[var(--color-text)]">{f.tipo.replace(/_/g, " ")}</td>
                          <td className="w-20 py-1.5 pr-2">
                            <CeldaNumero valor={f.diametro_mm} onChange={(v) => actualizarFeature(i, { diametro_mm: v })} />
                          </td>
                          <td className="w-20 py-1.5 pr-2">
                            <CeldaNumero valor={f.largo_mm} onChange={(v) => actualizarFeature(i, { largo_mm: v })} />
                          </td>
                          <td className="w-20 py-1.5 pr-2">
                            <CeldaNumero valor={f.ancho_mm} onChange={(v) => actualizarFeature(i, { ancho_mm: v })} />
                          </td>
                          <td className="w-20 py-1.5 pr-2">
                            <CeldaNumero valor={f.profundidad_mm} onChange={(v) => actualizarFeature(i, { profundidad_mm: v })} />
                          </td>
                          {f.posiciones?.length ? (
                            <td className="py-1.5 pr-2 text-[var(--color-text-faint)]" colSpan={2}>
                              {f.posiciones.length} posiciones (patrón) - usa JSON avanzado para editarlas
                            </td>
                          ) : (
                            <>
                              <td className="w-16 py-1.5 pr-2">
                                <CeldaNumero
                                  valor={f.posicion?.x ?? null}
                                  onChange={(v) => actualizarFeature(i, { posicion: v === null ? null : { x: v, y: f.posicion?.y ?? 0 } })}
                                />
                              </td>
                              <td className="w-16 py-1.5 pr-2">
                                <CeldaNumero
                                  valor={f.posicion?.y ?? null}
                                  onChange={(v) => actualizarFeature(i, { posicion: v === null ? null : { x: f.posicion?.x ?? 0, y: v } })}
                                />
                              </td>
                            </>
                          )}
                          <td className="w-20 py-1.5 pr-2">
                            <CeldaNumero valor={f.tolerancia_mm} onChange={(v) => actualizarFeature(i, { tolerancia_mm: v })} />
                          </td>
                          <td className="py-1.5">
                            <button
                              type="button"
                              onClick={() => eliminarFeature(i)}
                              className="rounded p-1 text-[var(--color-text-faint)] hover:bg-[var(--color-danger)]/10 hover:text-[var(--color-danger)]"
                              title="Eliminar este feature"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <Button variant="ghost" icon={<Plus className="h-3.5 w-3.5" />} onClick={agregarFeature} className="!px-2 !py-1 text-xs">
                Agregar feature
              </Button>
            </div>
          )}

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
                  {!readOnly && onBuscarMedidasFaltantes && (
                    <Button
                      variant="secondary"
                      icon={<RefreshCw className="h-3.5 w-3.5" />}
                      onClick={onBuscarMedidasFaltantes}
                      loading={buscandoMedidas}
                      className="mt-2.5 !px-2.5 !py-1.5 text-xs"
                    >
                      Buscar estas medidas de nuevo en el plano
                    </Button>
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
              <Button variant="secondary" icon={<Pencil className="h-3.5 w-3.5" />} onClick={empezarEdicion}>
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

function CampoTexto({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block min-w-0">
      <span className="text-[var(--color-text-faint)]">{label}</span>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} className={`mt-0.5 ${INPUT_CLASS}`} />
    </label>
  );
}

function CampoNumero({ label, value, onChange }: { label: string; value: number | null | undefined; onChange: (v: number | null) => void }) {
  return (
    <label className="block min-w-0">
      <span className="text-[var(--color-text-faint)]">{label}</span>
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(numeroONulo(e.target.value))}
        className={`mt-0.5 ${INPUT_CLASS}`}
      />
    </label>
  );
}

function CeldaNumero({ valor, onChange }: { valor: number | null | undefined; onChange: (v: number | null) => void }) {
  return (
    <input
      type="number"
      value={valor ?? ""}
      onChange={(e) => onChange(numeroONulo(e.target.value))}
      placeholder="—"
      className={INPUT_CLASS}
    />
  );
}
