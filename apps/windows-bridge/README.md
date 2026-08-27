# Axiscam Windows Bridge

A small local HTTP service that lets Axiscam drive **real** SOLIDWORKS and
Mastercam on your own Windows machine, instead of the simulated
geometry/CAM engine the orchestrator uses by default everywhere else
(servers, containers, this dev sandbox - anywhere SOLIDWORKS/Mastercam
aren't installed).

It only listens on `127.0.0.1:5757` and is meant to run **alongside** the
Axiscam orchestrator, on the same Windows PC that has SOLIDWORKS/Mastercam
licensed and installed.

## How "connects automatically" actually works

There is no configuration step. The orchestrator's `generar_modelo_3d` and
`exportar_codigo_g` tools each make one short, best-effort HTTP call to
`http://127.0.0.1:5757` before falling back to the simulated engine (see
`apps/orchestrator/app/integrations/windows_bridge.py`):

- Nothing listening there (this bridge isn't running) → the call fails
  fast (0.3s connect timeout) and the orchestrator silently uses the
  simulated engine, exactly like today.
- This bridge running and SOLIDWORKS available → the orchestrator gets
  back a real STEP/STL model and marks the resulting files
  `es_simulacion: false` in the project (shown in the web UI as a "SolidWorks
  real" badge instead of "Motor simulado").
- This bridge running but the real call fails (a COM exception, a bad
  template path, etc.) → that error is surfaced to you as a real failure,
  never silently swallowed into a fake simulated result.

So: run the orchestrator wherever you want (your PC, a server), and run
this bridge on your Windows machine that actually has the software. As
soon as both are up, the very next model/G-code generation prefers the
real one. If the orchestrator runs on a *different* machine than the
bridge, point it at the bridge with `AXISCAM_WINDOWS_BRIDGE_URL` (see
below) - but on a single Windows shop-floor PC running both, the default
`127.0.0.1:5757` needs no configuration at all.

## Prerequisites

- **.NET 8 SDK** (Windows, x64) - https://dotnet.microsoft.com/download
- **SOLIDWORKS** installed, for the real modeling path. The connector uses
  SOLIDWORKS's COM automation API (`SldWorks.Application`), which has been
  stable across a wide range of versions.
- **Mastercam** installed, optional - see "Mastercam status" below before
  expecting real toolpaths/G-code from it.

## Building

```powershell
cd apps\windows-bridge
.\build.ps1
```

This builds all three projects in Release and copies everything into one
folder (`apps\windows-bridge\dist\`) so the optional SOLIDWORKS plugin DLL
sits next to the API host - `AxiscamBridge.Api` loads it via reflection at
startup (`Services/PluginLoader.cs`), so both must be in the same folder to
be found.

You can also build/run project by project with plain `dotnet build` /
`dotnet run --project src\AxiscamBridge.Api` while iterating - a
post-build step in each plugin project best-effort copies its own output
next to the API's `bin` folder too.

## Running

```powershell
cd apps\windows-bridge\dist
.\AxiscamBridge.Api.exe
```

Check `http://127.0.0.1:5757/health` in a browser - it should report
`solidworks_disponible: true` if SOLIDWORKS is installed and reachable.
Leave it running while you use Axiscam normally; the orchestrator finds it
automatically on the next model/G-code generation.

## Configuration

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `SolidWorksInteropPath` (MSBuild property, not an env var) | build time | `C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist` | Where to find `SolidWorks.Interop.*.dll`. Pass `-p:SolidWorksInteropPath=...` to `dotnet build`/`build.ps1` if your install is elsewhere. |
| `AXISCAM_SW_PART_TEMPLATE` | runtime, on the bridge machine | `C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\Part.prtdot` | Path to the `.prtdot` part template new models are created from. The service fails fast at startup with a clear message if this doesn't exist. |
| `AXISCAM_WINDOWS_BRIDGE_URL` | runtime, on the **orchestrator** machine | `http://127.0.0.1:5757` | Only needed if the orchestrator and this bridge run on different machines. |

If `SolidWorksInteropPath` doesn't point at real interop DLLs at build
time, `AxiscamBridge.SolidWorks` compiles to an empty library instead of
failing the build - `AxiscamBridge.Api` and the rest of Axiscam still work
normally, just without the real-SOLIDWORKS path. This is what makes
`dotnet build` succeed on this Linux dev sandbox with zero SOLIDWORKS
present, the same way it will on your Windows machine whether or not
SOLIDWORKS happens to be installed there.

## Honest status

This is a real, compiling, locally-verified .NET solution - not a mockup.
Here's exactly what's been checked and what hasn't, so you know what to
expect the first time you point it at your own SOLIDWORKS/Mastercam:

**`AxiscamBridge.Api`** - verified. Builds and runs in this sandbox;
`/health`, `/solidworks/generar-modelo` (503 path), and
`/mastercam/generar-codigo-g` (503 path) were exercised directly and
behave as documented. `/solidworks/activar` (the "Ver en SolidWorks"
button in the chat, still part of the product today) compiles cleanly
the same way, but only its unavailable/unreachable path has actually
been exercised here. `/mastercam/abrir` also compiles and exists in this
Api project, but Axiscam's product scope is CAD-only now (see the main
README's "Por qué Axiscam no genera código G") - there is no "Abrir en
Mastercam" button in the chat anymore, so this endpoint isn't called by
anything in the current frontend; it would need to be wired up again if
CAM is ever re-exposed. See the two entries below for what's unverified
in each service.

**`AxiscamBridge.SolidWorks`** - written with real confidence, **not yet
run against real SOLIDWORKS**. No sandbox used to build this had
SOLIDWORKS installed, so `SolidWorksService.cs` has never actually driven
a live SOLIDWORKS instance. It's written against long-stable, documented
API members (`FeatureExtrusion2`, `FeatureCut4`, `NewDocument`,
`SaveAs`) with the one most common real-world bug (SOLIDWORKS API lengths
are always in **meters**, regardless of document display units) handled
in exactly one place (`MmToM`). Current scope: rectangular/circular base
extrusion, through-hole barrenos on the top face, STEP/STL export. Blind
holes, cajeras, fillets/chamfers, and lateral faces are not implemented
yet - if you hit one of these, the response's `features_omitidos` will
say so explicitly rather than silently skipping it. If a specific COM
call throws an argument-count/type exception on your SOLIDWORKS version,
that method's exact overload (SOLIDWORKS has added
`FeatureExtrusion3/4` etc. over the years without removing the old ones)
is the first thing to check.

Cross-checked every COM call in this file against real published
SOLIDWORKS macro examples (not just API help pages, several of which
wouldn't render for automated fetching) and found and fixed one genuine
bug in the process: `FeatureCut4` (used for the through-hole barrenos)
was called with 25 arguments where the real signature needs 27 - it was
missing `AssemblyFeatureScope` and `AutoSelectComponents`. Against the
real interop assembly this would have failed to compile outright (wrong
argument count), not produced a wrong cut silently - still worth fixing
before anyone hits it. `FeatureExtrusion2` (23 args) and `SaveAs`'s
`ref errors, ref warnings` marshaling were both independently confirmed
correct as originally written against real code examples, not just
inferred from memory.

The model is also no longer closed after generation, and
`ActivarUltimoModeloAsync` (behind `/solidworks/activar`, "Ver en
SolidWorks" in the chat) re-activates it and brings the SOLIDWORKS window
to the front via `ActivateDoc3` + a Win32 `SetForegroundWindow` on the
`SLDWORKS` process. **This method has never run against a real SOLIDWORKS
install either** - `SolidWorksService.cs` isn't even compiled in this
sandbox (see `AxiscamBridge.SolidWorks.csproj`: the whole file is excluded
from the build tree when the interop DLLs aren't found), so this isn't
"written with confidence" the way the rest of the class is, it's a first
draft against documented API shape only. If `ActivateDoc3` throws on your
version, same move as above: check its exact overload in your installed
SOLIDWORKS's API help.

**`AxiscamBridge.Mastercam`** - deliberately scoped to detection-only.
Mastercam does not expose one stable, universally-documented external
automation object the way SOLIDWORKS does (`SldWorks.Application`) -
its primary automation surface is **NET-Hooks**, C# plugin DLLs that
Mastercam *loads into itself* and runs from its own UI/ribbon, not
something an external process calls over HTTP the way this bridge calls
SOLIDWORKS. What counts as "the API" also genuinely differs across
Mastercam versions in a way SOLIDWORKS mostly avoids. So
`MastercamService.cs` does only the part that's real and
version-independent - detecting whether Mastercam is installed and which
version, via the filesystem - and `EstaDisponible` is hard-coded `false`
even when Mastercam is found, because full "Pieza JSON in, verified
G-code out" automation genuinely isn't implemented. Calling
`generar-codigo-g` against a machine with Mastercam installed returns a
clear 503 explaining exactly that, plus a pointer to import the STEP file
manually in the meantime - never a fabricated response.

`AbrirStepAsync` (behind `/mastercam/abrir`, "Abrir en Mastercam" in the
chat) is real and does compile in this sandbox (unlike the SOLIDWORKS
project, this one has no interop-DLL gate), but the specific move of
passing the STEP path as `mastercam.exe`'s first argument to open it
automatically is an assumption based on standard Windows GUI app
convention, **not a confirmed Mastercam command-line contract for any
version**. If it doesn't load the file, Mastercam still launches and the
user imports the STEP manually - it never blocks or fails on that guess
being wrong. This button intentionally does not imply Mastercam "did"
anything, the way "Ver en SolidWorks" does.

### Completing the Mastercam connector

To finish this for real: write a Mastercam Net-Hook (a C# class library
targeting your installed Mastercam version's NET-Hook SDK, typically
found under `<Mastercam install>\hooks` or via Mastercam's own SDK
download) that accepts a `Pieza`-shaped payload, drives Mastercam's own
API to build toolpaths and post G-code, and writes the result somewhere
this bridge can read it back from (a temp file handoff is simplest,
since NET-Hooks run inside Mastercam's process, not this one).
`MastercamService.GenerarCodigoGAsync` is the one place to wire that
hand-off into once it exists.

## Security

`AxiscamBridge.Api` binds to `127.0.0.1` only, never `0.0.0.0` - it drives
licensed CAD/CAM software with real filesystem and COM access on your
machine, so it must never be reachable from anything other than the
orchestrator running on the same machine (see the comment next to
`app.Run(...)` in `Program.cs`).
