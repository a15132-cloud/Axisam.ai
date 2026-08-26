// Relay minimo y sin estado entre la app de escritorio de Axiscam y la API
// real de Anthropic. Vive aqui (Vercel Edge Function, en el mismo proyecto
// que ya sirve apps/web) para no depender de una cuenta/pago nuevo - un
// cold start de funcion serverless/edge es sub-segundo, nada que ver con el
// spin-down de varias decenas de segundos de un servicio de computo siempre
// encendido como el que Axiscam usaba en Render.
//
// Por que existe: la app de escritorio (apps/desktop) sigue usando UNA sola
// API key de Anthropic pagada por el operador de Axiscam (los usuarios
// finales nunca ven ni configuran una key propia). Esa key NUNCA viaja
// dentro del instalador que se descarga - cualquier valor embebido en un
// binario publico es extraible con esfuerzo suficiente. En vez de eso, el
// backend local (apps/orchestrator) apunta su SDK de Anthropic aqui
// (ANTHROPIC_BASE_URL) con una key de relleno, y este endpoint es el unico
// lugar que conoce la key real - guardada como variable de entorno secreta
// de Vercel, nunca en el repo.
//
// Que SI hace: reenviar el metodo/body/headers tal cual a
// https://api.anthropic.com<mismo-path>, reemplazando x-api-key por la key
// real, y devolver la respuesta (incluyendo streaming SSE) sin tocarla. El
// SDK de Anthropic arma internamente rutas como "/v1/messages" sobre el
// base_url configurado - el "[...path]" de este archivo es justamente lo
// que hace que /api/relay/v1/messages (lo que el SDK termina pidiendo si
// ANTHROPIC_BASE_URL=".../api/relay") llegue aqui sin tener que declarar
// cada ruta de la API una por una.
//
// Que NO hace (limitacion conocida, ver apps/desktop/README.md): el header
// AXISCAM_RELAY_CLIENT_HEADER de abajo es una disuasion superficial, no
// seguridad real - tambien es extraible del instalador. La proteccion de
// fondo real sigue siendo la misma que ya recomienda el README principal
// para el modelo de key compartida: fija un limite de gasto mensual en
// https://console.anthropic.com/settings/limits.
export const config = { runtime: "edge" };

const ANTHROPIC_API_ORIGIN = "https://api.anthropic.com";
const PREFIJO_RELAY = "/api/relay";

export default async function handler(req) {
  const keyReal = process.env.ANTHROPIC_API_KEY;
  if (!keyReal) {
    return new Response(
      JSON.stringify({ error: "Relay no configurado: falta ANTHROPIC_API_KEY como variable de entorno en Vercel." }),
      { status: 500, headers: { "content-type": "application/json" } }
    );
  }

  // Disuasion superficial (ver docstring arriba) - si esta variable esta
  // configurada en Vercel, exige que la peticion traiga el mismo header
  // fijo que apps/desktop embebe en su build. Si no esta configurada, el
  // relay queda abierto a quien tenga la URL (aceptable solo mientras se
  // confirma el limite de gasto en la consola de Anthropic).
  const clienteEsperado = process.env.AXISCAM_RELAY_CLIENT_HEADER;
  if (clienteEsperado && req.headers.get("x-axiscam-client") !== clienteEsperado) {
    return new Response(JSON.stringify({ error: "No autorizado." }), {
      status: 401,
      headers: { "content-type": "application/json" },
    });
  }

  const url = new URL(req.url);
  const pathDestino = url.pathname.startsWith(PREFIJO_RELAY) ? url.pathname.slice(PREFIJO_RELAY.length) : url.pathname;
  const urlDestino = ANTHROPIC_API_ORIGIN + pathDestino + url.search;

  const headers = new Headers(req.headers);
  headers.set("x-api-key", keyReal);
  headers.delete("x-axiscam-client");
  headers.delete("host");

  const sinCuerpo = req.method === "GET" || req.method === "HEAD";
  const respuesta = await fetch(urlDestino, {
    method: req.method,
    headers,
    body: sinCuerpo ? undefined : req.body,
    // Requerido por el runtime cuando el body de la peticion es un stream.
    duplex: sinCuerpo ? undefined : "half",
  });

  const headersRespuesta = new Headers(respuesta.headers);
  // El body ya viene descomprimido por el fetch interno del runtime - dejar
  // este header tal cual confundiria al cliente sobre la codificacion real.
  headersRespuesta.delete("content-encoding");

  return new Response(respuesta.body, { status: respuesta.status, headers: headersRespuesta });
}
