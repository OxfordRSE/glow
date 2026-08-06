"""Liveness ping from the open browser tab/window.

`main.py`'s watcher thread quits the server once heartbeats stop arriving —
the closest a browser-tab app gets to "the window was closed". No auth: it
carries no data, runs on every page (including signin), and only touches
process lifecycle.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()


@router.post("/heartbeat")
def heartbeat(request: Request) -> Response:
    request.app.state.last_heartbeat = time.time()
    return Response(status_code=204)
