import { useEffect, useRef, useState } from "react";
import { Upload, Play, Pause, RotateCcw, FileCode, Box, Loader2 } from "lucide-react";
import { ToolpathViewer } from "./ToolpathViewer";
import { parsearGCode, type ResultadoParseoGCode } from "../../lib/gcodeParser";
import { ErrorBoundary } from "../system/ErrorBoundary";
import { WarningBanner } from "../common/WarningBanner";
import { api, ApiError } from "../../lib/api";

const VELOCIDADES = [0.5, 1, 2, 4];

export function SimulacionEstandaloneView() {
  const [stlUrl, setStlUrl] = useState<string | null>(null);
  const [nombreModelo, setNombreModelo] = useState<string | null>(null);
  const [nombreGcode, setNombreGcode] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoParseoGCode | null>(null);
  const [errorLectura, setErrorLectura] = useState<string | null>(null);
  const [convirtiendoStep, setConvirtiendoStep] = useState(false);

  const [reproduciendo, setReproduciendo] = useState(false);
  const [velocidad, setVelocidad] = useState(1);
  const [progreso, setProgreso] = useState(0);
  const progresoRef = useRef(0);

  const inputModeloRef = useRef<HTMLInputElement>(null);
  const inputGcodeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (stlUrl) URL.revokeObjectURL(stlUrl);
    };
  }, [stlUrl]);

  async function manejarModelo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    e.target.value = "";
    if (!archivo) return;
    setErrorLectura(null);
    const nombre = archivo.name.toLowerCase();

    if (nombre.endsWith(".stl")) {
      if (stlUrl) URL.revokeObjectURL(stlUrl);
      setStlUrl(URL.createObjectURL(archivo));
      setNombreModelo(archivo.name);
      return;
    }

    if (nombre.endsWith(".step") || nombre.endsWith(".stp")) {
      // A browser can only draw a triangle mesh - STEP has exact CAD
      // surfaces, so it needs a real CAD kernel to tessellate it into one
      // first. The backend does this with the same cadquery/OpenCascade
      // engine that builds Axiscam's own models (see
      // app/geometry/export.py's convertir_step_a_stl_bytes) - this isn't
      // a client-side trick, it's a real conversion round trip.
      setConvirtiendoStep(true);
      try {
        const stlBlob = await api.convertirStepAStl(archivo);
        if (stlUrl) URL.revokeObjectURL(stlUrl);
        setStlUrl(URL.createObjectURL(stlBlob));
        setNombreModelo(archivo.name);
      } catch (err) {
        setErrorLectura(err instanceof ApiError ? err.message : "No se pudo convertir el archivo STEP.");
      } finally {
        setConvirtiendoStep(false);
      }
      return;
    }

    setErrorLectura("Este visor solo puede mostrar archivos .STL o .STEP/.STP - ninguno de los demás archivos del proyecto sirve aquí.");
  }

  async function manejarGcode(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    e.target.value = "";
    if (!archivo) return;
    setErrorLectura(null);
    try {
      const texto = await archivo.text();
      const parseo = parsearGCode(texto);
      if (parseo.segmentos.length === 0) {
        setErrorLectura("No se encontró ningún movimiento reconocible en este archivo de código G.");
        setResultado(null);
        return;
      }
      setResultado(parseo);
      setNombreGcode(archivo.name);
      setReproduciendo(false);
      setProgreso(0);
      progresoRef.current = 0;
    } catch {
      setErrorLectura("No se pudo leer el archivo de código G - asegúrate de que sea un archivo de texto plano.");
    }
  }

  function reiniciar() {
    setReproduciendo(false);
    setProgreso(0);
    progresoRef.current = 0;
  }

  const longitudTotal =
    resultado?.segmentos.reduce((acc, s) => acc + Math.hypot(s.hasta[0] - s.desde[0], s.hasta[1] - s.desde[1], s.hasta[2] - s.desde[2]), 0) ?? 0;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto scrollbar-thin p-4 sm:p-6">
      <div className="mb-4">
        <h2 className="font-display text-lg font-semibold text-[var(--color-text)]">Simulación de código G</h2>
        <p className="mt-1 max-w-2xl text-xs text-[var(--color-text-muted)]">
          Sube un modelo (.STL o .STEP - el STEP se convierte automáticamente) y un archivo de código G para ver la
          trayectoria de la herramienta antes de cargarla en la máquina. Esta es una vista independiente - no crea ni
          modifica ningún proyecto. Muestra exactamente por dónde pasa el centro de la herramienta y en qué orden, tal
          como está escrito en el archivo -{" "}
          <strong className="text-[var(--color-text)]">no verifica colisiones contra el material o las mordazas</strong>, eso
          lo sigue haciendo un maquinista antes de maquinar.
        </p>
      </div>

      <div className="mb-1.5 flex flex-wrap gap-2">
        {/* No "accept" filter on either input on purpose - restricting it by
            extension/MIME hid valid files in some browsers/OS file pickers
            (same bug already found and fixed on the chat attachment picker).
            Both files are validated by content/extension after picking
            instead, in manejarModelo/manejarGcode below. */}
        <input ref={inputModeloRef} type="file" className="hidden" onChange={manejarModelo} disabled={convirtiendoStep} />
        <button
          onClick={() => inputModeloRef.current?.click()}
          disabled={convirtiendoStep}
          className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-3)] disabled:opacity-60"
        >
          {convirtiendoStep ? <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" /> : <Box className="h-4 w-4 text-[var(--color-accent)]" />}
          {convirtiendoStep ? "Convirtiendo STEP…" : (nombreModelo ?? "Subir modelo (.STL o .STEP)")}
        </button>

        <input ref={inputGcodeRef} type="file" className="hidden" onChange={manejarGcode} />
        <button
          onClick={() => inputGcodeRef.current?.click()}
          className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-3)]"
        >
          <FileCode className="h-4 w-4 text-[var(--color-accent)]" />
          {nombreGcode ?? "Subir código G"}
        </button>
      </div>
      <p className="mb-4 max-w-2xl text-[11px] text-[var(--color-text-faint)]">
        Modelo: el <strong className="text-[var(--color-text-muted)]">.STEP</strong> (el mismo que usan SolidWorks y
        Mastercam) o el <strong className="text-[var(--color-text-muted)]">.STL</strong> - ambos están junto al mensaje
        del modelo 3D en tu proyecto. Código G: el archivo que descargaste al aprobar el proyecto - Axiscam lo nombra
        con extensión <strong className="text-[var(--color-text-muted)]">.nc</strong> (la mayoría de las máquinas) o{" "}
        <strong className="text-[var(--color-text-muted)]">.mpf</strong> (controles Siemens) - es texto plano, ábrelo
        con cualquier editor de texto si no estás seguro de cuál archivo es.
      </p>

      {errorLectura && <p className="mb-3 text-xs text-[var(--color-danger)]">{errorLectura}</p>}

      {resultado && resultado.advertencias.length > 0 && (
        <div className="mb-4">
          <WarningBanner title="Advertencias al interpretar el código G" items={resultado.advertencias} />
        </div>
      )}

      {!resultado ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-border)] py-16 text-center text-sm text-[var(--color-text-faint)]">
          <Upload className="h-6 w-6" />
          Sube un archivo de código G para empezar. El modelo (.STL o .STEP) es opcional pero ayuda a ver la trayectoria en contexto.
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="min-h-[360px] flex-1">
            <ErrorBoundary compact>
              <ToolpathViewer
                stlUrl={stlUrl}
                segmentos={resultado.segmentos}
                reproduciendo={reproduciendo}
                velocidad={velocidad}
                progreso={progreso}
                progresoRef={progresoRef}
                onProgreso={setProgreso}
              />
            </ErrorBoundary>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5">
            <button
              onClick={() => setReproduciendo((r) => !r)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent)] text-black"
              title={reproduciendo ? "Pausar" : "Reproducir"}
            >
              {reproduciendo ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button
              onClick={reiniciar}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
              title="Reiniciar"
            >
              <RotateCcw className="h-4 w-4" />
            </button>

            <input
              type="range"
              min={0}
              max={longitudTotal || 1}
              step={longitudTotal / 1000 || 1}
              value={progreso}
              onChange={(e) => {
                const v = Number(e.target.value);
                setProgreso(v);
                progresoRef.current = v;
                setReproduciendo(false);
              }}
              className="min-w-[120px] flex-1 accent-[var(--color-accent)]"
            />

            <div className="flex shrink-0 items-center gap-1 text-xs text-[var(--color-text-muted)]">
              {VELOCIDADES.map((v) => (
                <button
                  key={v}
                  onClick={() => setVelocidad(v)}
                  className={`rounded px-1.5 py-0.5 ${velocidad === v ? "bg-[var(--color-accent)] text-black" : "hover:bg-[var(--color-surface-3)]"}`}
                >
                  {v}x
                </button>
              ))}
            </div>

            <span className="shrink-0 text-[10px] text-[var(--color-text-faint)]">
              {resultado.segmentos.length} movimientos · {Math.round(longitudTotal)} mm de recorrido
              {resultado.lineasIgnoradas > 0 ? ` · ${resultado.lineasIgnoradas} líneas sin movimiento ignoradas` : ""}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
