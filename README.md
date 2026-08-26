# Axiscam

Agente de IA que orquesta el flujo de diseño CAD (SolidWorks) y manufactura CAM (Mastercam)
de un taller: un usuario sube el plano de una pieza en un chat, el agente extrae las medidas,
genera el modelo 3D, planea las trayectorias de maquinado y exporta el código G — con
aprobación humana obligatoria en tres puntos antes de que nada llegue a una máquina real.

## Qué es real hoy y qué es simulación

Este entorno de desarrollo es Linux y no tiene SolidWorks ni Mastercam instalados (ambos solo
corren en Windows con licencia activa vía COM/SDK). Para no bloquear todo el proyecto en esa
infraestructura, el sistema está dividido así:

| Capa | Estado en este repo |
|---|---|
| Capa 1 — Chat / UI | **Real y funcional** (React) |
| Capa 2 — Orquestador (loop de tool-use con Claude) | **Real y funcional** (FastAPI + Anthropic SDK) |
| Capa 3 — Visión / extracción del plano | **Real y funcional** (Claude multimodal), requiere `ANTHROPIC_API_KEY` |
| Capa 4 — SolidWorks (modelado 3D) | **Geometría real por defecto**, generada con un kernel OpenCascade (`cadquery`) — produce archivos STEP/STL reales, abribles en SolidWorks hoy mismo. **SolidWorks real cuando está disponible**: si `apps/windows-bridge` corre en tu propia PC con Windows con SolidWorks instalado, el orquestador lo detecta y prefiere automáticamente su salida en vez del motor simulado (ver más abajo). |
| Capa 4 — Mastercam (trayectorias / código G) | **Simulación basada en reglas**, claramente etiquetada como tal. Genera trayectoria de corte real para taladrado (G81/G83), cajeras (desbaste en zigzag con radio de herramienta compensado) y contornos exteriores/redondeos (offset con esquinas correctamente redondeadas) — no solo taladros. Sigue sin chequeo de colisiones entre features simultáneos, sin rampas de entrada, y features sin suficiente geometría en el JSON (p.ej. escalón) quedan como planeación sin trayectoria. **Ningún código G de este sistema debe cargarse a una máquina sin que Mastercam real lo verifique.** El conector de Mastercam real en `apps/windows-bridge` existe pero es honesto sobre su alcance: detecta la instalación, no automatiza todavía (ver `apps/windows-bridge/README.md`). |
| Capa 5 — Base de conocimiento de manufactura | **Real**, tabla de decisión explícita (YAML + Python), datos semilla pendientes de validar por un maquinista |
| Capa 6 — Aprobación humana | **Real y aplicado en el backend** — cada transición de aprobación es un endpoint dedicado que ningún tool-call del LLM puede invocar por su cuenta |

## Conectar tu SolidWorks/Mastercam real (`apps/windows-bridge`)

Este repo también incluye un servicio .NET opcional (`apps/windows-bridge`) que, corriendo en
tu propia PC con Windows con SolidWorks/Mastercam instalados, hace que Axiscam use el software
real en vez del motor simulado — sin configuración manual. El orquestador intenta conectarse a
`http://127.0.0.1:5757` en cada generación de modelo/código G con un timeout corto; si no hay
nada ahí (el caso normal en este sandbox, en un servidor, o en cualquier máquina sin SolidWorks),
sigue usando el motor simulado exactamente como hoy. Si el bridge está corriendo, la interfaz
muestra un indicador ("SolidWorks real" / "Motor simulado") en cada modelo y código G generado,
y en el pie del menú lateral. Ver `apps/windows-bridge/README.md` para instalación, alcance real
verificado, y cómo terminar el conector de Mastercam.

## Estructura

```
apps/
  desktop/        App de escritorio (Electron) - la forma principal de correr Axiscam hoy,
                  ver apps/desktop/README.md
  orchestrator/   Backend Python (FastAPI) - Capas 2, 3, 4, 5, 6 - el mismo proceso corre
                  local (dentro de apps/desktop) o remoto (modo avanzado/web)
  web/            Frontend React - Capa 1
  windows-bridge/ Servicio .NET opcional - conecta la Capa 4 a SolidWorks/Mastercam reales
                  en la PC Windows del usuario (ver apps/windows-bridge/README.md)
api/
  relay/          Función Edge de Vercel que oculta la API key real de Anthropic detrás de
                  la app de escritorio - ver apps/relay/README.md
docs/
  architecture.md Detalle técnico de cada capa y el plan de migración a SolidWorks/Mastercam reales
```

## Correr en desarrollo

### Backend

```bash
cd apps/orchestrator
cp .env.example .env   # agrega tu ANTHROPIC_API_KEY
uv sync --group dev
uv run uvicorn app.main:app --reload --port 8001
```

### Frontend

```bash
cd apps/web
npm install
npm run dev   # http://localhost:5173, con proxy a /api -> localhost:8001
```

### Tests (backend)

```bash
cd apps/orchestrator
uv run pytest
```

## Flujo de uso

1. Crear un proyecto, subir el plano (PDF/imagen/DXF) con instrucciones opcionales en texto.
2. Revisar y **confirmar** los datos extraídos (medidas, material, features) — checkpoint 1.
3. El sistema genera el modelo 3D real (STEP + STL descargables) y lo muestra en una vista 3D.
   **Confirmar** el modelo — checkpoint 2.
4. El sistema planea trayectorias y muestra una simulación estimada (tiempo, herramientas,
   velocidades/avances). Un usuario con nombre/usuario da la **aprobación final** — checkpoint 3.
5. Solo entonces se exporta el código G (marcado como simulación pendiente de verificación).
6. En cualquier momento a partir del modelo 3D, el botón **"Descargar todo (.zip)"** entrega
   STEP + STL + código G (si existe) + un reporte de resumen en un solo archivo.

La interfaz es responsiva: en celular, el menú de proyectos se abre como panel deslizable y el
panel de plano/vista 3D/actividad se accede con una pestaña "Detalles" junto al chat.

## Descargar Axiscam (app de escritorio)

Esta es la forma principal de usar Axiscam hoy: **no hay servidor remoto del
que depender**. La gente entra a la página de descargas, instala Axiscam, y
listo - el modelado 3D (`cadquery`/OpenCascade generando STEP/STL real),
el guardado de proyectos, y la simulación de trayectorias corren
**100% localmente** en su propia compu. Lo único que sigue saliendo a
internet es la llamada a Claude (leer un plano, chatear) - y esa pasa por
un relay mínimo que oculta la key real, nunca directo con una key embebida
en el instalador (ver `apps/relay/README.md` para el porqué).

Este cambio existe porque la versión anterior (frontend en Vercel + backend
en Render) causaba justo el error que probablemente te trajo a leer esto:
"no se pudo contactar al servidor" o "la petición se cortó a medio camino"
cada vez que Render reiniciaba el servicio - un servidor que puede estar
dormido o redesplegando en cualquier momento es un punto de falla que una
app de escritorio simplemente no tiene.

- **Construir el instalador de Windows**: ver `apps/desktop/README.md`
  (`cd apps/desktop && npm install && npm run dist:win`). También hay un
  workflow de CI (`.github/workflows/build-desktop.yml`) que produce el
  mismo instalador en `windows-latest` sin necesitar una PC Windows a la
  mano.
- **Correrlo en modo desarrollo**: `cd apps/desktop && npm install && npm start`
  arranca el backend real y abre la ventana, sin necesidad de empaquetar nada.
- **Limitaciones conocidas de esta primera versión** (léelas antes de
  repartir el instalador a alguien): están documentadas sin rodeos en
  `apps/desktop/README.md` - el riesgo más grande es que el empaquetado con
  `cadquery`/OpenCascade en un Python portable de Windows se escribió con
  cuidado pero no se pudo validar de punta a punta en una PC Windows real
  desde este entorno de desarrollo.
- Mac/Linux están declarados como targets de empaquetado pero **no
  probados todavía** - el script de vendorizado del backend por ahora solo
  existe para Windows (la plataforma que se pidió como prioridad).

### Modo avanzado: correr Axiscam como app web (opcional)

Si en cambio quieres seguir auto-hospedando Axiscam como una app web
tradicional (frontend + backend cada uno en su propio servicio), eso sigue
siendo posible - queda documentado aquí como alternativa, no como el camino
principal.

Este es un monorepo de **dos servicios independientes que deben desplegarse por separado** — este
es el paso que causa el banner rojo "No se pudo conectar con el backend" si solo desplegaste uno
de los dos. Vercel solo puede alojar el primero:

| Servicio | Dónde | Qué hace |
|---|---|---|
| `apps/web` (frontend) | Vercel | La interfaz de chat que ves en el navegador |
| `apps/orchestrator` (backend) | Render, Railway, Fly.io u otro host de contenedores | El trabajo real: llama a Claude, genera geometría, código G, etc. |

**Si el backend nunca se desplegó, el frontend en Vercel no tiene con quién hablar — por eso
aparece "no se pudo conectar", aunque el frontend cargue perfectamente.** No es un bug del
código: son dos despliegues separados y ambos son necesarios.

Por qué el backend no puede vivir también en Vercel: sus funciones serverless no soportan un
proceso de larga duración con un motor de geometría 3D pesado (`cadquery`/OpenCascade, cientos de
MB de librerías nativas - muy por encima del límite de tamaño de una función de Vercel) ni guardar
archivos de forma permanente (los planos y STEP/STL/G-code generados). No es una limitación de
configuración que se pueda ajustar - es el mismo motivo por el que ningún producto de IA serio
corre su backend completo solo en funciones serverless. **Y esto es completamente invisible para
tus clientes**: ellos solo entran a tu link de Vercel y usan la app normal - nunca ven, ni les
importa, que el trabajo pesado ocurre en un segundo servicio detrás.

> Nota: `render.yaml` sigue en el repo y funciona, pero quedó como una opción entre varias - no es
> el despliegue recomendado por defecto. Si el spin-down/redeploy de un servicio siempre encendido
> te sigue causando el banner rojo de arriba, la app de escritorio (sección anterior) elimina ese
> problema de raíz en vez de solo cambiar de proveedor.

#### Paso 1 — Backend en Render (el que probablemente falta)

1. En https://dashboard.render.com → **New +** → **Blueprint** → conecta este repositorio de
   GitHub y selecciona la rama con este código. Render detecta `render.yaml` en la raíz del repo
   automáticamente y configura el servicio (usa el `Dockerfile` de `apps/orchestrator/`).
2. Render te pedirá dos valores antes de desplegar:
   - `ANTHROPIC_API_KEY` — tu clave de https://console.anthropic.com/settings/keys. Esta es la
     **única** key que existe en todo el sistema — tus clientes jamás la ven ni tienen que
     configurar nada, igual que en Perplexity, Grok o ChatGPT (ellos tampoco te piden una API key;
     la empresa la paga por detrás). Ver la sección "Evitar quedarte sin créditos sin avisar" más
     abajo antes de desplegar.
   - `AXISCAM_CORS_ORIGINS` — la URL de tu frontend en Vercel, por ejemplo
     `https://tu-proyecto.vercel.app` (sin `/` al final). Si no coincide exactamente con tu
     dominio de Vercel, el navegador bloquea las llamadas y verás el mismo banner rojo aunque el
     backend sí esté corriendo.
3. Cuando termine el deploy, copia la URL pública que te da Render (algo como
   `https://axiscam-orchestrator.onrender.com`).

#### Paso 2 — Apuntar Vercel a ese backend

1. En el dashboard de tu proyecto en Vercel → **Settings** → **Environment Variables**.
2. Agrega `VITE_API_BASE_URL` = la URL de Render del paso anterior + `/api`, por ejemplo
   `https://axiscam-orchestrator.onrender.com/api`.
3. **Redeploy** el proyecto en Vercel (las variables de entorno solo aplican en el próximo build,
   no retroactivamente a un deploy que ya existe).

Con eso el banner rojo debe desaparecer. Alternativas a Render con el mismo `Dockerfile`:
Railway o Fly.io — ambos soportan "deploy from Dockerfile" desde el repo de GitHub, si prefieres
alguno de esos en vez del blueprint de Render.

> Nota honesta: escribí y revisé el `Dockerfile` y el `render.yaml` con cuidado, pero este
> sandbox no tiene acceso a una cuenta de Render ni un daemon de Docker corriendo, así que no
> pude ejecutar el despliegue de punta a punta yo mismo para confirmarlo. Si algo falla al
> desplegar (típicamente un paquete de sistema faltante para las librerías nativas de
> `cadquery`, o un typo en la clave de Render Blueprints como `runtime: docker`), copia el error
> exacto del log de Render y lo corrijo.

## Una sola API key, invisible para tus clientes

Axiscam necesita a Claude (Anthropic) para el chat y la lectura de planos — no hay forma honesta
de tener un agente de IA real sin una API key real conectándolo a un modelo real (ningún producto
de IA escapa a esto, incluidos Perplexity, Grok o ChatGPT). Lo que sí es una decisión de diseño:
**quién carga con esa key**. Axiscam usa una sola `ANTHROPIC_API_KEY` tuya — tus clientes nunca ven
ni configuran nada relacionado con IA, exactamente como en cualquier producto de IA orientado a
consumidor. Dónde vive esa key depende del modo:

- **App de escritorio** (la forma principal, ver arriba): la key real vive solo en el relay
  (`api/relay/[...path].js`, desplegado en Vercel) - nunca dentro del instalador que la gente
  descarga. Ver `apps/relay/README.md` para el detalle completo y su limitación conocida.
- **Modo avanzado (app web)**: la key vive directo en el backend (Render u otro host).

Si esa key llega a fallar (vencida, sin créditos, límite de uso alcanzado), el cliente ve un
mensaje profesional y genérico en el chat en vez de un error técnico — el detalle real queda solo
en el registro de actividad del proyecto, para que tú lo diagnostiques.

### Evitar quedarte sin créditos sin avisar

Es pago por uso (no hay una versión "que no se acaba" — ningún proveedor de IA real la tiene,
incluido el que usan Perplexity/Grok por detrás), pero sí puedes evitar sorpresas de facturación:

1. En https://console.anthropic.com, ve a **Settings → Limits** y configura un **límite de gasto
   mensual** (spending limit). Al llegar a ese límite, la API simplemente deja de responder en vez
   de seguir cobrando — Axiscam ya maneja ese caso mostrando el mensaje profesional mencionado
   arriba en vez de un error técnico.
2. Activa las **alertas de uso por correo** en la misma sección, para enterarte antes de llegar al
   límite, no cuando ya se cortó el servicio.
3. Una conversación típica de Axiscam (unos mensajes + extraer un plano) cuesta centavos de dólar,
   no dólares — para calibrar cuánto poner de límite mensual según cuántos proyectos esperas
   procesar.

### Muchos clientes usando Axiscam al mismo tiempo

Con una sola key compartida entre todos tus clientes (arriba), la pregunta real es si esa key
aguanta que varios estén chateando a la vez sin que ninguno vea un error - esto está resuelto en
dos niveles:

1. **Reintentos automáticos.** Cada llamada a Claude (`app/agent/orchestrator.py`,
   `app/vision/extractor.py`) reintenta hasta 5 veces con backoff exponencial si la cuenta recibe
   un `429` (límite momentáneo) o un error transitorio del lado de Anthropic - un pico de varios
   clientes escribiendo al mismo tiempo se absorbe solo, sin que nadie vea nada raro.
2. **Los límites de tu cuenta de Anthropic suben solos con el uso.** Anthropic asigna un límite de
   peticiones/minuto según el historial de gasto de la cuenta (tiers) - entre más uso real y pago
   acumules, más alto sube automáticamente, sin que tengas que hacer nada. Si en algún momento
   tienes muchos clientes simultáneos y sigues viendo el mensaje de "límite de uso alcanzado" con
   frecuencia, en https://console.anthropic.com puedes pedir directamente un aumento de límite
   para tu cuenta - es un trámite normal, no un tope fijo.

Este es el mismo patrón que usa cualquier producto de IA con muchos usuarios detrás de una sola
cuenta (Perplexity, Notion AI, etc.) - no es una limitación particular de Axiscam.

### Almacenamiento persistente (solo aplica al modo avanzado/web)

La app de escritorio guarda todo en el disco de cada usuario (su propia carpeta de datos local) -
esto no le aplica. Si en cambio estás en el modo avanzado (backend propio en Render/Railway/Fly):
el plan gratuito de esos hosts no incluye disco persistente: los planos subidos y los archivos
STEP/STL/G-code generados se pierden en cada redeploy **y en cada reinicio por inactividad**
(~15 min sin uso) del servicio - no es un caso raro, es el comportamiento normal del plan free. Si
tu servicio en Render sigue en "free", vas a seguir perdiendo proyectos sin previo aviso, incluyendo
a mitad de una demo.

`render.yaml` ya trae listo un disco persistente montado en `/data` (bloque `disk:`) y
`plan: starter` para que funcione - pero eso solo aplica cuando conectas/sincronizas el
blueprint de nuevo, o si cambias el plan del servicio manualmente en el dashboard de Render
(Settings del servicio → Plan). Este repo no puede cambiarte el plan ni cobrarte por su cuenta;
eso lo confirmas tú directamente en Render, donde también puedes ver el costo exacto antes de
aceptar.

## Limitaciones conocidas (para no sorprenderse)

- Sin `ANTHROPIC_API_KEY` configurada, la extracción de planos y el chat con el agente no
  funcionan — el resto del pipeline (confirmar, generar, aprobar) sigue operando desde botones
  directos en la interfaz.
- El motor de geometría (Capa 4 SolidWorks) soporta barrenos en caras laterales de piezas
  rectangulares (`cara: lateral_izquierda/derecha/frontal/posterior`). Sigue sin soportar: bases
  no rectangulares/circulares, escalones, perfiles exteriores no rectangulares, ni cajeras/ranuras
  en caras laterales. Se reportan como advertencia explícita en vez de modelarse a ciegas.
- El código G tiene trayectoria de corte real para taladrado, cajeras/ranuras y contornos
  exteriores/redondeos; features sin geometría suficiente en el JSON (p.ej. escalón) quedan como
  planeación (herramienta + velocidades) sin trayectoria, hasta integrar Mastercam real. Ninguna
  de las dos tiene chequeo de colisiones entre features simultáneos ni rampas de entrada.
- Los valores de velocidad/avance de la base de conocimiento (`app/knowledge_base/data/`) son
  datos semilla de referencia — cada material tiene un campo `validado_por: null` hasta que un
  maquinista del taller los revise.
