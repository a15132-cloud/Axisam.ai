"""Client for the optional local Windows companion service (apps/windows-bridge).

Axiscam's default Capa 4 is a simulated geometry/CAM engine (cadquery +
G-code templates) so the whole pipeline works out of the box on any
machine - including servers, containers, and this dev sandbox - with no
SolidWorks or Mastercam installed. apps/windows-bridge is a separate
.NET service a user runs ONLY on their own Windows machine that actually
has SolidWorks/Mastercam licensed and installed. When that service is
reachable, this client prefers it over the simulation, so
generar_modelo_3d/exportar_codigo_g produce real SolidWorks/Mastercam
output instead of the simulated one.

"Conecta facil" in practice means: zero configuration. The bridge always
listens on 127.0.0.1:5757 (see AxiscamBridge.Api/Program.cs), and this
client's default BRIDGE_URL points at exactly that - so on the user's own
Windows machine, running the bridge alongside the orchestrator is enough
for detection to happen automatically on the very next model/G-code
generation call. Everywhere else (this sandbox, a Linux/Mac dev machine,
a hosted deployment), the connection attempt fails fast and the caller
falls back to the simulated engine - AXISCAM_WINDOWS_BRIDGE_URL exists
only for the unusual case of running the bridge on a different host/port.

Every lookup here is short-timeout and best-effort: "bridge not running"
is the overwhelmingly common case and must never raise or add
perceptible latency. The one thing this module does raise for is "the
bridge IS there, DID attempt the real SolidWorks/Mastercam call, and it
failed" - that is a genuine failure the user needs to see, not something
to paper over by silently falling back to a simulated result that would
look identical to a real one.
"""

from __future__ import annotations

import os

import httpx

from app.schemas.piece import Pieza
from app.schemas.project import ToolpathPlan

BRIDGE_URL = os.environ.get("AXISCAM_WINDOWS_BRIDGE_URL", "http://127.0.0.1:5757").rstrip("/")

# Connect timeout is deliberately tiny: on every machine that isn't the
# user's own Windows shop-floor PC (the default case), nothing is
# listening on this port, and the connection fails almost instantly.
# Read/write allow real STEP/STL/G-code payloads time to transfer once a
# connection is actually established.
_TIMEOUT = httpx.Timeout(connect=0.3, read=15.0, write=15.0, pool=0.3)


class BridgeError(Exception):
    """The bridge responded but the real SolidWorks/Mastercam call failed.

    Distinct on purpose from "bridge unreachable" / "software not
    available there" (both represented as None) - those are the expected
    default and the caller falls back to the simulated engine. This is a
    genuine failure that must reach the user, not be masked by a fallback
    that would look like a real result.
    """


def _post(path: str, payload: dict) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            return client.post(f"{BRIDGE_URL}{path}", json=payload)
    except httpx.HTTPError:
        return None


def _get(path: str) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            return client.get(f"{BRIDGE_URL}{path}")
    except httpx.HTTPError:
        return None


def estado_bridge() -> dict | None:
    """Raw /health payload, or None if nothing is listening at BRIDGE_URL.

    Used both to gate generar_modelo_solidworks/generar_codigo_g_mastercam
    and to let the orchestrator's own /api/health report real connection
    status to the frontend, instead of a static "not implemented" string.
    """
    resp = _get("/health")
    if resp is None or resp.is_error:
        return None
    return resp.json()


def generar_modelo_solidworks(pieza: Pieza) -> dict | None:
    """None whenever the bridge or SolidWorks isn't there - the normal
    case the caller falls back on. Raises BridgeError only when the
    bridge genuinely attempted the SolidWorks call and it failed.
    """
    resp = _post("/solidworks/generar-modelo", pieza.model_dump(mode="json"))
    if resp is None or resp.status_code == 503:
        return None
    if resp.is_error:
        raise BridgeError(f"El bridge de Windows respondio con error generando el modelo en SolidWorks: {resp.text}")
    return resp.json()


def generar_codigo_g_mastercam(pieza: Pieza, plan: ToolpathPlan, postprocesador: str) -> dict | None:
    """Same None-vs-BridgeError contract as generar_modelo_solidworks."""
    resp = _post(
        "/mastercam/generar-codigo-g",
        {
            "pieza": pieza.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "postprocesador": postprocesador,
        },
    )
    if resp is None or resp.status_code == 503:
        return None
    if resp.is_error:
        raise BridgeError(f"El bridge de Windows respondio con error generando codigo G en Mastercam: {resp.text}")
    return resp.json()
