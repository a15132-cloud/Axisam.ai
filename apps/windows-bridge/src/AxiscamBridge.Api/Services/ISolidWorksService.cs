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

    /// Re-activates and brings to the front the SOLIDWORKS document from
    /// the most recent GenerarModeloAsync call in this process, so "Ver en
    /// SolidWorks" in the chat jumps to the real, already-open part
    /// instead of the user having to find it themselves. False when
    /// nothing has been generated yet in this bridge session.
    Task<bool> ActivarUltimoModeloAsync(CancellationToken ct = default);
}

public interface IMastercamService
{
    bool EstaDisponible { get; }
    string? Version { get; }
    Task<CodigoGResultado> GenerarCodigoGAsync(Pieza pieza, TrayectoriaResultado plan, string postprocesador, CancellationToken ct = default);

    /// Whether mastercam.exe was found on this machine - distinct from
    /// EstaDisponible (which is about verified G-code automation, and is
    /// always false today, see MastercamService's class remarks). Gates
    /// AbrirStepAsync, which only needs the executable to exist.
    bool EstaInstalado { get; }

    /// Launches Mastercam and best-effort opens the given STEP file so the
    /// user lands on the actual model instead of an empty window. This is
    /// NOT the same guarantee as SolidWorks's ActivarUltimoModeloAsync -
    /// Mastercam never actually built anything automatically, so this is
    /// "open the file for me," not "take me to what you did."
    Task<bool> AbrirStepAsync(string rutaStepAbsoluta, CancellationToken ct = default);
}
