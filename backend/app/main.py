"""FastAPI 应用入口。"""

import asyncio
from contextlib import asynccontextmanager, suppress
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.platform import runtime
from app.platform.database import Device, InferenceSession, Session, record_audit
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app):
    from app.platform.eog import warmup, shutdown
    await asyncio.to_thread(warmup)
    # Never resume movement after a service restart.
    with Session() as db:
        for session in db.scalars(select(InferenceSession).where(InferenceSession.status != "CLOSED")):
            session.status = "CLOSED"
        for device in db.scalars(select(Device)):
            device.data = {**device.data, "action": "STOP", "mode": "SIMULATED"}
            if device.state == "BUSY":
                device.state = "ONLINE"
        db.commit()
    task = asyncio.create_task(runtime.watchdog())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    with Session() as db:
        for replay in runtime.live.values():
            runtime.stop_all(db, replay, "SHUTDOWN")
        db.commit()
    runtime.live.clear()
    shutdown()

app = FastAPI(
    lifespan=lifespan,
    docs_url=None if settings.production else "/docs",
    redoc_url=None if settings.production else "/redoc",
    openapi_url=None if settings.production else "/openapi.json",
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "面向 ALS 重度运动障碍人群的脑电四分类意图识别系统（科研原型）。\n"
        "使用 EA+FBCSP 冷启动模型识别左转/右转/直行/停止；"
        "非医疗器械，结果仅供科研实验。"
    ),
)


@app.middleware("http")
async def platform_guard(request: Request, call_next):
    started = time.perf_counter()
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if origin and origin not in settings.effective_cors_origins:
            return JSONResponse({"detail": "Origin rejected"}, status_code=403)
        if settings.production and request.headers.get("x-bci-request") != "1":
            return JSONResponse({"detail": "Request header required"}, status_code=403)
    # Batch inference is research-only; project Q&A is available to every signed-in role.
    if settings.production and request.url.path.startswith(("/api/v1/analyze", "/api/v1/demo", "/api/v1/assistant/chat")):
        from app.platform.security import current_user
        from fastapi import HTTPException
        try:
            user = current_user(request)
            if not request.url.path.startswith("/api/v1/assistant/chat") and user["role"] not in {"admin", "researcher"}:
                raise HTTPException(403, "Research role required")
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    try:
        response = await call_next(request)
    except Exception:
        runtime.error_count += 1
        for replay in runtime.live.values():
            replay.running = False
            replay.controller.emergency = True
            replay.pending.clear()
        try:
            with Session() as db:
                for replay in runtime.live.values():
                    runtime.stop_all(db, replay, "API_ERROR")
                db.commit()
        except Exception:
            pass
        response = JSONResponse({"detail": "服务异常，已停止控制"}, status_code=500)
    elapsed = (time.perf_counter()-started)*1000
    runtime.request_count += 1
    runtime.request_metrics.append(elapsed)
    if response.status_code >= 400:
        runtime.error_count += 1
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Processing-Ms"] = str(round(elapsed,3))
    # Persist metadata only: never bodies, passwords, tokens, EEG or questions.
    if not request.url.path.endswith("/tick"):
        try:
            with Session() as db:
                record_audit(db, None, "api_access", method=request.method,
                             path=request.url.path[:160], status=response.status_code, latency_ms=elapsed)
                db.commit()
        except Exception:
            pass
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.effective_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "个体化脑机辅助控制平台 API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
