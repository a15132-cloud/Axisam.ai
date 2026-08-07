using System.Text.Json.Serialization;

namespace AxiscamBridge.Api.Contracts;

// Mirrors apps/orchestrator/app/schemas/piece.py field-for-field (same
// JSON property names) so the Python orchestrator and this bridge speak
// the exact same wire format - neither side re-derives or reinterprets
// the other's shape.

public sealed class Posicion2D
{
    [JsonPropertyName("x")] public double X { get; set; }
    [JsonPropertyName("y")] public double Y { get; set; }
}

public sealed class SimboloGDT
{
    [JsonPropertyName("tipo")] public string Tipo { get; set; } = "";
    [JsonPropertyName("valor_mm")] public double ValorMm { get; set; }
    [JsonPropertyName("datum_referencia")] public string? DatumReferencia { get; set; }
    [JsonPropertyName("aplica_a")] public string? AplicaA { get; set; }
}

public sealed class Feature
{
    [JsonPropertyName("id")] public string? Id { get; set; }
    [JsonPropertyName("tipo")] public string Tipo { get; set; } = "";
    [JsonPropertyName("diametro_mm")] public double? DiametroMm { get; set; }
    [JsonPropertyName("profundidad_mm")] public double? ProfundidadMm { get; set; }
    [JsonPropertyName("ancho_mm")] public double? AnchoMm { get; set; }
    [JsonPropertyName("largo_mm")] public double? LargoMm { get; set; }
    [JsonPropertyName("radio_mm")] public double? RadioMm { get; set; }
    [JsonPropertyName("angulo_grados")] public double? AnguloGrados { get; set; }
    [JsonPropertyName("posicion")] public Posicion2D? Posicion { get; set; }
    [JsonPropertyName("posiciones")] public List<Posicion2D>? Posiciones { get; set; }
    [JsonPropertyName("cara")] public string? Cara { get; set; } = "superior";
    [JsonPropertyName("pasante")] public bool Pasante { get; set; } = true;
    [JsonPropertyName("cantidad")] public int Cantidad { get; set; } = 1;
    [JsonPropertyName("tolerancia_mm")] public double? ToleranciaMm { get; set; }
    [JsonPropertyName("rosca")] public string? Rosca { get; set; }
    [JsonPropertyName("gdt")] public List<SimboloGDT> Gdt { get; set; } = new();

    /// Same fallback rule as Feature.lista_posiciones() in piece.py.
    public List<Posicion2D> ListaPosiciones()
    {
        if (Posiciones is { Count: > 0 }) return Posiciones;
        if (Posicion is not null) return new List<Posicion2D> { Posicion };
        return new List<Posicion2D>();
    }
}

public sealed class Dimensiones
{
    [JsonPropertyName("forma_base")] public string FormaBase { get; set; } = "rectangular";
    [JsonPropertyName("largo_mm")] public double? LargoMm { get; set; }
    [JsonPropertyName("ancho_mm")] public double? AnchoMm { get; set; }
    [JsonPropertyName("diametro_mm")] public double? DiametroMm { get; set; }
    [JsonPropertyName("espesor_mm")] public double EspesorMm { get; set; }
    [JsonPropertyName("longitud_mm")] public double? LongitudMm { get; set; }
}

public sealed class ToleranciaGeneral
{
    [JsonPropertyName("valor_mm")] public double ValorMm { get; set; } = 0.1;
    [JsonPropertyName("norma")] public string? Norma { get; set; } = "ISO 2768-m";
}

public sealed class Material
{
    [JsonPropertyName("nombre")] public string Nombre { get; set; } = "";
    [JsonPropertyName("designacion")] public string? Designacion { get; set; }
    [JsonPropertyName("dureza")] public string? Dureza { get; set; }
}

public sealed class ExtraccionMeta
{
    [JsonPropertyName("confianza_global")] public double ConfianzaGlobal { get; set; }
    [JsonPropertyName("campos_baja_confianza")] public List<string> CamposBajaConfianza { get; set; } = new();
    [JsonPropertyName("notas")] public string? Notas { get; set; }
    [JsonPropertyName("archivo_origen")] public string? ArchivoOrigen { get; set; }
}

public sealed class Pieza
{
    [JsonPropertyName("pieza")] public string NombrePieza { get; set; } = "";
    [JsonPropertyName("tipo_maquinado")] public string TipoMaquinado { get; set; } = "fresado";
    [JsonPropertyName("material")] public Material Material { get; set; } = new();
    [JsonPropertyName("dimensiones")] public Dimensiones Dimensiones { get; set; } = new();
    [JsonPropertyName("tolerancia_general")] public ToleranciaGeneral ToleranciaGeneral { get; set; } = new();
    [JsonPropertyName("features")] public List<Feature> Features { get; set; } = new();
    [JsonPropertyName("acabado_superficial")] public string? AcabadoSuperficial { get; set; }
    [JsonPropertyName("cantidad")] public int Cantidad { get; set; } = 1;
    [JsonPropertyName("unidades")] public string Unidades { get; set; } = "mm";
    [JsonPropertyName("extraccion")] public ExtraccionMeta Extraccion { get; set; } = new();
}
