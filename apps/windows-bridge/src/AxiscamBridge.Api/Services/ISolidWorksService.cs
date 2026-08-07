using AxiscamBridge.Api.Contracts;

namespace AxiscamBridge.Api.Services;

/// Implemented for real by AxiscamBridge.SolidWorks (COM interop, Windows +
/// SolidWorks only, loaded as an optional plugin - see PluginLoader). This
/// interface is the entire contract the rest of the app depends on, so it
/// never needs to know whether it's talking to real SolidWorks or the
/// unavailable stub.
public interface ISolidWorksService
{
    bool EstaDisponible { get; }
    string? Version { get; }
    Task<ModeloResultado> GenerarModeloAsync(Pieza pieza, CancellationToken ct = default);
}

public interface IMastercamService
{
    bool EstaDisponible { get; }
    string? Version { get; }
    Task<CodigoGResultado> GenerarCodigoGAsync(Pieza pieza, TrayectoriaResultado plan, string postprocesador, CancellationToken ct = default);
}
