using AxiscamBridge.Api.Contracts;

namespace AxiscamBridge.Api.Services;

/// What every /health check and every generation attempt gets when the
/// real plugin (AxiscamBridge.SolidWorks / .Mastercam) wasn't found or
/// failed to load - e.g. this machine doesn't have SolidWorks installed,
/// or the interop DLLs weren't at the configured path when the plugin
/// project was built. The orchestrator on the Python side reads
/// `esta_disponible` and falls back to its own simulation engine, so this
/// is a normal, expected state, not an error condition on its own.
public sealed class UnavailableSolidWorksService : ISolidWorksService
{
    private readonly string _razon;
    public UnavailableSolidWorksService(string razon) => _razon = razon;

    public bool EstaDisponible => false;
    public string? Version => null;

    public Task<ModeloResultado> GenerarModeloAsync(Pieza pieza, CancellationToken ct = default) =>
        throw new InvalidOperationException($"SolidWorks no esta disponible en este equipo: {_razon}");

    public Task<bool> ActivarUltimoModeloAsync(CancellationToken ct = default) => Task.FromResult(false);
}

public sealed class UnavailableMastercamService : IMastercamService
{
    private readonly string _razon;
    public UnavailableMastercamService(string razon) => _razon = razon;

    public bool EstaDisponible => false;
    public bool EstaInstalado => false;
    public string? Version => null;

    public Task<CodigoGResultado> GenerarCodigoGAsync(Pieza pieza, TrayectoriaResultado plan, string postprocesador, CancellationToken ct = default) =>
        throw new InvalidOperationException($"Mastercam no esta disponible en este equipo: {_razon}");

    public Task<bool> AbrirStepAsync(string rutaStepAbsoluta, CancellationToken ct = default) =>
        throw new InvalidOperationException($"Mastercam no esta disponible en este equipo: {_razon}");
}
