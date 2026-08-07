using System.Reflection;
using Microsoft.Extensions.Logging;

namespace AxiscamBridge.Api.Services;

/// Loads the real SolidWorks/Mastercam connectors as optional plugins via
/// reflection instead of a compile-time project reference. That's what
/// makes "conecta facil" true in practice: this Api project has zero
/// compile-time dependency on the SolidWorks/Mastercam interop assemblies
/// (which don't exist unless those programs are installed), so it builds
/// and runs identically on every machine. Whether a real connection is
/// available is decided once, at startup, by whether the sibling DLL is
/// present and loads cleanly - never a reason for the bridge itself to
/// crash or refuse to start.
public static class PluginLoader
{
    public static ISolidWorksService CargarSolidWorks(ILogger logger) =>
        Cargar<ISolidWorksService>(
            "AxiscamBridge.SolidWorks.dll",
            "AxiscamBridge.SolidWorks.SolidWorksService",
            logger,
            razon => new UnavailableSolidWorksService(razon));

    public static IMastercamService CargarMastercam(ILogger logger) =>
        Cargar<IMastercamService>(
            "AxiscamBridge.Mastercam.dll",
            "AxiscamBridge.Mastercam.MastercamService",
            logger,
            razon => new UnavailableMastercamService(razon));

    private static T Cargar<T>(string dllName, string typeName, ILogger logger, Func<string, T> crearFallback)
        where T : class
    {
        var ruta = Path.Combine(AppContext.BaseDirectory, dllName);
        if (!File.Exists(ruta))
        {
            logger.LogInformation("{Dll} no encontrado en {Ruta} - modo no disponible.", dllName, ruta);
            return crearFallback("plugin no encontrado (no se compilo en este equipo)");
        }

        try
        {
            var assembly = Assembly.LoadFrom(ruta);
            var tipo = assembly.GetType(typeName)
                ?? throw new InvalidOperationException($"El ensamblado {dllName} no contiene el tipo {typeName}");
            var instancia = Activator.CreateInstance(tipo) as T
                ?? throw new InvalidOperationException($"{typeName} no implementa {typeof(T).Name}");
            logger.LogInformation("{Dll} cargado correctamente.", dllName);
            return instancia;
        }
        catch (Exception ex)
        {
            // Deliberately broad: COM registration errors, missing native
            // dependencies, a SolidWorks/Mastercam version the interop
            // assemblies don't match, etc. all land here - none of them
            // should crash the bridge, they should just mean "not
            // available right now, fall back to simulation."
            logger.LogWarning(ex, "No se pudo cargar {Dll} - modo no disponible.", dllName);
            return crearFallback($"error al cargar el plugin: {ex.Message}");
        }
    }
}
