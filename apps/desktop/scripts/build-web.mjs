// Compila apps/web con la URL del backend local horneada en el build (Vite
// hornea env vars en tiempo de compilacion, no de ejecucion - por eso esto
// no se puede resolver despues, dentro de Electron). Escrito en Node en vez
// de un script de shell para que funcione igual en Windows/Mac/Linux.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const aqui = path.dirname(fileURLToPath(import.meta.url));
const dirDesktop = path.join(aqui, "..");
const dirWeb = path.join(dirDesktop, "..", "web");
const dirDistWeb = path.join(dirWeb, "dist");
const dirDestino = path.join(dirDesktop, "resources", "web-dist");

// Mismo puerto fijo que apps/desktop/main.js (PUERTO_BACKEND) - si alguna
// vez cambia ahi, tiene que cambiar aqui tambien.
const env = { ...process.env, VITE_API_BASE_URL: "http://127.0.0.1:8731/api" };

function ejecutar(cmd, args, cwd) {
  const resultado = spawnSync(cmd, args, { cwd, env, stdio: "inherit", shell: process.platform === "win32" });
  if (resultado.status !== 0) {
    throw new Error(`Fallo "${cmd} ${args.join(" ")}" en ${cwd} (codigo ${resultado.status})`);
  }
}

if (!existsSync(path.join(dirWeb, "node_modules"))) {
  ejecutar("npm", ["install"], dirWeb);
}
ejecutar("npx", ["tsc", "-b"], dirWeb);
// --base ./ (en vez del default "/" que usa el deploy normal en Vercel):
// Electron carga index.html con win.loadFile(), es decir por file://, no
// por http://. Con base "/" los assets quedan referenciados como
// "/assets/x.js" - una ruta absoluta que file:// resuelve contra la RAIZ
// del sistema de archivos, no contra la carpeta de index.html, y todo
// carga en blanco (visto en vivo: "net::ERR_FILE_NOT_FOUND" en consola,
// <div id="root"> se queda vacio). Con base relativa los assets quedan
// como "./assets/x.js", que resuelve bien tanto por file:// como por
// http:// - por eso solo el build de escritorio pasa este flag, el
// deploy de Vercel (servido por http siempre) no lo necesita.
ejecutar("npx", ["vite", "build", "--base", "./"], dirWeb);

rmSync(dirDestino, { recursive: true, force: true });
mkdirSync(dirDestino, { recursive: true });
cpSync(dirDistWeb, dirDestino, { recursive: true });

console.log(`apps/web compilado con VITE_API_BASE_URL=${env.VITE_API_BASE_URL} -> ${dirDestino}`);
