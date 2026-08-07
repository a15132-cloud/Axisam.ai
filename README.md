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
  orchestrator/   Backend Python (FastAPI) - Capas 2, 3, 4, 5, 6
  web/            Frontend React - Capa 1
  windows-bridge/ Servicio .NET opcional - conecta la Capa 4 a SolidWorks/Mastercam reales
                  en la PC Windows del usuario (ver apps/windows-bridge/README.md)
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

## Desplegar a producción

Este es un monorepo de **dos servicios independientes que deben desplegarse por separado** — este
es el paso que causa el banner rojo "No se pudo conectar con el backend" si solo desplegaste uno
de los dos. Vercel solo puede alojar el primero:

| Servicio | Dónde | Qué hace |
|---|---|---|
| `apps/web` (frontend) | Vercel | La interfaz de chat que ves en el navegador |
| `apps/orchestrator` (backend) | Render (u otro host de contenedores) | El trabajo real: llama a Claude, genera geometría, código G, etc. |

**Si el backend nunca se desplegó, el frontend en Vercel no tiene con quién hablar — por eso
aparece "no se pudo conectar", aunque el frontend cargue perfectamente.** No es un bug del
código: son dos despliegues separados y ambos son necesarios.

### Paso 1 — Backend en Render (el que probablemente falta)

1. En https://dashboard.render.com → **New +** → **Blueprint** → conecta este repositorio de
   GitHub y selecciona la rama con este código. Render detecta `render.yaml` en la raíz del repo
   automáticamente y configura el servicio (usa el `Dockerfile` de `apps/orchestrator/`).
2. Render te pedirá dos valores antes de desplegar:
   - `ANTHROPIC_API_KEY` — **puedes dejarla en blanco.** Axiscam usa "bring your own key": cada
     persona que use la app agrega su propia API key de Anthropic desde el botón "Configuración"
     en la interfaz, y esa key se usa solo para sus propios mensajes — tú, como operador del
     backend, nunca pagas el uso de tus clientes. Solo llena esto si quieres una key de respaldo
     del lado del servidor (por ejemplo para tus propias pruebas).
   - `AXISCAM_CORS_ORIGINS` — la URL de tu frontend en Vercel, por ejemplo
     `https://tu-proyecto.vercel.app` (sin `/` al final). Esta sí es necesaria: si no coincide
     exactamente con tu dominio de Vercel, el navegador bloquea las llamadas y verás el mismo
     banner rojo aunque el backend sí esté corriendo.
3. Cuando termine el deploy, copia la URL pública que te da Render (algo como
   `https://axiscam-orchestrator.onrender.com`).

### Paso 2 — Apuntar Vercel a ese backend

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

## Cada cliente usa su propia API key de Anthropic ("bring your own key")

Axiscam necesita a Claude (Anthropic) para el chat y la lectura de planos — no hay forma honesta
de tener un agente de IA real sin una API key real conectándolo a un modelo real. Lo que sí se
puede evitar es que **tú** pagues el uso de **todos tus clientes** con una sola key: cada persona
que abre Axiscam agrega su propia API key desde el botón "Configuración" (arriba a la derecha,
ícono de llave). Esa key:

- Se guarda solo en el navegador de esa persona (`localStorage`), nunca en el servidor.
- Se manda como header (`X-Anthropic-Api-Key`) solo en las dos llamadas que realmente usan Claude
  (subir plano, chat) — ver `_cliente_de_usuario` en `app/api/routes_projects.py`.
- Nunca se escribe en el archivo del proyecto ni en ningún log del backend.

Conseguir una toma ~2 minutos en https://console.anthropic.com/settings/keys y es "pay-as-you-go"
(se paga solo lo que se use, sin suscripción fija). Si el backend además tiene su propio
`ANTHROPIC_API_KEY` configurado (opcional, ver `render.yaml`), esa sirve como respaldo cuando un
usuario no ha puesto la suya todavía.

### Almacenamiento persistente

El plan gratuito de Render (igual que Railway/Fly en su plan gratis) no incluye disco
persistente: los planos subidos y los archivos STEP/STL/G-code generados se pierden en cada
redeploy o reinicio del servicio. Para producción real con datos persistentes, sube a un plan de
pago y agrega un disco montado en `/data`, o migra ese almacenamiento a algo como S3 — ninguna de
las dos era parte del alcance de esta fase.

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
