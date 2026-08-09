using System.Text.Json.Serialization;

namespace AxiscamBridge.Api.Contracts;

/// Mirrors app/geometry/builder.py::BuildResult + app/geometry/export.py's
/// property dict, plus the actual file bytes (base64) since this crosses
/// a process boundary instead of writing straight to a shared filesystem
/// the way the Python-only path does.
public sealed class ModeloResultado
{
    [JsonPropertyName("archivo_step_base64")] public string ArchivoStepBase64 { get; set; } = "";
    [JsonPropertyName("archivo_stl_base64")] public string ArchivoStlBase64 { get; set; } = "";
    [JsonPropertyName("nombre_archivo")] public string NombreArchivo { get; set; } = "pieza";
    [JsonPropertyName("advertencias")] public List<string> Advertencias { get; set; } = new();
    [JsonPropertyName("features_omitidos")] public List<string> FeaturesOmitidos { get; set; } = new();
    [JsonPropertyName("propiedades_geometricas")] public PropiedadesGeometricas? PropiedadesGeometricas { get; set; }
}

public sealed class PropiedadesGeometricas
{
    [JsonPropertyName("volumen_mm3")] public double VolumenMm3 { get; set; }
    [JsonPropertyName("area_superficial_mm2")] public double AreaSuperficialMm2 { get; set; }
    [JsonPropertyName("bbox_mm")] public BoundingBox BboxMm { get; set; } = new();
}

public sealed class BoundingBox
{
    [JsonPropertyName("x")] public double X { get; set; }
    [JsonPropertyName("y")] public double Y { get; set; }
    [JsonPropertyName("z")] public double Z { get; set; }
}

/// Mirrors app/schemas/project.py::ToolpathPlan.
public sealed class TrayectoriaResultado
{
    [JsonPropertyName("estrategia")] public string Estrategia { get; set; } = "";
    [JsonPropertyName("herramientas")] public List<Dictionary<string, object?>> Herramientas { get; set; } = new();
    [JsonPropertyName("tiempo_estimado_min")] public double? TiempoEstimadoMin { get; set; }
    [JsonPropertyName("operaciones")] public List<Dictionary<string, object?>> Operaciones { get; set; } = new();
    [JsonPropertyName("advertencias")] public List<string> Advertencias { get; set; } = new();
}

/// Mirrors app/cam/gcode.py::ResultadoGCode.
public sealed class CodigoGResultado
{
    [JsonPropertyName("contenido")] public string Contenido { get; set; } = "";
    [JsonPropertyName("operaciones_con_movimiento_real")] public int OperacionesConMovimientoReal { get; set; }
    [JsonPropertyName("operaciones_solo_planeadas")] public int OperacionesSoloPlaneadas { get; set; }
    [JsonPropertyName("advertencias")] public List<string> Advertencias { get; set; } = new();
    [JsonPropertyName("es_simulacion")] public bool EsSimulacion { get; set; }
}

public sealed class HealthResponse
{
    [JsonPropertyName("status")] public string Status { get; set; } = "ok";
    [JsonPropertyName("solidworks_disponible")] public bool SolidWorksDisponible { get; set; }
    [JsonPropertyName("mastercam_disponible")] public bool MastercamDisponible { get; set; }
    // True whenever mastercam.exe was found, even though MastercamDisponible
    // (full automation) is always false today - see MastercamService's
    // class remarks. Lets the frontend offer "Abrir en Mastercam" (launch +
    // best-effort open the file) without implying automation exists.
    [JsonPropertyName("mastercam_instalado")] public bool MastercamInstalado { get; set; }
    [JsonPropertyName("version_solidworks")] public string? VersionSolidWorks { get; set; }
    [JsonPropertyName("version_mastercam")] public string? VersionMastercam { get; set; }
    [JsonPropertyName("detalle")] public string? Detalle { get; set; }
}
