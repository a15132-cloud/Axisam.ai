# Relay de Anthropic (para la app de escritorio)

Este "proyecto" no tiene código propio - el código real vive en
`/api/relay/[...path].js` en la raíz del repo, porque así es como Vercel
descubre funciones serverless/Edge (tienen que estar bajo `/api` en la raíz
del proyecto, no importa que el resto del sitio se compile desde
`apps/web`). Esta carpeta solo documenta qué es, por qué existe, y cómo
desplegarlo - ver el docstring completo en ese archivo para el detalle
técnico del reenvío.

## Por qué existe

La app de escritorio (`apps/desktop`) sigue usando una sola API key de
Anthropic pagada por ti - a nadie que descargue Axiscam se le pide su propia
key. El problema: un instalador que la gente descarga es un binario público,
y cualquier valor incrustado ahí (incluida una API key) se puede extraer con
esfuerzo suficiente. Este relay es la solución: la key real nunca sale de
Vercel. El backend local de cada usuario llama a este endpoint (no a
`api.anthropic.com` directo), y solo este endpoint conoce la key real.

Vive en el **mismo proyecto de Vercel que ya usan para `apps/web`** - cero
cuenta nueva, cero costo nuevo. Un cold start de función Edge es
sub-segundo; no tiene nada que ver con el spin-down de decenas de segundos
que causaba los errores en Render.

## Desplegar

1. En el dashboard de tu proyecto de Vercel (el mismo de `apps/web`) →
   **Settings → Environment Variables**, agrega:
   - `ANTHROPIC_API_KEY` = tu key real de
     https://console.anthropic.com/settings/keys (marcada como *secreta* -
     nunca la pongas en el repo ni en `apps/desktop`).
   - `AXISCAM_RELAY_CLIENT_HEADER` (opcional pero recomendado) = cualquier
     cadena que tú elijas, p. ej. un UUID generado una vez. Es una
     disuasión superficial contra quien encuentre la URL del relay por
     curiosidad - no seguridad real (ver la limitación abajo) - así que
     tiene que coincidir con el mismo valor que `apps/desktop` embebe en su
     build (ver `apps/desktop/README.md`).
2. Redeploy el proyecto (las variables de entorno solo aplican al build
   siguiente).
3. La URL del relay queda en
   `https://<tu-proyecto>.vercel.app/api/relay` - eso es lo que
   `apps/desktop` pasa como `ANTHROPIC_BASE_URL` al backend local.

## Probarlo

```bash
curl -s https://<tu-proyecto>.vercel.app/api/relay/v1/messages \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-axiscam-client: <el mismo valor de AXISCAM_RELAY_CLIENT_HEADER>" \
  -d '{"model":"claude-sonnet-5","max_tokens":16,"messages":[{"role":"user","content":"di hola"}]}'
```

Una respuesta JSON real de Claude confirma que el relay reenvía
correctamente. Un 401 significa que falta o no coincide el header
`x-axiscam-client`; un 500 significa que `ANTHROPIC_API_KEY` no está
configurada en Vercel.

## Limitación conocida (léela antes de confiar en esto como "seguro")

El header `x-axiscam-client` disuade a quien encuentre la URL por
casualidad, pero no a alguien decidido a extraerlo del instalador - eso es
cierto de cualquier valor embebido en un binario público, con o sin relay.
La protección de fondo real, igual que ya recomienda el README principal
para el modelo de key compartida de hoy, es fijar un **límite de gasto
mensual** en https://console.anthropic.com/settings/limits. Este relay
cambia QUÉ se expone si algo sale mal (una key de relleno inútil por sí
sola, revocable/rotable sin tocar la key real) - no elimina la necesidad de
ese límite.
