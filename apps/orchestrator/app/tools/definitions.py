"""Anthropic tool definitions the orchestrator agent (Capa 2) can call
mid-conversation. These map to the Capa 4 pipeline actions - not the raw
SolidWorks COM method names from the brief (crear_boceto_solidworks,
extruir_solidworks, ...), because this codebase's geometry engine builds
a full solid from the confirmed Pieza in one deterministic pass rather
than exposing incremental sketch/feature state across tool calls. See
app/geometry/builder.py for why (fillet/chamfer ordering constraints).

When the real SolidWorks COM service exists, these same tool names can
either call it directly or stay as a facade in front of the finer-grained
COM calls - the contract Claude sees does not need to change.
"""

GENERAR_MODELO_3D = {
    "name": "generar_modelo_3d",
    "description": (
        "Genera el modelo solido 3D (STEP + STL) a partir de la pieza extraida y CONFIRMADA por el "
        "usuario. Solo funciona si el usuario ya confirmo los datos extraidos del plano - si no, falla "
        "con un error explicando que falta la confirmacion."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

GENERAR_TRAYECTORIAS = {
    "name": "generar_trayectorias",
    "description": (
        "Planea la estrategia de maquinado, herramientas y parametros de corte (velocidad/avance) para "
        "cada feature de la pieza, usando la base de conocimiento de manufactura. Requiere que el usuario "
        "ya haya confirmado el modelo 3D."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "postprocesador": {
                "type": "string",
                "description": (
                    "Clave del postprocesador/controlador CNC a usar (p.ej. 'haas_vf_generico', "
                    "'fanuc_generico', 'siemens_840d'). Si el usuario no especifica, omite este campo "
                    "para usar el default del taller (Haas)."
                ),
            }
        },
        "additionalProperties": False,
    },
}

SIMULAR_MAQUINADO = {
    "name": "simular_maquinado",
    "description": (
        "Genera un resumen estimado de la operacion de maquinado (tiempo, herramientas, advertencias) "
        "a partir del plan de trayectorias ya generado. Este resumen es lo que el usuario revisa antes "
        "de dar la aprobacion final - dejalo claro en tu respuesta: es una ESTIMACION basada en reglas, "
        "no una simulacion fisica verificada por Mastercam real."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

EXPORTAR_CODIGO_G = {
    "name": "exportar_codigo_g",
    "description": (
        "Genera el archivo de codigo G final. SOLO puede ejecutarse despues de que el usuario dio la "
        "aprobacion final explicita (boton de aprobacion en la interfaz, no un mensaje de chat) - si no, "
        "falla. El archivo resultante sigue marcado como simulacion (pendiente de verificar con Mastercam "
        "real) y el usuario debe revisarlo con un maquinista antes de cargarlo en la maquina CNC."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

TODAS = [GENERAR_MODELO_3D, GENERAR_TRAYECTORIAS, SIMULAR_MAQUINADO, EXPORTAR_CODIGO_G]
