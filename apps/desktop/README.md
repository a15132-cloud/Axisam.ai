# Axiscam Desktop

Envuelve Axiscam como una app de escritorio de verdad: la gente la
descarga, la instala, y ya - sin depender de que un servidor remoto (Render
o cualquier otro) esté despierto para poder usarla.

## Cómo funciona

```
Ventana de Electron (carga apps/web/dist, ya compilado)
        │  http://127.0.0.1:8731/api
        ▼
Backend local (el mismo apps/orchestrator de siempre - FastAPI +
                cadquery/OpenCascade - corriendo como proceso hijo)
        │  guarda proyectos/STEP/STL en el userData del SO, 100% local
        │
        │  la ÚNICA llamada que sale a internet: extracción de plano y
        │  chat, y solo hasta el relay (ver apps/relay/README.md) - todo
        │  lo demás (generar el STEP/STL, guardar archivos, simulación de
        │  G-code) no toca la red para nada.
        ▼
Relay en Vercel (api/relay/[...path].js) → api.anthropic.com
```

`main.js` arranca el backend, espera a que `/api/health` responda, y recién
entonces abre la ventana - así un arranque lento (la primera vez que el
motor de geometría carga) nunca se ve como una ventana en blanco o rota.

## Desarrollo

```bash
cd apps/orchestrator && uv sync --group dev   # una vez
cd apps/desktop && npm install
npm start
```

`npm start` compila `apps/web` con la URL del backend local ya horneada
(`scripts/build-web.mjs`) y abre Electron, que a su vez lanza el backend
real vía `uv run uvicorn` sobre el propio `apps/orchestrator` del repo - los
mismos tests/comportamiento que ya existen, nada nuevo que mantener por
separado.

## Construir el instalador de Windows

Antes de construir un instalador para repartir de verdad, edita
`RELAY_URL_DEFAULT` en `main.js` (o exporta `AXISCAM_RELAY_URL` en el
entorno donde corres el build) con la URL real de tu relay desplegado en
Vercel - ver `apps/relay/README.md`. El valor que trae el repo
(`https://TU-PROYECTO.vercel.app/api/relay`) es un placeholder a propósito,
no una URL real.

```powershell
cd apps/desktop
npm install
npm run dist:win
```

Esto: compila `apps/web`, vendoriza un Python portable con el backend
completo instalado dentro (`scripts/vendor-backend-windows.ps1`), y corre
`electron-builder` para producir un instalador `.exe` (NSIS) en
`apps/desktop/dist/`. También hay targets declarados para Mac (`dmg`) y
Linux (`AppImage`) en `package.json` para "instalable en cualquiera", pero
Windows es la plataforma principal y la única que este flujo prueba con
detalle por ahora.

## Limitaciones conocidas (léelas antes de repartir el instalador)

- **El script de vendorizado (`vendor-backend-windows.ps1`) se escribió y
  revisó con cuidado, pero no se pudo ejecutar de punta a punta en una PC
  Windows real desde este entorno** (un sandbox Linux sin Windows
  disponible) - `cadquery`/`cadquery-ocp` (el kernel de geometría) es una
  extensión nativa pesada, y confirmar que carga y exporta STEP
  correctamente dentro de un Python portable en Windows real es el
  siguiente paso pendiente, ya sea vía el workflow de CI
  (`.github/workflows/build-desktop.yml`) o probándolo tú mismo.
- El instalador no viene firmado (sin certificado de code-signing) -
  Windows SmartScreen va a mostrar "editor no reconocido" la primera vez
  que alguien lo instale. Aceptable para una v1.
- El instalador pesa varios cientos de MB - `cadquery-ocp` + su dependencia
  transitiva `vtk` (no usada realmente aquí, solo viene con el paquete) son
  pesadas. No se intentó reducir esto en esta pasada.
- La API key de Anthropic sigue siendo compartida (ver
  `apps/relay/README.md`) - el relay oculta la key real, pero el header de
  "cliente autorizado" que usa `apps/desktop` sigue siendo, en el fondo,
  algo embebido en un binario público. La protección real de fondo es el
  límite de gasto mensual en la consola de Anthropic.
