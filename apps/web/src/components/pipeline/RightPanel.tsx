import { FileText } from "lucide-react";
import { Card, CardHeader } from "../common/Card";
import { Badge } from "../common/Badge";
import { ActividadTimeline } from "./ActividadTimeline";
import { StlViewer } from "../viewer/StlViewer";
import { api } from "../../lib/api";
import type { Proyecto } from "../../lib/types";

const IMAGE_EXT = [".png", ".jpg", ".jpeg", ".webp", ".gif"];

const ETAPA_LABEL: Record<Proyecto["etapa"], string> = {
  plano_subido: "Plano subido",
  extrayendo: "Extrayendo datos",
  esperando_confirmacion_extraccion: "Esperando confirmación",
  modelando: "Modelando",
  esperando_confirmacion_modelo: "Esperando confirmación",
  generando_trayectorias: "Generando trayectorias",
  simulando: "Simulando",
  esperando_aprobacion_final: "Esperando aprobación",
  aprobado: "Aprobado",
  rechazado: "Rechazado",
  error: "Error",
};

const ETAPA_TONE: Record<Proyecto["etapa"], "neutral" | "accent" | "ok" | "warn" | "danger"> = {
  plano_subido: "neutral",
  extrayendo: "accent",
  esperando_confirmacion_extraccion: "warn",
  modelando: "accent",
  esperando_confirmacion_modelo: "warn",
  generando_trayectorias: "accent",
  simulando: "accent",
  esperando_aprobacion_final: "warn",
  aprobado: "ok",
  rechazado: "danger",
  error: "danger",
};

export function RightPanel({ proyecto }: { proyecto: Proyecto }) {
  const nombrePlano = proyecto.archivo_plano || "";
  const esImagen = IMAGE_EXT.some((ext) => nombrePlano.toLowerCase().endsWith(ext));
  const esPdf = nombrePlano.toLowerCase().endsWith(".pdf");
  const stl = proyecto.archivos.find((a) => a.tipo === "stl");

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto scrollbar-thin p-4">
      <Card>
        <CardHeader
          title="Datos del proyecto"
          right={<Badge tone={ETAPA_TONE[proyecto.etapa]}>{ETAPA_LABEL[proyecto.etapa]}</Badge>}
        />
        <div className="space-y-1.5 px-4 py-3 text-xs">
          <Row label="ID" value={proyecto.id} />
          <Row label="Creado" value={new Date(proyecto.creado_en).toLocaleString("es-MX")} />
          <Row label="Actualizado" value={new Date(proyecto.actualizado_en).toLocaleString("es-MX")} />
          {proyecto.postprocesador && <Row label="Postprocesador" value={proyecto.postprocesador} />}
          {proyecto.aprobado_por && <Row label="Aprobado por" value={proyecto.aprobado_por} />}
        </div>
      </Card>

      {nombrePlano && (
        <Card delay={0.05}>
          <CardHeader title="Plano subido" subtitle={nombrePlano} />
          <div className="p-4">
            {esImagen ? (
              <img
                src={api.planoOriginalUrl(proyecto.id)}
                alt="Plano subido"
                className="max-h-80 w-full rounded-lg border border-[var(--color-border)] object-contain bg-white"
              />
            ) : esPdf ? (
              <iframe src={api.planoOriginalUrl(proyecto.id)} title="Plano PDF" className="h-80 w-full rounded-lg border border-[var(--color-border)]" />
            ) : (
              <a
                href={api.planoOriginalUrl(proyecto.id)}
                download
                className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              >
                <FileText className="h-4 w-4" /> {nombrePlano} (sin vista previa - descargar)
              </a>
            )}
          </div>
        </Card>
      )}

      {stl && (
        <Card delay={0.1}>
          <CardHeader title="Vista 3D previa" />
          <div className="p-4">
            <StlViewer url={api.archivoUrl(proyecto.id, stl.nombre)} />
          </div>
        </Card>
      )}

      <Card delay={0.15} className="flex-1">
        <CardHeader title="Actividad del proyecto" />
        <div className="p-4">
          <ActividadTimeline eventos={proyecto.actividad} />
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--color-text-faint)]">{label}</span>
      <span className="font-medium text-[var(--color-text)]">{value}</span>
    </div>
  );
}
