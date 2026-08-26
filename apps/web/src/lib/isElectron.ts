// La app de escritorio (apps/desktop) carga este mismo build de apps/web
// dentro de una ventana de Electron - Electron agrega "Electron/<version>"
// al user agent por defecto, sin que main.js tenga que exponer nada extra
// via preload solo para esto. Cualquier otro visitante (el mismo build
// publicado en Vercel, abierto en un navegador normal) no lo trae.
export function esElectron(): boolean {
  return typeof navigator !== "undefined" && /Electron/i.test(navigator.userAgent);
}
