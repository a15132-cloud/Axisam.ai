# Arquitectura de Axiscam

## El contrato central: `Pieza`

Todo el pipeline gira alrededor de un solo JSON (`app/schemas/piece.py::Pieza`): la Capa 3 lo
produce a partir del plano, el humano lo confirma o edita, y la Capa 4 (geometría) lo consume para
construir el sólido — ese modelo 3D es la entrega final de Axiscam (ver "Por qué Axiscam no genera
código G" en el README). Ninguna capa downstream reinterpreta texto libre ni vuelve a "leer" el
plano — todas comparten la misma estructura tipada (Pydantic en el backend, TypeScript espejado en
`apps/web/src/lib/types.ts`).

Esto importa porque es lo que permite que Capa 4 (SolidWorks) sea reemplazable sin tocar Capa 2/3:
mientras algo siga produciendo un `Pieza` válido y algo siga consumiendo ese mismo contrato para
construir geometría, el resto del sistema no necesita cambiar.

## Capa 6 no es una instrucción de prompt — es una separación de código

La regla "nunca debe avanzar el proyecto sin aprobación humana explícita" no se implementa
pidiéndole al LLM que se comporte bien. Se implementa así:

- Las dos transiciones de aprobación (`app/agent/approval.py`) son funciones invocadas **solo**
  desde endpoints REST dedicados (`/confirmar-extraccion`, `/confirmar-modelo`), que la interfaz
  llama cuando un humano hace clic en un botón específico. `confirmar_modelo` es la última — no
  hay una tercera etapa de trayectorias/código G después (ver el docstring del módulo).
- El loop de tool-use de Claude (`app/agent/orchestrator.py`) **no tiene** esas funciones en su
  lista de tools. No puede llamarlas aunque el usuario le diga "ya confirmé" en el chat.
- Cada handler de Capa 4 (`app/tools/handlers.py`) vuelve a validar la precondición del lado del
  servidor (`proyecto.pieza_confirmada`, `proyecto.modelo_confirmado`) antes de hacer nada — no
  solo confía en que el LLM decidió llamar la herramienta en el momento correcto. Ver
  `tests/test_approval_and_handlers.py` para la prueba de que el pipeline completo respeta el
  orden incluso si algo intenta saltarse un paso.

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
- Barrenos en caras laterales (`cara: lateral_izquierda/derecha/frontal/posterior`) sí están
  soportados en piezas de base rectangular: cada cara tiene su propio par de ejes documentado en
  `CARAS_LATERALES` (`app/geometry/builder.py`) - `posicion.x` es la distancia a lo largo de esa
  cara, `posicion.y` es la altura (Z), sin importar cuál de las 4 caras sea. La herramienta de
  corte se construye con `cq.Solid.makeCylinder(radio, altura, pnt=origen, dir=direccion)` en vez
  de un `Workplane` con un plano con nombre (`"YZ"`/`"XZ"`) para no depender de memorizar la
  convención de normales de esos planes en cadquery - el punto y la dirección son explícitos y se
  verifican con un test que calcula el volumen removido exacto (πr²·longitud) para las 4 caras.
- Features no soportados (`escalon`, `perfil_exterior`, cajeras/ranuras en caras laterales) se
  reportan en `features_omitidos` y se persisten en el proyecto (`Proyecto.features_omitidos_modelo`)
  para que el humano los vea en el checkpoint de revisión del modelo, no solo en un toast que
  desaparece.

### Migración a SolidWorks real — implementada

Este servicio ya existe: `apps/windows-bridge/src/AxiscamBridge.SolidWorks` es un proyecto
C#/.NET que expone la misma operación (`Pieza -> STEP/STL`) vía la SolidWorks COM API
(`FeatureExtrusion2`, `FeatureCut4`, `SaveAs`), servido por `AxiscamBridge.Api` en
`http://127.0.0.1:5757`. `app/tools/handlers.py::generar_modelo_3d` llama primero a
`app/integrations/windows_bridge.py::generar_modelo_solidworks` (HTTP con timeout corto) y solo
cae al motor `cadquery` si ese bridge no está corriendo o SolidWorks no está disponible ahí — el
resto del pipeline (Capa 2, 5, 6, frontend) no cambió, porque ambos caminos devuelven el mismo
contrato `Pieza -> archivos STEP/STL + advertencias`, y el resultado marca `es_simulacion: false`
cuando viene de SolidWorks real.

Lo que sigue pendiente: el conector fue escrito con cuidado contra la API documentada y estable
de SolidWorks, pero **no se ha ejecutado todavía contra una instalación real** — ningún sandbox
usado para construirlo tenía SolidWorks instalado. Ver `apps/windows-bridge/README.md`, sección
"Honest status", para el alcance exacto verificado vs. pendiente de primera prueba real.

## Capa 4/5 — Mastercam/CAM: motor retenido, no expuesto en el producto

Axiscam es CAD, no CAM (ver "Por qué Axiscam no genera código G" en el README): el agente y la
API solo llegan hasta el modelo 3D confirmado. `app/cam/*.py` (planeación de trayectorias,
selección de herramienta/velocidad por feature, generación de código G) sigue existiendo en el
repo y sigue probado (`tests/test_cam.py`), pero ninguna tool del agente ni endpoint de la API lo
invoca — solo es alcanzable llamando directamente a las funciones de `app/tools/handlers.py`
(`generar_trayectorias`, `simular_maquinado`, `exportar_codigo_g`) desde un test o un script. Esta
sección documenta ese motor retenido tal cual funciona, no una capa activa del producto.

Construir un motor CAM real (offsets de contorno sin gubias, desbaste de cajeras con
verificación de colisiones, enlaces entre operaciones) es un proyecto de ingeniería
especializado por sí solo — no algo defendible como "hecho" en este alcance. En vez de fingir
que existe, `app/cam/`:

- **Sí calcula de verdad** la selección de herramienta y velocidad/avance por feature
  (`app/knowledge_base/rules.py`), usando fórmulas estándar de maquinado (RPM = 1000·Vc / (π·D)).
  Esto es información real y útil incluso sin Mastercam conectado.
- **Sí genera G-code real** para las operaciones cuya geometría de corte está bien definida a
  partir del `Pieza` (`app/cam/toolpath_geometry.py`, funciones puras y probadas por separado):
  - Taladrado: ciclos fijos G81/G83 (posición + profundidad).
  - Cajeras/ranuras: desbaste en zigzag, con el radio de la herramienta compensado (el centro de
    la herramienta nunca sale del bolsillo inset por su radio) y multi-pasada en Z según la
    profundidad total.
  - Contorno exterior (`perfil_exterior`) y redondeo/chaflán: offset de la silueta de la pieza
    (rectangular o circular) con esquinas correctamente redondeadas para un offset hacia afuera
    (suma de Minkowski con un disco de radio = radio de herramienta) — geometría real, no una
    aproximación cualquiera. `perfil_exterior` usa offset = radio de herramienta (la fresa corta
    por fuera del contorno nominal); redondeo/chaflán usan offset = 0 (la forma de la herramienta,
    no el offset, es lo que crea el filete/chaflán).
  Las esquinas se aproximan con segmentos de línea recta en vez de arcos G2/G3 - una decisión
  deliberada de seguridad: es mucho más fácil verificar que una lista de puntos calculados está
  dentro de los límites esperados (hay tests que lo verifican) que verificar que el sentido y el
  IJ de un arco están bien - un arco con la direccion invertida es un tipo de error que un test
  superficial no detecta fácilmente.
- **No inventa** geometría para features sin suficiente información en el `Pieza` (p.ej.
  `escalon`, que necesitaría saber qué arista y en qué dirección). `app/cam/gcode.py` deja un
  comentario explícito (`TRAYECTORIA NO GENERADA`) en vez de un G1/G2/G3 fabricado que parecería
  confiable sin serlo.
- Todo archivo de código G lleva un encabezado y pie de página que dice **SIMULACIÓN - NO
  VERIFICADO POR MASTERCAM REAL - NO CARGAR EN LA MÁQUINA CNC SIN REVISIÓN**, además de la
  aprobación humana obligatoria antes de que el archivo exista. Lo que sigue faltando incluso
  para las operaciones con trayectoria real: chequeo de colisiones/gubias entre features
  simultáneos, entradas rampadas (el plunge es recto), y desbaste adaptativo.

Un bug real que se encontró y corrigió durante las pruebas: el generador de ciclos de taladrado
insertaba un `G0` (movimiento rápido) entre cada barreno repetido de un patrón. `G81`/`G83` son
códigos modales del mismo grupo que `G0`/`G1` — emitir `G0` entre barrenos cancela silenciosamente
el ciclo fijo, y los barrenos 2..N dejarían de maquinarse sin ningún error visible. Ver
`tests/test_cam.py::test_ciclo_taladrado_no_se_cancela_entre_barrenos` para la prueba de
regresión. Es el tipo de error que un "parece razonable" no detecta — solo generar el G-code real
y revisarlo con cuidado lo hizo evidente.

### Migración a Mastercam real — el enganche existe, la automatización no

Nota de alcance: lo que sigue describe `app/tools/handlers.py::exportar_codigo_g` tal como está
escrito — código real y probado, pero no invocado por ningún endpoint ni tool del agente hoy (ver
la nota de alcance al inicio de esta sección). Es la ruta que quedaría lista para conectar si el
producto vuelve a exponer CAM en el futuro.

`exportar_codigo_g` ya intenta primero
`app/integrations/windows_bridge.py::generar_codigo_g_mastercam` contra el mismo bridge de
`apps/windows-bridge`, y solo cae a `app.cam.gcode` si no hay respuesta real — el mismo patrón
que SolidWorks. Lo que falta es el otro lado: `AxiscamBridge.Mastercam.MastercamService` hoy solo
detecta si Mastercam está instalado (por filesystem, sin COM) y reporta `EstaDisponible = false`
a propósito, porque a diferencia de SolidWorks, Mastercam no expone una API de automatización
externa estable y universal — su mecanismo principal son los Net-Hooks, DLLs C# que Mastercam
*carga dentro de sí mismo* y corre desde su propia UI, no algo que un proceso externo invoque por
HTTP. Completar esto significa escribir un Net-Hook contra el SDK de la versión de Mastercam
instalada, que reciba el STEP generado por Capa 4 y el `ToolpathPlan` ya calculado por
`app/cam/planner.py` (que sigue siendo útil como *plan* incluso con Mastercam real generando la
geometría de corte), y que le entregue el código G resultante de vuelta a
`MastercamService.GenerarCodigoGAsync` — ver "Completing the Mastercam connector" en
`apps/windows-bridge/README.md`.

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

Las tarjetas de la conversación (extracción, modelo 3D) se derivan del estado real del proyecto
en cada render (`app/lib/deriveEntries.ts`) en vez de mantenerse como una copia separada que se
actualiza a mano después de cada acción — evita que la UI muestre algo que ya no coincide con lo
que el backend realmente hizo. La vista de Simulación de código G (`SimulacionEstandaloneView.tsx`)
es independiente de este estado: no lee ni escribe ningún proyecto, solo parsea y anima el archivo
`.nc` que el usuario suba junto con su propio modelo.

### Responsive (celular / tablet / escritorio)

Un solo breakpoint (`lg`, 1024px) separa dos layouts, no varios ajustes puntuales:

- **Sidebar de proyectos**: panel fijo en escritorio; por debajo de `lg` se vuelve un cajón
  (`fixed` + `-translate-x-full`/`translate-x-0`, con backdrop) que se abre con el botón de
  hamburguesa del header y se cierra solo al seleccionar un proyecto.
- **Panel derecho** (datos del proyecto, plano, vista 3D, actividad): en escritorio siempre
  visible junto al chat; por debajo de `lg` estaba simplemente oculto (`hidden lg:block`) - eso
  se cambió por una pestaña "Chat"/"Detalles" en el header, con ambos paneles siempre montados
  y solo la visibilidad CSS alternada (`hidden`/`flex` según la pestaña activa), para no perder
  el estado del chat ni forzar un remount del visor 3D cada vez que se cambia de pestaña.
- Verificado con capturas reales en 390px (celular), 768px (tablet) y 1600px (escritorio) - no
  solo revisado por CSS, sino confirmando visualmente que el visor 3D renderiza correctamente
  después de cambiar de pestaña en móvil (un canvas WebGL creado mientras su contenedor tiene
  `display:none` puede quedar mal dimensionado; el chat, que es la pestaña por defecto, se monta
  visible desde el inicio).

### Descarga completa

`GET /api/projects/{id}/descargar-todo` arma un .zip en memoria (`app/storage/bundle.py`) con
STEP + STL (y un archivo de código G solo en el caso retenido/no-expuesto descrito arriba, si
alguna vez existe uno) más un `RESUMEN.txt` con las medidas y el aviso de qué es geometría real
vs. simulación - así el usuario tiene un solo archivo para llevarse, sin tener que entender la
distinción entre botones individuales.

## Referencia rápida de la API

Ver `apps/orchestrator/app/api/routes_projects.py` y `routes_files.py` para el detalle; en
resumen:

- `POST /api/projects` crear · `GET /api/projects` listar · `GET/DELETE /api/projects/{id}`
- `PUT /api/projects/{id}/nombre` renombrar
- `POST /api/projects/{id}/plano` subir plano (dispara Capa 3) · `/plano/verificar`,
  `/plano/buscar-medidas-faltantes` — segunda pasada de verificación de la extracción
- `PUT /api/projects/{id}/pieza-extraida` editar extracción antes de confirmar
- `POST /api/projects/{id}/confirmar-extraccion` — checkpoint 1
- `POST /api/projects/{id}/generar-modelo-3d` · `/activar-solidworks`
- `POST /api/projects/{id}/confirmar-modelo` — checkpoint 2, el último · `/rechazar`
- `POST /api/projects/{id}/chat` — loop de tool-use de Claude
- `GET /api/projects/{id}/files/{nombre}`, `/plano-original` y `/descargar-todo` (.zip) — descargas
- `GET /api/knowledge-base/materiales`, `/postprocesadores`
- `POST /api/convert/step-a-stl` — conversión STEP→STL para la vista de Simulación independiente

No hay endpoints de trayectorias/simulación/código G — ver "Por qué Axiscam no genera código G"
en el README.
