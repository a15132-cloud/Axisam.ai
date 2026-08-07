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
| Capa 4 — SolidWorks (modelado 3D) | **Geometría real**, generada con un kernel OpenCascade (`cadquery`) en vez de la COM API de SolidWorks. Produce archivos STEP/STL reales, abribles en SolidWorks hoy mismo. |
| Capa 4 — Mastercam (trayectorias / código G) | **Simulación basada en reglas**, claramente etiquetada como tal. Genera trayectoria de corte real para taladrado (G81/G83), cajeras (desbaste en zigzag con radio de herramienta compensado) y contornos exteriores/redondeos (offset con esquinas correctamente redondeadas) — no solo taladros. Sigue sin chequeo de colisiones entre features simultáneos, sin rampas de entrada, y features sin suficiente geometría en el JSON (p.ej. escalón) quedan como planeación sin trayectoria. **Ningún código G de este sistema debe cargarse a una máquina sin que Mastercam real lo verifique.** |
| Capa 5 — Base de conocimiento de manufactura | **Real**, tabla de decisión explícita (YAML + Python), datos semilla pendientes de validar por un maquinista |
| Capa 6 — Aprobación humana | **Real y aplicado en el backend** — cada transición de aprobación es un endpoint dedicado que ningún tool-call del LLM puede invocar por su cuenta |

Cuando el servidor Windows con SolidWorks/Mastercam esté listo, el plan es sustituir
`app/geometry/builder.py` por llamadas COM reales y construir el servicio .NET para Mastercam
SDK detrás de los mismos endpoints — el contrato JSON (`Pieza`, `ToolpathPlan`) no cambia.
Ver `docs/architecture.md` para el detalle de esa migración.

## Estructura

```
apps/
  orchestrator/   Backend Python (FastAPI) - Capas 2, 3, 4, 5, 6
  web/            Frontend React - Capa 1
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

Este es un monorepo de dos servicios independientes, y **solo uno de los dos puede vivir en
Vercel**:

- **`apps/web` (frontend) → Vercel.** El `vercel.json` en la raíz del repo ya le dice a Vercel
  cómo construir este proyecto (`cd apps/web && npm install/build`, salida en `apps/web/dist`)
  — si antes daba error era porque no había ningún `package.json` en la raíz del repo y Vercel
  no tenía qué construir ahí. En el dashboard de Vercel, define la variable de entorno
  `VITE_API_BASE_URL` con la URL pública de tu backend (siguiente punto) + `/api`, por ejemplo
  `https://axiscam-api.tudominio.com/api`. Sin esta variable el frontend intenta llamar `/api`
  en el propio dominio de Vercel, que no tiene backend detrás.

- **`apps/orchestrator` (backend) → NO puede vivir en Vercel.** No es un error de configuración,
  es un límite real de la plataforma: Vercel corre funciones serverless efímeras (sin disco
  persistente, con límite de tiempo de ejecución), y este backend es un proceso FastAPI de larga
  duración que guarda archivos en disco (planos subidos, STEP/STL/G-code generados) y depende de
  `cadquery`/OpenCascade, una librería nativa pesada que no cabe cómodamente en el límite de
  tamaño de una función serverless de Vercel. Se agregó un `Dockerfile` en `apps/orchestrator/`
  listo para desplegar en **Railway, Render o Fly.io** (todos soportan "deploy from Dockerfile"
  con un par de clics desde el repo de GitHub). Ahí necesitas configurar:
  - `ANTHROPIC_API_KEY`
  - `AXISCAM_CORS_ORIGINS=https://tu-proyecto.vercel.app` (el dominio real de tu frontend)
  - Un volumen persistente montado en `/data` (si no, los archivos generados se pierden en cada
    redeploy — para producción real, la migración natural es mover ese almacenamiento a algo
    como S3, pero no era parte del alcance de esta fase)

  > Nota honesta: escribí y revisé el `Dockerfile` con cuidado, pero este sandbox no tiene un
  > daemon de Docker corriendo, así que no pude ejecutar `docker build` para verificarlo de
  > punta a punta. Si al desplegarlo algo falla (típicamente por un paquete del sistema faltante
  > para las librerías nativas de `cadquery`), dímelo y lo ajusto.

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
