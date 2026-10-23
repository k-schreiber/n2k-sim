"""REST + WebSocket API (contract in docs/spec/web-ui.md) and static file serving."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from n2k_sim.app import Runtime
from n2k_sim.config import Scenario

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
STATE_INTERVAL = 0.25  # s
RAW_INTERVAL = 0.2  # s
MOTION_INTERVAL = 0.1  # s, the simulation tick
OK = {"ok": True}


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await runtime.start()
        yield
        await runtime.stop()

    app = FastAPI(title="n2k-sim", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def guarded(fn, *args):
        try:
            return fn(*args)
        except (ValueError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def state():
        return runtime.state()

    @app.get("/api/scenario")
    async def get_scenario():
        return runtime.scenario.model_dump()

    @app.put("/api/scenario")
    async def put_scenario(body: dict[str, Any] = Body(...)):
        scenario = guarded(Scenario.model_validate, body)
        await runtime.load_scenario(scenario)
        return OK

    @app.patch("/api/scenario/{section}")
    async def patch_section(section: str, body: dict[str, Any] = Body(...)):
        guarded(runtime.patch_section, section, body)
        return OK

    @app.patch("/api/static")
    async def patch_static(body: dict[str, Any] = Body(...)):
        guarded(runtime.patch_static, body)
        return OK

    @app.put("/api/overrides/{name}")
    async def put_override(name: str, body: dict[str, Any] = Body(...)):
        if body.get("value") is None:
            raise HTTPException(status_code=400, detail="value required")
        guarded(runtime.set_override, name, body["value"])
        return OK

    @app.delete("/api/overrides/{name}")
    async def delete_override(name: str):
        guarded(runtime.set_override, name, None)
        return OK

    @app.patch("/api/output")
    async def patch_output(body: dict[str, Any] = Body(...)):
        try:
            await runtime.patch_output(body)
        except (ValueError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return OK

    @app.patch("/api/output/pgns/{pgn_id}")
    async def patch_pgn(pgn_id: str, body: dict[str, Any] = Body(...)):
        guarded(runtime.patch_pgn, pgn_id, body)
        return OK

    @app.post("/api/wind/gust")
    async def gust():
        runtime.sim.env.wind.trigger_gust(runtime.sim.t)
        return OK

    @app.post("/api/seabed/shallow")
    async def shallow():
        runtime.sim.env.trigger_shallow(runtime.sim.t)
        return OK

    @app.post("/api/autopilot/tack")
    @app.post("/api/autopilot/gybe")
    async def tack():
        runtime.tack()
        return OK

    @app.post("/api/autopilot/adjust")
    async def adjust(body: dict[str, Any] = Body(...)):
        guarded(runtime.adjust, float(body.get("delta", 0)))
        return OK

    @app.post("/api/log/reset_trip")
    async def reset_trip():
        runtime.sim.boat.reset_trip()
        return OK

    @app.post("/api/sim/{action}")
    async def sim_control(action: str):
        if action == "pause":
            runtime.running = False
        elif action == "resume":
            runtime.running = True
        elif action == "reset":
            runtime.reset()
        else:
            raise HTTPException(status_code=404, detail=f"unknown action {action}")
        return OK

    @app.get("/api/polar")
    async def get_polar():
        p = runtime.sim.polar
        return {"name": p.name, "tws": p.tws, "twa": p.twa, "speed": p.speed}

    @app.put("/api/polar")
    async def put_polar(request: Request):
        text = (await request.body()).decode("utf-8", errors="replace")
        guarded(runtime.upload_polar, text)
        return OK

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        sub = {"raw": False, "motion": False, "seq": runtime.raw_seq}

        async def receive():
            while True:
                msg = json.loads(await socket.receive_text())
                topic = msg.get("subscribe")
                if topic == "raw":
                    sub.update(raw=True, seq=max(runtime.raw_seq - 200, 0))
                elif topic == "motion":
                    sub["motion"] = True
                topic = msg.get("unsubscribe")
                if topic in ("raw", "motion"):
                    sub[topic] = False

        async def send():
            loop = asyncio.get_running_loop()
            last_state = last_raw = 0.0
            while True:
                now = loop.time()
                if now - last_state >= STATE_INTERVAL:
                    await socket.send_json({"type": "state", **runtime.state()})
                    last_state = now
                if sub["raw"] and now - last_raw >= RAW_INTERVAL:
                    lines, sub["seq"] = runtime.raw_since(sub["seq"])
                    if lines:
                        await socket.send_json({"type": "raw", "lines": lines})
                    last_raw = now
                if sub["motion"]:
                    await socket.send_json(runtime.motion())
                await asyncio.sleep(MOTION_INTERVAL if sub["motion"] else min(STATE_INTERVAL, RAW_INTERVAL))

        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        except WebSocketDisconnect:
            pass
        finally:
            for t in tasks:
                t.cancel()

    return app
