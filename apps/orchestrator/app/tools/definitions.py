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

Axiscam's scope is CAD only now - it builds the confirmed STEP/STL and
stops there. Toolpath planning/G-code generation (generar_trayectorias,
simular_maquinado, exportar_codigo_g) used to be tools here too; the
underlying engine (app/cam/*.py) still exists and is still tested, it's
just no longer offered to the agent or the user - see approval.py's
module docstring for the product-scope reasoning.
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

TODAS = [GENERAR_MODELO_3D]
