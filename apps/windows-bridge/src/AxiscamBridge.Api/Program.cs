using System.Text.Json.Serialization;
using AxiscamBridge.Api.Contracts;
using AxiscamBridge.Api.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.ConfigureHttpJsonOptions(options =>
{
    // Every DTO property already carries an explicit [JsonPropertyName]
    // matching the Python side's snake_case field names - no naming
    // policy needed or wanted here.
    options.SerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
});

var loggerFactory = LoggerFactory.Create(b => b.AddConsole());
var startupLogger = loggerFactory.CreateLogger("PluginLoader");

// Loaded once at startup - see PluginLoader for why this never throws.
var solidWorks = PluginLoader.CargarSolidWorks(startupLogger);
var mastercam = PluginLoader.CargarMastercam(startupLogger);
builder.Services.AddSingleton(solidWorks);
builder.Services.AddSingleton(mastercam);

var app = builder.Build();

app.MapGet("/health", (ISolidWorksService sw, IMastercamService mc) => new HealthResponse
{
    Status = "ok",
    SolidWorksDisponible = sw.EstaDisponible,
    MastercamDisponible = mc.EstaDisponible,
    MastercamInstalado = mc.EstaInstalado,
    VersionSolidWorks = sw.Version,
    VersionMastercam = mc.Version,
    Detalle = "Axiscam Windows Bridge - conecta la app web con SolidWorks/Mastercam instalados localmente",
});

app.MapPost("/solidworks/generar-modelo", async (Pieza pieza, ISolidWorksService sw) =>
{
    if (!sw.EstaDisponible)
        return Results.Problem("SolidWorks no esta disponible en este equipo.", statusCode: 503);

    try
    {
        var resultado = await sw.GenerarModeloAsync(pieza);
        return Results.Ok(resultado);
    }
    catch (Exception ex)
    {
        return Results.Problem($"Error generando el modelo en SolidWorks: {ex.Message}", statusCode: 500);
    }
});

app.MapPost("/mastercam/generar-codigo-g", async (GenerarCodigoGRequest req, IMastercamService mc) =>
{
    if (!mc.EstaDisponible)
        return Results.Problem("Mastercam no esta disponible en este equipo.", statusCode: 503);

    try
    {
        var resultado = await mc.GenerarCodigoGAsync(req.Pieza, req.Plan, req.Postprocesador);
        return Results.Ok(resultado);
    }
    catch (Exception ex)
    {
        return Results.Problem($"Error generando codigo G en Mastercam: {ex.Message}", statusCode: 500);
    }
});

app.MapPost("/solidworks/activar", async (ISolidWorksService sw) =>
{
    if (!sw.EstaDisponible)
        return Results.Problem("SolidWorks no esta disponible en este equipo.", statusCode: 503);

    try
    {
        var activado = await sw.ActivarUltimoModeloAsync();
        return activado
            ? Results.Ok(new ActivarResponse { Activado = true })
            : Results.Problem("No hay ningun modelo generado en esta sesion del bridge todavia.", statusCode: 409);
    }
    catch (Exception ex)
    {
        return Results.Problem($"Error activando el documento en SolidWorks: {ex.Message}", statusCode: 500);
    }
});

app.MapPost("/mastercam/abrir", async (AbrirMastercamRequest req, IMastercamService mc) =>
{
    if (!mc.EstaInstalado)
        return Results.Problem("Mastercam no parece estar instalado en este equipo.", statusCode: 503);

    try
    {
        var abierto = await mc.AbrirStepAsync(req.RutaStepAbsoluta);
        return Results.Ok(new ActivarResponse { Activado = abierto });
    }
    catch (Exception ex)
    {
        return Results.Problem($"Error abriendo Mastercam: {ex.Message}", statusCode: 500);
    }
});

app.Run("http://127.0.0.1:5757");

// Only listens on 127.0.0.1 (never 0.0.0.0) - this bridge drives licensed
// CAD/CAM software with real file-system and COM access, it must never be
// reachable from anything other than the orchestrator running on the same
// machine.

public sealed class GenerarCodigoGRequest
{
    [JsonPropertyName("pieza")] public Pieza Pieza { get; set; } = new();
    [JsonPropertyName("plan")] public TrayectoriaResultado Plan { get; set; } = new();
    [JsonPropertyName("postprocesador")] public string Postprocesador { get; set; } = "haas_vf_generico";
}

public sealed class AbrirMastercamRequest
{
    [JsonPropertyName("ruta_step_absoluta")] public string RutaStepAbsoluta { get; set; } = "";
}

public sealed class ActivarResponse
{
    [JsonPropertyName("activado")] public bool Activado { get; set; }
}
