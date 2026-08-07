#Requires -Version 5.1
<#
Builds all three AxiscamBridge projects in Release and assembles one
output folder (dist\) with everything AxiscamBridge.Api.exe needs to run,
including the SOLIDWORKS plugin DLL if it was built (PluginLoader looks
for it next to the API's own executable, not via a project reference -
see Services/PluginLoader.cs).

Usage:
  .\build.ps1
  .\build.ps1 -SolidWorksInteropPath "D:\SOLIDWORKS\api\redist"
#>

param(
    [string]$SolidWorksInteropPath = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dist = Join-Path $root "dist"

Write-Host "Axiscam Windows Bridge - build" -ForegroundColor Cyan

if (Test-Path $dist) {
    Remove-Item $dist -Recurse -Force
}
New-Item -ItemType Directory -Path $dist | Out-Null

$buildArgs = @("build", (Join-Path $root "AxiscamBridge.sln"), "-c", "Release")
if ($SolidWorksInteropPath -ne "") {
    $buildArgs += "-p:SolidWorksInteropPath=$SolidWorksInteropPath"
}

Write-Host "Running: dotnet $($buildArgs -join ' ')" -ForegroundColor DarkGray
& dotnet @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "dotnet build failed with exit code $LASTEXITCODE"
}

function Copy-ProjectOutput {
    param([string]$ProjectDir, [string]$Tfm)
    $outDir = Join-Path $root "src\$ProjectDir\bin\Release\$Tfm"
    if (Test-Path $outDir) {
        Copy-Item "$outDir\*" -Destination $dist -Recurse -Force
        Write-Host "Copied $ProjectDir ($Tfm) -> dist\" -ForegroundColor Green
    } else {
        Write-Host "Skipped $ProjectDir ($Tfm) - not found (expected on non-Windows builds)" -ForegroundColor Yellow
    }
}

Copy-ProjectOutput -ProjectDir "AxiscamBridge.Api" -Tfm "net8.0"
Copy-ProjectOutput -ProjectDir "AxiscamBridge.SolidWorks" -Tfm "net8.0-windows"
Copy-ProjectOutput -ProjectDir "AxiscamBridge.Mastercam" -Tfm "net8.0-windows"

Write-Host ""
Write-Host "Done. Run the bridge with:" -ForegroundColor Cyan
Write-Host "  cd dist; .\AxiscamBridge.Api.exe"
