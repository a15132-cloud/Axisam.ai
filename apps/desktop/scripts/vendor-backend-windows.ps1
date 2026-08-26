# Empaqueta apps/orchestrator (el backend real: FastAPI + cadquery/OpenCascade)
# junto con un Python portable en apps/desktop/resources/backend, listo para
# que electron-builder lo copie dentro del instalador (ver
# apps/desktop/package.json -> build.extraResources).
#
# Por que un Python portable "vendorizado" en vez de congelar el backend con
# PyInstaller: cadquery-ocp es una extension nativa enorme (bindings de
# OpenCascade) - el analisis estatico de imports que hace PyInstaller para
# decidir que empaquetar tiene reportes conocidos de perder simbolos de
# extensiones nativas asi de grandes. Copiar un interprete completo + su
# venv entero (sin "adivinar" que archivos hacen falta) es mas simple y mas
# seguro para justo este caso, a costa de un instalador mas pesado.
#
# ADVERTENCIA HONESTA (ver el plan/README de apps/desktop): este script se
# escribio y se revisó con cuidado, pero solo se puede EJECUTAR Y VALIDAR de
# verdad en Windows (requiere powershell.exe + el instalador de python.org) -
# este repo se preparó desde un sandbox Linux que no tiene Windows disponible,
# asi que no se pudo correr de punta a punta aqui. Si algo falla, corre este
# script a mano en una PC Windows y copia el error exacto.

$ErrorActionPreference = "Stop"

$AQUI = Split-Path -Parent $MyInvocation.MyCommand.Path
$DIR_DESKTOP = Resolve-Path (Join-Path $AQUI "..")
$DIR_ORCHESTRATOR = Resolve-Path (Join-Path $DIR_DESKTOP "../orchestrator")
$DIR_DESTINO = Join-Path $DIR_DESKTOP "resources/backend"
$PYTHON_VERSION = "3.11.9"
$PYTHON_ZIP_URL = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-embed-amd64.zip"
$GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

Write-Host "1/5 - Limpiando $DIR_DESTINO"
if (Test-Path $DIR_DESTINO) { Remove-Item -Recurse -Force $DIR_DESTINO }
New-Item -ItemType Directory -Force -Path $DIR_DESTINO | Out-Null

Write-Host "2/5 - Descargando Python $PYTHON_VERSION embebido"
$zipPath = Join-Path $env:TEMP "python-embed.zip"
Invoke-WebRequest -Uri $PYTHON_ZIP_URL -OutFile $zipPath
Expand-Archive -Path $zipPath -DestinationPath $DIR_DESTINO -Force

# La distribucion "embebida" trae pip/site-packages deshabilitados por
# defecto via un ._pth que restringe el sys.path - hay que habilitarlos
# para poder instalar cadquery y sus dependencias dentro de esta misma
# carpeta portable.
$pthFile = Get-ChildItem -Path $DIR_DESTINO -Filter "python*._pth" | Select-Object -First 1
(Get-Content $pthFile.FullName) -replace '^#import site', 'import site' | Set-Content $pthFile.FullName

Write-Host "3/5 - Instalando pip"
$getPipPath = Join-Path $env:TEMP "get-pip.py"
Invoke-WebRequest -Uri $GET_PIP_URL -OutFile $getPipPath
& "$DIR_DESTINO/python.exe" $getPipPath --no-warn-script-location

Write-Host "4/5 - Exportando dependencias desde uv.lock e instalandolas en el Python portable"
Push-Location $DIR_ORCHESTRATOR
try {
    # uv export produce un requirements.txt real (con hashes) a partir del
    # mismo uv.lock que ya fija las versiones para dev/CI - una sola fuente
    # de verdad para las dependencias, en vez de mantener una lista aparte
    # a mano para el empaquetado de escritorio.
    uv export --no-dev --frozen --format requirements-txt -o requirements.desktop.txt
    & "$DIR_DESTINO/python.exe" -m pip install --no-warn-script-location -r requirements.desktop.txt
    Remove-Item requirements.desktop.txt
} finally {
    Pop-Location
}

Write-Host "5/5 - Copiando el codigo fuente del backend (app/)"
Copy-Item -Recurse -Force (Join-Path $DIR_ORCHESTRATOR "app") (Join-Path $DIR_DESTINO "app")

Write-Host "Listo: $DIR_DESTINO contiene un Python portable con Axiscam listo para correr como 'python.exe -m uvicorn app.main:app'."
