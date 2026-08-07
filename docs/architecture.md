# Arquitectura de Axiscam

## El contrato central: `Pieza`

Todo el pipeline gira alrededor de un solo JSON (`app/schemas/piece.py::Pieza`): la Capa 3 lo
produce a partir del plano, el humano lo confirma o edita, la Capa 4 (geometría) lo consume para
construir el sólido, y la Capa 4/5 (CAM) lo vuelve a consumir para planear trayectorias. Ninguna
capa downstream reinterpreta texto libre ni vuelve a "leer" el plano — todas comparten la misma
estructura tipada (Pydantic en el backend, TypeScript espejado en `apps/web/src/lib/types.ts`).

Esto importa porque es lo que permite que Capa 4 (SolidWorks) sea reemplazable sin tocar Capa 2/3/5:
mientras algo siga produciendo un `Pieza` válido y algo siga consumiendo ese mismo contrato para
construir geometría, el resto del sistema no necesita cambiar.

## Capa 6 no es una instrucción de prompt — es una separación de código

La regla "nunca debe llegar código G a una máquina sin aprobación humana explícita" no se
implementa pidiéndole al LLM que se comporte bien. Se implementa así:

- Las tres transiciones de aprobación (`app/agent/approval.py`) son funciones invocadas
  **solo** desde endpoints REST dedicados (`/confirmar-extraccion`, `/confirmar-modelo`,
  `/aprobar-final`), que la interfaz llama cuando un humano hace clic en un botón específico.
- El loop de tool-use de Claude (`app/agent/orchestrator.py`) **no tiene** esas tres funciones
  en su lista de tools. No puede llamarlas aunque el usuario le diga "ya confirmé" en el chat.
- Cada handler de Capa 4 (`app/tools/handlers.py`) vuelve a validar la precondición del lado del
  servidor (`proyecto.pieza_confirmada`, `proyecto.modelo_confirmado`, `proyecto.aprobacion_final`)
  antes de hacer nada — no solo confía en que el LLM decidió llamar la herramienta en el momento
  correcto. Ver `tests/test_approval_and_handlers.py` para la prueba de que el pipeline completo
  respeta el orden incluso si algo intenta saltarse un paso.

El system prompt del agente (`app/agent/orchestrator.py::SYSTEM_PROMPT`) refuerza esto en lenguaje
natural para que el agente explique bien la situación al usuario, pero la garantía real está en
que las funciones de aprobación viven fuera del alcance de las tools del LLM.

## Capa 4 — SolidWorks: por qué un kernel de geometría real y no un mock

`app/geometry/builder.py` usa `cadquery` (bindings Python de OpenCascade) para construir un
sólido real a partir del `Pieza` confirmado, y exporta STEP/STL reales. La razón de no usar un
mock que solo devuelva "ok": el requisito explícito del proyecto es que el usuario reciba un
archivo que pueda cargar en SolidWorks/Mastercam hoy — un mock sin geometría real no cumple eso.

Restricciones deliberadas (documentadas en el código, no ocultas):

- Los redondeos/chaflanes de esquina se aplican **antes** de cortar barrenos/cajeras, porque
  después de cortar, los bordes de las paredes de los barrenos también son "verticales" y un
  selector de aristas los tomaría por error. El orden de operaciones en `build_pieza` no es
  arbitrario.
- Formas base no soportadas (`poligonal`, `revolucion`) lanzan `GeometryBuildError` en vez de
  adivinar geometría — un plano mal interpretado geométricamente es peor que un error claro.
- Features no soportados (`escalon`, `perfil_exterior`, caras laterales) se reportan en
  `features_omitidos` y se persisten en el proyecto (`Proyecto.features_omitidos_modelo`) para
  que el humano los vea en el checkpoint de revisión del modelo, no solo en un toast que
  desaparece.

### Migración a SolidWorks real

Cuando exista el servidor Windows: escribir un servicio C#/.NET que exponga los mismos verbos
(`crear sólido desde Pieza -> exportar STEP/STL`) vía la SolidWorks COM API, y hacer que
`app/tools/handlers.py::generar_modelo_3d` llame a ese servicio (HTTP/gRPC) en vez de a
`app.geometry.builder`. El resto del pipeline (Capa 2, 5, 6, frontend) no necesita cambios porque
consume el mismo contrato `Pieza -> archivos STEP/STL + advertencias`.

## Capa 4/5 — Mastercam: por qué es honestamente una simulación

Construir un motor CAM real (offsets de contorno sin gubias, desbaste de cajeras con
verificación de colisiones, enlaces entre operaciones) es un proyecto de ingeniería
especializado por sí solo — no algo defendible como "hecho" en este alcance. En vez de fingir
que existe, `app/cam/`:

- **Sí calcula de verdad** la selección de herramienta y velocidad/avance por feature
  (`app/knowledge_base/rules.py`), usando fórmulas estándar de maquinado (RPM = 1000·Vc / (π·D)).
  Esto es información real y útil incluso sin Mastercam conectado.
- **Sí genera G-code real** para taladrado (ciclos fijos G81/G83) — es geometría simple
  (posición + profundidad) y bien definida sin necesitar un motor CAM completo.
- **No inventa** trayectorias de corte para cajeras/perfiles/contornos. `app/cam/gcode.py` deja
  un comentario explícito (`TRAYECTORIA NO GENERADA - requiere Mastercam real`) en vez de un
  G1/G2/G3 fabricado que parecería confiable sin serlo.
- Todo archivo de código G lleva un encabezado y pie de página que dice **SIMULACIÓN - NO
  VERIFICADO POR MASTERCAM REAL - NO CARGAR EN LA MÁQUINA CNC SIN REVISIÓN**, además de la
  aprobación humana obligatoria antes de que el archivo exista.

Un bug real que se encontró y corrigió durante las pruebas: el generador de ciclos de taladrado
insertaba un `G0` (movimiento rápido) entre cada barreno repetido de un patrón. `G81`/`G83` son
códigos modales del mismo grupo que `G0`/`G1` — emitir `G0` entre barrenos cancela silenciosamente
el ciclo fijo, y los barrenos 2..N dejarían de maquinarse sin ningún error visible. Ver
`tests/test_cam.py::test_ciclo_taladrado_no_se_cancela_entre_barrenos` para la prueba de
regresión. Es el tipo de error que un "parece razonable" no detecta — solo generar el G-code real
y revisarlo con cuidado lo hizo evidente.

### Migración a Mastercam real

Escribir el servicio C#/.NET usando Mastercam SDK (NET-Hooks/C-Hooks) que reciba el STEP
generado por Capa 4 (SolidWorks) y el `ToolpathPlan` ya calculado por `app/cam/planner.py` (que
sigue siendo útil como *plan* incluso con Mastercam real generando la geometría de corte), y que
devuelva código G verificado. `app/tools/handlers.py::exportar_codigo_g` cambia para llamar a ese
servicio en vez de a `app.cam.gcode`.

## Capa 5 — base de conocimiento

`app/knowledge_base/data/*.yaml` son tablas de decisión explícitas, no un modelo entrenado:
materiales (velocidad de corte, avance por diente, refrigerante), catálogo de herramientas
disponibles, y postprocesadores (Haas por default, con Fanuc/Siemens ya definidos y la
estructura pensada para agregar más). Cada material tiene `validado_por: null` — el plan
explícito del proyecto es que un maquinista con experiencia real valide y ajuste estos números
antes de confiar en ellos para producción; el código ya emite una advertencia visible cada vez
que usa un valor no validado.

## Frontend

React + Vite + TypeScript + Tailwind v4 + Framer Motion + react-three-fiber. Decisión notable:
el visor 3D (`app/components/viewer/StlViewer.tsx`) NO usa `@react-three/drei`'s `<Stage>` con
un `environment` HDR, porque ese HDR se descarga de un CDN externo por default — en una red sin
acceso a ese host (como el sandbox de este mismo desarrollo) el `Canvas` completo pierde el
contexto WebGL y la pantalla queda en negro. La iluminación es manual y autocontenida, y el
encuadre de cámara usa `<Bounds>` (matemática pura, sin red). Esto también es la decisión correcta
para una herramienta de taller que podría correr en una red aislada.

Las tarjetas de la conversación (extracción, modelo 3D, trayectorias, simulación, código G) se
derivan del estado real del proyecto en cada render (`app/lib/deriveEntries.ts`) en vez de
mantenerse como una copia separada que se actualiza a mano después de cada acción — evita que la
UI muestre algo que ya no coincide con lo que el backend realmente hizo.

## Referencia rápida de la API

Ver `apps/orchestrator/app/api/routes_projects.py` y `routes_files.py` para el detalle; en
resumen:

- `POST /api/projects` crear · `GET /api/projects` listar · `GET/DELETE /api/projects/{id}`
- `POST /api/projects/{id}/plano` subir plano (dispara Capa 3)
- `PUT /api/projects/{id}/pieza-extraida` editar extracción antes de confirmar
- `POST /api/projects/{id}/confirmar-extraccion` — checkpoint 1
- `POST /api/projects/{id}/generar-modelo-3d`
- `POST /api/projects/{id}/confirmar-modelo` — checkpoint 2
- `POST /api/projects/{id}/generar-trayectorias`, `/simular-maquinado`
- `POST /api/projects/{id}/aprobar-final` — checkpoint 3 · `/rechazar`
- `POST /api/projects/{id}/exportar-codigo-g`
- `POST /api/projects/{id}/chat` — loop de tool-use de Claude
- `GET /api/projects/{id}/files/{nombre}` y `/plano-original` — descargas
- `GET /api/knowledge-base/materiales`, `/postprocesadores`
