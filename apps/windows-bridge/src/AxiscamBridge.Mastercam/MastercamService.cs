using System.Diagnostics;
using AxiscamBridge.Api.Contracts;
using AxiscamBridge.Api.Services;

namespace AxiscamBridge.Mastercam;

/// Honesty note, upfront: this connector is at a different confidence
/// level than AxiscamBridge.SolidWorks, deliberately. SOLIDWORKS exposes
/// one stable, well-documented external COM automation object
/// (SldWorks.Application) that has worked the same way across a very
/// wide range of versions. Mastercam does not have an equivalent - its
/// automation story is primarily NET-Hooks, which are C# plugin DLLs
/// that Mastercam LOADS INTO ITSELF and runs from its own UI/ribbon, not
/// something an external process calls over HTTP the way this bridge
/// calls SOLIDWORKS. What counts as "the automation API" also genuinely
/// differs across Mastercam versions in a way SOLIDWORKS's API mostly
/// doesn't.
///
/// So this class does the part that's real and version-independent
/// (detect whether Mastercam is installed and which version, via the
/// filesystem - no COM, no guessing at an API surface I'm not confident
/// about) and is explicit that full "Pieza JSON in, verified G-code out"
/// automation is NOT implemented here. Completing it means writing a
/// Mastercam Net-Hook against your specific installed version's SDK that
/// this service can hand off to (see README's "Completing the Mastercam
/// connector" section) - pretending to call an API I can't verify exists
/// for your version would be worse than being explicit about the gap.
public sealed class MastercamService : IMastercamService
{
    private readonly (bool encontrado, string? version, string? exePath) _deteccion;

    public MastercamService()
    {
        _deteccion = DetectarInstalacion();
    }

    // Deliberately false even when Mastercam IS detected: this reports
    // whether GenerarCodigoGAsync can actually produce real, verified
    // G-code right now, and it can't yet. See class remarks.
    public bool EstaDisponible => false;

    // Unlike EstaDisponible, this is genuinely true whenever mastercam.exe
    // was found - it only gates AbrirStepAsync (launch the app, open a
    // file), which needs nothing beyond the executable existing.
    public bool EstaInstalado => _deteccion.encontrado;

    public string? Version => _deteccion.version;

    public Task<CodigoGResultado> GenerarCodigoGAsync(Pieza pieza, TrayectoriaResultado plan, string postprocesador, CancellationToken ct = default)
    {
        var mensaje = _deteccion.encontrado
            ? $"Mastercam {_deteccion.version} esta instalado en este equipo, pero la automatizacion todavia no esta " +
              "implementada en este bridge (requiere un Net-Hook especifico para tu version - ver README). " +
              "Importa el STEP generado manualmente en Mastercam por ahora."
            : "Mastercam no parece estar instalado en este equipo.";
        throw new NotSupportedException(mensaje);
    }

    // Best-effort only, and explicit about it: passing a file path as the
    // first argument to open-on-launch is the near-universal Windows GUI
    // app convention, but it is NOT confirmed against this specific
    // Mastercam version's actual command-line contract (unlike the
    // filesystem detection above, which needs no such assumption). If the
    // file doesn't load automatically, launching still succeeds and the
    // user imports the STEP manually from the button already offered
    // above it in the chat - this never blocks on the guess being right.
    public Task<bool> AbrirStepAsync(string rutaStepAbsoluta, CancellationToken ct = default)
    {
        if (!_deteccion.encontrado || _deteccion.exePath is null)
            throw new InvalidOperationException("Mastercam no parece estar instalado en este equipo.");

        try
        {
            Process.Start(new ProcessStartInfo(_deteccion.exePath, $"\"{rutaStepAbsoluta}\"") { UseShellExecute = true });
            return Task.FromResult(true);
        }
        catch (Exception)
        {
            // Fall back to just launching Mastercam with no arguments -
            // still real and useful even if the file-open guess was wrong.
            Process.Start(new ProcessStartInfo(_deteccion.exePath) { UseShellExecute = true });
            return Task.FromResult(true);
        }
    }

    private static (bool, string?, string?) DetectarInstalacion()
    {
        // Mastercam installs as "Mcam<year>" (e.g. Mcam2024) under
        // Program Files by long-standing convention. Scanning for that
        // pattern plus mastercam.exe's own file version is filesystem-only
        // - no COM, no version-specific API surface, so this part is on
        // solid ground even though I can't run it here to confirm.
        var raices = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
        };

        foreach (var raiz in raices.Distinct().Where(Directory.Exists))
        {
            IEnumerable<string> candidatos;
            try
            {
                candidatos = Directory.EnumerateDirectories(raiz, "Mcam*");
            }
            catch
            {
                continue;
            }

            foreach (var carpeta in candidatos)
            {
                var exe = Path.Combine(carpeta, "mastercam.exe");
                if (!File.Exists(exe)) continue;
                string? version = null;
                try
                {
                    version = FileVersionInfo.GetVersionInfo(exe).FileVersion;
                }
                catch
                {
                    // fall through with version = null; folder name below still gives a hint
                }
                return (true, version ?? Path.GetFileName(carpeta), exe);
            }
        }

        return (false, null, null);
    }
}
