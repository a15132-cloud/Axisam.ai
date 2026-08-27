# Axiscam

Agente de IA de CAD para un taller: un usuario sube el plano de una pieza en un chat, el agente
extrae las medidas y genera el modelo 3D real (STEP + STL), con aprobación humana obligatoria en
dos puntos antes de entregar el archivo final. Axiscam es una herramienta de **CAD, no de CAM**:
entrega el modelo 3D listo para que un programador CAM/maquinista lo trabaje en Mastercam (u otro
software CAM) — no planea trayectorias de maquinado ni genera código G. Ver "Por qué Axiscam no
genera código G" más abajo.

## Qué es real hoy y qué es simulación

Este entorno de desarrollo es Linux y no tiene SolidWorks instalado (corre en Windows con
licencia activa vía COM). Para no bloquear todo el proyecto en esa infraestructura, el sistema
está dividido así:

| Capa | Estado en este repo |
|---|---|
| Capa 1 — Chat / UI | **Real y funcional** (React) |
| Capa 2 — Orquestador (loop de tool-use con Claude) | **Real y funcional** (FastAPI + Anthropic SDK) |
| Capa 3 — Visión / extracción del plano | **Real y funcional** (Claude multimodal), requiere `ANTHROPIC_API_KEY` |
| Capa 4 — SolidWorks (modelado 3D) | **Geometría real por defecto**, generada con un kernel OpenCascade (`cadquery`) — produce archivos STEP/STL reales, abribles en SolidWorks hoy mismo. **SolidWorks real cuando está disponible**: si `apps/windows-bridge` corre en tu propia PC con Windows con SolidWorks instalado, el orquestador lo detecta y prefiere automáticamente su salida en vez del motor simulado (ver más abajo). |
| Capa 5 — Base de conocimiento de manufactura | **Real**, tabla de decisión explícita (YAML + Python) — sigue existiendo y probada (`app/knowledge_base/`), pero ya no se expone al usuario: es parte del motor CAM retenido, ver la sección de abajo. |
| Capa 6 — Aprobación humana | **Real y aplicado en el backend** — cada transición de aprobación es un endpoint dedicado que ningún tool-call del LLM puede invocar por su cuenta |

## Por qué Axiscam no genera código G

Decisión de producto: Axiscam construye el modelo 3D confirmado (STEP/STL) y se detiene ahí. No
planea trayectorias, no estima tiempo de maquinado ni genera código G — eso queda para el
programador CAM del taller, trabajando el STEP en Mastercam real. Dos checkpoints humanos, no
tres: confirmar los datos extraídos del plano, y confirmar el modelo 3D — el segundo es el
checkpoint final, no hay una tercera etapa de "trayectorias/código G" después.

Si quieres **visualizar** una trayectoria de código G (tuyo, no generado por Axiscam) sobre un
modelo, la vista independiente de **Simulación** (menú lateral) lo hace: subes tu propio `.nc`
junto con un `.STL`/`.STEP`, y anima el recorrido real de la herramienta tal como está escrito en
el archivo. Es solo un visor — no crea ni modifica ningún proyecto, y no verifica colisiones
contra material o mordazas.

El motor CAM que sí planeaba trayectorias y generaba código G (`app/cam/*.py` — selección de
herramienta/velocidades por feature, ciclos de taladrado G81/G83, desbaste de cajeras, offsets de
contorno) sigue en el repo, sigue probado (`apps/orchestrator/tests/test_cam.py`), pero ya no
está conectado a las tools del agente ni a los endpoints de la API — es ingeniería real que puede
volver a exponerse más adelante (sería un cambio de enrutamiento, no una reescritura), pero hoy no
forma parte del producto.

## Conectar tu SolidWorks real (`apps/windows-bridge`)

Este repo también incluye un servicio .NET opcional (`apps/windows-bridge`) que, corriendo en tu
propia PC con Windows con SolidWorks instalado, hace que Axiscam use el software real en vez del
motor simulado — sin configuración manual. El orquestador intenta conectarse a
`http://127.0.0.1:5757` en cada generación de modelo con un timeout corto; si no hay nada ahí (el
caso normal en este sandbox, en un servidor, o en cualquier máquina sin SolidWorks), sigue usando
el motor simulado exactamente como hoy. Si el bridge está corriendo, la interfaz muestra un
indicador ("SolidWorks real" / "Motor simulado") en cada modelo generado, y en el pie del menú
lateral. Ver `apps/windows-bridge/README.md` para instalación y alcance real verificado.

## Estructura

```
apps/
  orchestrator/   Backend Python (FastAPI) - Capas 2, 3, 4, 6 (Capa 5/CAM retenida pero no expuesta)
  web/            Frontend React - Capa 1
  windows-bridge/ Servicio .NET opcional - conecta la Capa 4 a SolidWorks real
                  en la PC Windows del usuario (ver apps/windows-bridge/README.md)
docs/
  architecture.md Detalle técnico de cada capa y el plan de migración a SolidWorks real
deploy/
  docker-compose.yml + README.md  Backend propio autoalojado (gratis, sin PaaS) - ver "Desplegar
                                   a producción" abajo
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
   **Confirmar** el modelo — checkpoint 2, el último: el proyecto queda **Aprobado**.
4. En cualquier momento a partir del modelo 3D, el botón **"Descargar todo (.zip)"** entrega
   STEP + STL + un reporte de resumen (medidas, material, features, advertencias del modelado)
   en un solo archivo.

La interfaz es responsiva: en celular, el menú de proyectos se abre como panel deslizable y el
panel de plano/vista 3D/actividad se accede con una pestaña "Detalles" junto al chat.

## Desplegar a producción

Este es un monorepo de **dos servicios independientes que deben desplegarse por separado** — este
es el paso que causa el banner rojo "No se pudo conectar con el backend" si solo desplegaste uno
de los dos. Vercel solo puede alojar el primero:

| Servicio | Dónde | Qué hace |
|---|---|---|
| `apps/web` (frontend) | Vercel | La interfaz de chat que ves en el navegador |
| `apps/orchestrator` (backend) | Render (u otro host de contenedores) | El trabajo real: llama a Claude, genera la geometría 3D, etc. |

**Si el backend nunca se desplegó, el frontend en Vercel no tiene con quién hablar — por eso
aparece "no se pudo conectar", aunque el frontend cargue perfectamente.** No es un bug del
código: son dos despliegues separados y ambos son necesarios.

Por qué el backend no puede vivir también en Vercel: sus funciones serverless no soportan un
proceso de larga duración con un motor de geometría 3D pesado (`cadquery`/OpenCascade, cientos de
MB de librerías nativas - muy por encima del límite de tamaño de una función de Vercel) ni guardar
archivos de forma permanente (los planos y STEP/STL generados). No es una limitación de
configuración que se pueda ajustar - es el mismo motivo por el que ningún producto de IA serio
corre su backend completo solo en funciones serverless. **Y esto es completamente invisible para
tus clientes**: ellos solo entran a tu link de Vercel y usan la app normal - nunca ven, ni les
importa, que el trabajo pesado ocurre en un segundo servicio detrás.

### Paso 1 — Backend (elige una opción)

#### Opción A — Servidor propio, gratis para siempre (recomendado)

Ningún plan "free" de un PaaS administrado (Render, Railway, Fly) es realmente gratis sin
condiciones: todos duermen el servicio tras un rato de inactividad y tardan ~50s en despertar en
el siguiente request — eso es lo que se siente como "errores de conexión / lentitud constante".
`deploy/` trae un `docker-compose.yml` que corre el mismo backend en un servidor Linux normal
tuyo (por ejemplo una VM **Oracle Cloud "Always Free"** — la única oferta permanentemente gratis
con una máquina real que no se apaga sola, no una prueba de 30 días) detrás de Caddy, que consigue
el certificado HTTPS automáticamente. Ver **`deploy/README.md`** para la guía paso a paso completa
(crear la VM, abrir puertos, instalar Docker, levantar el stack). Al final tienes una URL HTTPS
propia — sigue con el Paso 2 de abajo usando esa URL.

#### Opción B — Render (u otro host de contenedores administrado)

Más simple de arrancar, pero de pago si necesitas que no se duerma (plan "Starter" o superior) —
ver "Almacenamiento persistente" más abajo.

1. En https://dashboard.render.com → **New +** → **Blueprint** → conecta este repositorio de
   GitHub y selecciona la rama con este código. Render detecta `render.yaml` en la raíz del repo
   automáticamente y configura el servicio (usa el `Dockerfile` de `apps/orchestrator/`).
2. Render te pedirá un solo valor antes de desplegar:
   - `ANTHROPIC_API_KEY` — tu clave de https://console.anthropic.com/settings/keys. Esta es la
     **única** key que existe en todo el sistema — tus clientes jamás la ven ni tienen que
     configurar nada, igual que en Perplexity, Grok o ChatGPT (ellos tampoco te piden una API key;
     la empresa la paga por detrás). Ver la sección "Evitar quedarte sin créditos sin avisar" más
     abajo antes de desplegar.
   (El backend acepta llamadas desde cualquier origen — no hay una URL de Vercel que configurar
   aquí ni un banner de CORS que perseguir; si el banner rojo de "no se pudo conectar" aparece, la
   causa está en el Paso 2 de abajo, no aquí.)
3. Cuando termine el deploy, copia la URL pública que te da Render (algo como
   `https://axiscam-orchestrator.onrender.com`).

Alternativas a Render con el mismo `Dockerfile`: Railway o Fly.io — ambos soportan "deploy from
Dockerfile" desde el repo de GitHub, si prefieres alguno de esos en vez del blueprint de Render.

### Paso 2 — Apuntar Vercel a ese backend

1. En el dashboard de tu proyecto en Vercel → **Settings** → **Environment Variables**.
2. Agrega `VITE_API_BASE_URL` = la URL del Paso 1 (tu dominio propio, o la de Render) + `/api`,
   por ejemplo `https://api.tu-dominio.com/api` o `https://axiscam-orchestrator.onrender.com/api`.
3. **Redeploy** el proyecto en Vercel (las variables de entorno solo aplican en el próximo build,
   no retroactivamente a un deploy que ya existe). Nota: `ANTHROPIC_API_KEY` **no** va en Vercel —
   Vercel solo sirve el frontend estático, esa key es del backend (Paso 1).

Con eso el banner rojo debe desaparecer.

> Nota honesta: escribí y revisé el `Dockerfile`, `render.yaml` y `deploy/docker-compose.yml` con
> cuidado (`docker compose config` valida sin errores, y el `Dockerfile` no cambió), pero este
> sandbox no tiene un daemon de Docker corriendo, así que no pude ejecutar el despliegue de punta
> a punta yo mismo para confirmarlo. Si algo falla al desplegar (típicamente un paquete de sistema
> faltante para las librerías nativas de `cadquery`, o los puertos 80/443 sin abrir en el Paso 1
> de `deploy/README.md`), copia el error exacto y lo corrijo.

## Una sola API key, invisible para tus clientes

Axiscam necesita a Claude (Anthropic) para el chat y la lectura de planos — no hay forma honesta
de tener un agente de IA real sin una API key real conectándolo a un modelo real (ningún producto
de IA escapa a esto, incluidos Perplexity, Grok o ChatGPT). Lo que sí es una decisión de diseño:
**quién carga con esa key**. Axiscam usa una sola `ANTHROPIC_API_KEY` configurada por ti en el
backend (Render) — tus clientes nunca ven ni configuran nada relacionado con IA, exactamente como
en cualquier producto de IA orientado a consumidor. Si esa key llega a fallar (vencida, sin
créditos, límite de uso alcanzado), el cliente ve un mensaje profesional y genérico en el chat en
vez de un error técnico — el detalle real queda solo en el registro de actividad del proyecto,
para que tú lo diagnostiques.

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

### Almacenamiento persistente

Con la Opción A (`deploy/`, servidor propio) esto no aplica - el volumen Docker `axiscam_data` es
siempre un punto de montaje real, persiste solo mientras no lo borres a propósito, sin plan de
pago de por medio. Lo que sigue es específico de Render/Railway/Fly (Opción B):

El plan gratuito de Render (igual que Railway/Fly en su plan gratis) no incluye disco
persistente: los planos subidos y los archivos STEP/STL generados se pierden en cada
redeploy **y en cada reinicio por inactividad** (~15 min sin uso) del servicio - no es un caso
raro, es el comportamiento normal del plan free. Si tu servicio en Render sigue en "free", vas a
seguir perdiendo proyectos sin previo aviso, incluyendo a mitad de una demo.

`render.yaml` ya trae listo un disco persistente montado en `/data` (bloque `disk:`) y
`plan: starter` para que funcione - pero eso solo aplica cuando conectas/sincronizas el
blueprint de nuevo, o si cambias el plan del servicio manualmente en el dashboard de Render
(Settings del servicio → Plan). Este repo no puede cambiarte el plan ni cobrarte por su cuenta;
eso lo confirmas tú directamente en Render, donde también puedes ver el costo exacto antes de
aceptar.

## Limitaciones conocidas (para no sorprenderse)

- Sin `ANTHROPIC_API_KEY` configurada, la extracción de planos y el chat con el agente no
  funcionan — el resto del pipeline (confirmar, generar) sigue operando desde botones directos
  en la interfaz.
- El motor de geometría (Capa 4 SolidWorks) soporta barrenos en caras laterales de piezas
  rectangulares (`cara: lateral_izquierda/derecha/frontal/posterior`). Sigue sin soportar: bases
  no rectangulares/circulares, escalones, perfiles exteriores no rectangulares, ni cajeras/ranuras
  en caras laterales. Se reportan como advertencia explícita en vez de modelarse a ciegas.
- Axiscam no genera código G ni planea trayectorias de maquinado — ver "Por qué Axiscam no genera
  código G" arriba. El motor CAM que sí lo hacía (`app/cam/*.py`, con velocidades/avances de
  `app/knowledge_base/data/` — datos semilla con `validado_por: null` hasta que un maquinista los
  revise) sigue en el repo y probado, pero no está conectado al producto hoy.
