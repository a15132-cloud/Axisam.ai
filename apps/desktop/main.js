// Proceso principal de Electron: arranca el backend real de Axiscam
// (apps/orchestrator, el mismo FastAPI + cadquery/OpenCascade que ya existe,
// sin cambios de logica) como proceso hijo LOCAL, espera a que responda, y
// abre una ventana que carga el build ya compilado de apps/web contra ese
// proceso local en vez de un servidor remoto - ver el plan en el README de
// esta carpeta para el porque completo.
"use strict";

const { app, BrowserWindow, dialog } = require("electron");
const path = require("node:path");
const http = require("node:http");
const { spawn, execSync } = require("node:child_process");

// Fijo a proposito: apps/web se compila para el escritorio con
// VITE_API_BASE_URL horneado a este mismo puerto (ver scripts/build-web.mjs
// y package.json) - no hay descubrimiento en tiempo de ejecucion porque Vite
// hornea env vars en build time, no runtime.
const PUERTO_BACKEND = 8731;
const URL_SALUD = `http://127.0.0.1:${PUERTO_BACKEND}/api/health`;
const TIMEOUT_ARRANQUE_MS = 60000;
const INTERVALO_SONDEO_MS = 400;

// URL del relay desplegado en Vercel (api/relay/[...path].js) - ver
// apps/relay/README.md. PLACEHOLDER: reemplaza esto por la URL real de TU
// proyecto de Vercel antes de generar un instalador de produccion (o
// exporta AXISCAM_RELAY_URL en el entorno del build - ver
// scripts/vendor-backend-windows.ps1 / package.json "dist:win").
const RELAY_URL_DEFAULT = "https://TU-PROYECTO.vercel.app/api/relay";

let procesoBackend = null;
let ventana = null;

function directorioDatosUsuario() {
  return path.join(app.getPath("userData"), "data");
}

function objetivoBackend() {
  if (!app.isPackaged) {
    // Desarrollo: corre el backend real del monorepo tal cual, con uv
    // (mismo comando que app/orchestrator/README.md documenta para dev).
    return {
      comando: process.platform === "win32" ? "uv.exe" : "uv",
      args: ["run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(PUERTO_BACKEND)],
      cwd: path.join(__dirname, "..", "orchestrator"),
    };
  }
  // Empaquetado: un Python portable + venv ya vendorizado por
  // scripts/vendor-backend-windows.ps1 (ver ese script y
  // electron-builder.yml -> extraResources) copiado dentro de
  // resources/backend en el instalador final.
  const base = path.join(process.resourcesPath, "backend");
  const ejecutable = process.platform === "win32" ? path.join(base, "python.exe") : path.join(base, "bin", "python3");
  return {
    comando: ejecutable,
    args: ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(PUERTO_BACKEND)],
    cwd: base,
  };
}

function lanzarBackend() {
  const objetivo = objetivoBackend();
  const env = {
    ...process.env,
    AXISCAM_STORAGE_DIR: directorioDatosUsuario(),
    // Key de relleno: el backend la necesita para construir el cliente del
    // SDK de Anthropic, pero el relay (api/relay/[...path].js) la
    // reemplaza por la key real antes de reenviar a Anthropic - esta jamas
    // se usa contra api.anthropic.com directamente. Ver
    // apps/relay/README.md para el porque completo.
    ANTHROPIC_API_KEY: "axiscam-desktop-usa-el-relay",
    ANTHROPIC_BASE_URL: process.env.AXISCAM_RELAY_URL || RELAY_URL_DEFAULT,
    AXISCAM_RELAY_CLIENT_HEADER: process.env.AXISCAM_RELAY_CLIENT_HEADER || "",
  };

  procesoBackend = spawn(objetivo.comando, objetivo.args, { cwd: objetivo.cwd, env });

  procesoBackend.stdout?.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  procesoBackend.stderr?.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  procesoBackend.on("error", (err) => {
    dialog.showErrorBox(
      "No se pudo arrancar el motor local de Axiscam",
      `No se pudo lanzar el proceso del backend (${objetivo.comando}): ${err.message}\n\n` +
        "Si acabas de instalar Axiscam, intenta reinstalarlo - puede que el antivirus haya bloqueado un archivo " +
        "durante la instalacion."
    );
    app.quit();
  });
}

function esperarSalud(timeoutRestanteMs) {
  return new Promise((resolve, reject) => {
    if (timeoutRestanteMs <= 0) {
      reject(new Error("El motor local de Axiscam no respondio a tiempo."));
      return;
    }
    const inicio = Date.now();
    const req = http.get(URL_SALUD, (res) => {
      res.resume();
      if (res.statusCode === 200) resolve();
      else setTimeout(() => esperarSalud(timeoutRestanteMs - (Date.now() - inicio) - INTERVALO_SONDEO_MS).then(resolve, reject), INTERVALO_SONDEO_MS);
    });
    req.on("error", () => {
      setTimeout(() => esperarSalud(timeoutRestanteMs - (Date.now() - inicio) - INTERVALO_SONDEO_MS).then(resolve, reject), INTERVALO_SONDEO_MS);
    });
  });
}

function crearVentana() {
  ventana = new BrowserWindow({
    width: 1400,
    height: 900,
    title: "Axiscam",
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });

  const indexHtml = app.isPackaged
    ? path.join(process.resourcesPath, "web-dist", "index.html")
    : path.join(__dirname, "..", "web", "dist", "index.html");
  ventana.loadFile(indexHtml);
}

function matarBackend() {
  if (!procesoBackend || procesoBackend.killed) return;
  if (process.platform === "win32") {
    // taskkill con /T mata todo el arbol de procesos - un simple .kill()
    // en Windows a veces deja huerfano el proceso real de python.exe
    // cuando el comando de arranque paso por un wrapper (uv.exe en dev).
    try {
      execSync(`taskkill /pid ${procesoBackend.pid} /T /F`);
    } catch {
      /* el proceso ya pudo haber terminado solo */
    }
  } else {
    procesoBackend.kill();
  }
}

app.whenReady().then(async () => {
  lanzarBackend();
  try {
    await esperarSalud(TIMEOUT_ARRANQUE_MS);
    crearVentana();
  } catch (err) {
    dialog.showErrorBox(
      "Axiscam no pudo arrancar",
      `${err.message}\n\nIntenta cerrar y volver a abrir Axiscam. Si el problema sigue, revisa que tu antivirus ` +
        "no este bloqueando el motor local."
    );
    matarBackend();
    app.quit();
  }
});

app.on("window-all-closed", () => {
  matarBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", matarBackend);
