using System.Diagnostics;
using System.Runtime.InteropServices;
using AxiscamBridge.Api.Contracts;
using AxiscamBridge.Api.Services;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace AxiscamBridge.SolidWorks;

/// Drives a real, locally-installed SOLIDWORKS via COM automation. This
/// file is written against long-stable, widely-documented SOLIDWORKS API
/// members (FeatureExtrusion2/FeatureCut4, stable since roughly the 2008
/// API and still present in current versions per SOLIDWORKS's own
/// backward-compatibility practice of adding FeatureExtrusion3/4 etc.
/// alongside the old ones rather than replacing them) - but it has NOT
/// been compiled or run against a real SOLIDWORKS install, because no
/// sandbox used to write this code has SOLIDWORKS or its interop
/// assemblies available. Treat this as a careful first draft, not a
/// verified integration - if a specific call throws a COM exception
/// about argument count/type, that method's exact overload is the first
/// thing to check against your installed SOLIDWORKS version's API help.
///
/// Scope, deliberately conservative for a first real-hardware pass:
/// rectangular/circular base extrusion, through-hole barrenos, STEP/STL
/// export. Blind holes, cajeras, fillets/chamfers, and lateral faces are
/// NOT implemented yet (see TODOs) - the same feature set the Python
/// cadquery bridge started with before it was verified and expanded.
///
/// Units: every SOLIDWORKS sketch/feature API call takes lengths in
/// METERS regardless of the document's display units - the single most
/// common bug source when driving SOLIDWORKS via the API. All conversions
/// from the Pieza JSON's millimeters happen at the MmToM() call site,
/// nowhere else, so there is exactly one place to check if geometry comes
/// out 1000x too big or too small.
public sealed class SolidWorksService : ISolidWorksService
{
    private const double MmToMFactor = 0.001;
    private static double MmToM(double mm) => mm * MmToMFactor;

    private readonly ISldWorks _app;
    private readonly string _version;
    private readonly string _partTemplatePath;
    private string? _ultimoTitulo;

    public SolidWorksService()
    {
        _app = ConectarOLanzar();
        _version = SafeRevision(_app);
        _partTemplatePath = Environment.GetEnvironmentVariable("AXISCAM_SW_PART_TEMPLATE")
            ?? @"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\Part.prtdot";
        // Fail fast at construction (caught by PluginLoader) if the
        // template genuinely doesn't exist - a clearer error than the
        // COM exception NewDocument would throw later.
        if (!File.Exists(_partTemplatePath))
            throw new FileNotFoundException(
                $"Plantilla de parte de SOLIDWORKS no encontrada en '{_partTemplatePath}'. " +
                "Define AXISCAM_SW_PART_TEMPLATE con la ruta real de tu plantilla .prtdot.",
                _partTemplatePath);
    }

    public bool EstaDisponible => true; // constructor already proved connectivity
    public string? Version => _version;

    private static ISldWorks ConectarOLanzar()
    {
        try
        {
            // Prefer attaching to an already-running SOLIDWORKS instance -
            // avoids a slow relaunch and any "which instance owns this
            // document" ambiguity if the user also has it open manually.
            return (ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
        }
        catch (COMException)
        {
            var type = Type.GetTypeFromProgID("SldWorks.Application")
                ?? throw new InvalidOperationException(
                    "SOLIDWORKS no parece estar instalado (ProgID 'SldWorks.Application' no registrado).");
            var app = (ISldWorks)Activator.CreateInstance(type)!;
            app.Visible = true; // background-but-invisible SOLIDWORKS is a common source of confusing hangs on license/dialog prompts
            return app;
        }
    }

    private static string SafeRevision(ISldWorks app)
    {
        try { return app.RevisionNumber(); } catch { return "desconocida"; }
    }

    public async Task<ModeloResultado> GenerarModeloAsync(Pieza pieza, CancellationToken ct = default) =>
        // The SOLIDWORKS COM API is single-threaded-apartment and not
        // async-friendly - run it on a dedicated thread so it doesn't
        // block the ASP.NET Core thread pool, without pretending the COM
        // calls themselves are asynchronous.
        await Task.Run(() => GenerarModeloSincrono(pieza), ct);

    private ModeloResultado GenerarModeloSincrono(Pieza pieza)
    {
        var advertencias = new List<string>();
        var omitidos = new List<string>();
        var d = pieza.Dimensiones;

        // PaperSize/Width/Height only matter for drawing templates - unused
        // (but still required as arguments) when TemplateName is a part
        // template, so they're 0 here.
        var swModelUntyped = _app.NewDocument(_partTemplatePath, 0, 0, 0);
        if (swModelUntyped is null)
            throw new InvalidOperationException("SOLIDWORKS.NewDocument no devolvio un documento - revisa la ruta de la plantilla.");
        var model = (IModelDoc2)swModelUntyped;
        var ext = model.Extension;

        if (d.FormaBase == "rectangular")
        {
            if (d.LargoMm is null || d.AnchoMm is null)
                throw new InvalidOperationException("forma_base=rectangular requiere largo_mm y ancho_mm");
            SketchOnTopPlane(model, ext);
            model.SketchManager.CreateCornerRectangle(0, 0, 0, MmToM(d.LargoMm.Value), MmToM(d.AnchoMm.Value), 0);
            ExitSketch(model);
            Extruir(model, MmToM(d.EspesorMm));
        }
        else if (d.FormaBase == "circular")
        {
            if (d.DiametroMm is null)
                throw new InvalidOperationException("forma_base=circular requiere diametro_mm");
            SketchOnTopPlane(model, ext);
            model.SketchManager.CreateCircleByRadius(0, 0, 0, MmToM(d.DiametroMm.Value) / 2);
            ExitSketch(model);
            Extruir(model, MmToM(d.EspesorMm));
        }
        else
        {
            throw new InvalidOperationException(
                $"forma_base='{d.FormaBase}' no soportada por el conector SOLIDWORKS todavia (igual que el motor de geometria en Python).");
        }

        foreach (var feature in pieza.Features)
        {
            if (feature.Tipo is "barreno" or "barreno_roscado")
            {
                if (feature.Cara is not (null or "superior"))
                {
                    omitidos.Add($"{feature.Tipo} (id={feature.Id}): solo caras 'superior' soportadas por el conector SOLIDWORKS por ahora");
                    continue;
                }
                if (!feature.Pasante)
                {
                    omitidos.Add($"{feature.Tipo} (id={feature.Id}): barrenos ciegos aun no soportados por el conector SOLIDWORKS - solo pasantes");
                    continue;
                }
                foreach (var pos in feature.ListaPosiciones())
                {
                    CortarBarrenoPasante(model, ext, MmToM(pos.X), MmToM(pos.Y), MmToM((feature.DiametroMm ?? 5.0) / 2), MmToM(d.EspesorMm));
                }
                if (feature.Tipo == "barreno_roscado")
                    advertencias.Add($"barreno_roscado {feature.Rosca} (id={feature.Id}): modelado como barreno liso - la geometria de la helice no se genera aun.");
            }
            else
            {
                omitidos.Add($"{feature.Tipo} (id={feature.Id}): no soportado todavia por el conector SOLIDWORKS (usa la Capa 4 simulada para esto por ahora)");
            }
        }

        var (stepBytes, stlBytes) = ExportarStepYStl(model, ext, pieza.NombrePieza);
        // Deliberately NOT calling _app.CloseDoc here anymore - the model
        // stays open in SOLIDWORKS so "Ver en SolidWorks" in the chat (see
        // ActivarUltimoModeloAsync) has an actual document to jump to.
        // Tradeoff: documents accumulate as open tabs across a session on
        // a local, single-user shop-floor install - acceptable, since the
        // point of this button is showing the user the real thing it made.
        _ultimoTitulo = model.GetTitle();

        return new ModeloResultado
        {
            ArchivoStepBase64 = Convert.ToBase64String(stepBytes),
            ArchivoStlBase64 = Convert.ToBase64String(stlBytes),
            NombreArchivo = string.IsNullOrWhiteSpace(pieza.NombrePieza) ? "pieza" : pieza.NombrePieza,
            Advertencias = advertencias,
            FeaturesOmitidos = omitidos,
        };
    }

    private static void SketchOnTopPlane(IModelDoc2 model, IModelDocExtension ext)
    {
        ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, false, 0, null!, 0);
        model.SketchManager.InsertSketch(true);
    }

    private static void ExitSketch(IModelDoc2 model) => model.SketchManager.InsertSketch(true);

    private static void Extruir(IModelDoc2 model, double profundidadM)
    {
        // FeatureExtrusion2 signature per SOLIDWORKS API help (stable
        // across a very wide version range): Sd, Flip, Dir, T1, T2, D1,
        // D2, Dchk1, Dchk2, Ddir1, Ddir2, Dang1, Dang2, OffsetReverse1,
        // OffsetReverse2, TranslateSurface1, TranslateSurface2, Merge,
        // UseFeatScope, UseAutoSelect, T0, StartOffset, FlipStartOffset.
        model.FeatureManager.FeatureExtrusion2(
            true, false, true,
            (int)swEndConditions_e.swEndCondBlind, 0,
            profundidadM, 0.0,
            false, false, false, false, 0.0, 0.0,
            false, false, false, false,
            true, true, true,
            (int)swStartConditions_e.swStartSketchPlane, 0.0, false);
    }

    private static void CortarBarrenoPasante(IModelDoc2 model, IModelDocExtension ext, double xM, double yM, double radioM, double espesorM)
    {
        ext.SelectByID2("Top Plane", "PLANE", 0, 0, 0, false, 0, null!, 0);
        model.SketchManager.InsertSketch(true);
        model.SketchManager.CreateCircleByRadius(xM, yM, 0, radioM);
        model.SketchManager.InsertSketch(true);

        // FeatureCut4 mirrors FeatureExtrusion2's parameter shape with a
        // few cut-specific flags appended (FlipSide, NormalCut, Optimize).
        model.FeatureManager.FeatureCut4(
            true, false, true,
            (int)swEndConditions_e.swEndCondThroughAll, 0,
            0.0, 0.0,
            false, false, false, false, 0.0, 0.0,
            false, false, false, false,
            true, false, false, true,
            (int)swStartConditions_e.swStartSketchPlane, 0.0, false, false);
    }

    // UNVERIFIED against a real SOLIDWORKS install, same caveat as the
    // rest of this file (see top-of-file remarks): ActivateDoc3's exact
    // parameter marshaling (ref vs out for Errors) can differ by
    // SOLIDWORKS version's interop DLL. If this throws a
    // MissingMethodException or argument-count COM error, that overload
    // is the first thing to check against your installed version's API
    // help - same debugging move as FeatureExtrusion2/FeatureCut4 above.
    public Task<bool> ActivarUltimoModeloAsync(CancellationToken ct = default) =>
        Task.Run(() =>
        {
            if (_ultimoTitulo is null) return false;

            int errors = 0;
            var activado = _app.ActivateDoc3(_ultimoTitulo, false, (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref errors);
            if (activado is null) return false;

            TraerVentanaAlFrente();
            return true;
        }, ct);

    // ActivateDoc3 only changes which document SOLIDWORKS treats as
    // active internally - it does not steal focus from whatever window
    // the user is currently looking at (the browser, in this case). A
    // plain Win32 SetForegroundWindow on the SOLIDWORKS process is the
    // standard, version-independent way to actually bring it on screen.
    private static void TraerVentanaAlFrente()
    {
        foreach (var proceso in Process.GetProcessesByName("SLDWORKS"))
        {
            if (proceso.MainWindowHandle != IntPtr.Zero)
            {
                SetForegroundWindow(proceso.MainWindowHandle);
                break;
            }
        }
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    private static (byte[] step, byte[] stl) ExportarStepYStl(IModelDoc2 model, IModelDocExtension ext, string nombrePieza)
    {
        var carpeta = Path.Combine(Path.GetTempPath(), "axiscam-bridge", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(carpeta);
        var nombreBase = string.IsNullOrWhiteSpace(nombrePieza) ? "pieza" : nombrePieza;
        var stepPath = Path.Combine(carpeta, $"{nombreBase}.step");
        var stlPath = Path.Combine(carpeta, $"{nombreBase}.stl");

        int errors = 0, warnings = 0;
        ext.SaveAs(stepPath, 0, (int)swSaveAsOptions_e.swSaveAsOptions_Silent, null!, ref errors, ref warnings);
        if (errors != 0)
            throw new InvalidOperationException($"SaveAs STEP fallo (codigo de error SOLIDWORKS {errors}).");

        ext.SaveAs(stlPath, 0, (int)swSaveAsOptions_e.swSaveAsOptions_Silent, null!, ref errors, ref warnings);
        if (errors != 0)
            throw new InvalidOperationException($"SaveAs STL fallo (codigo de error SOLIDWORKS {errors}).");

        var step = File.ReadAllBytes(stepPath);
        var stl = File.ReadAllBytes(stlPath);
        try { Directory.Delete(carpeta, recursive: true); } catch { /* best effort cleanup */ }
        return (step, stl);
    }
}
