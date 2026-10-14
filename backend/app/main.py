import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import PlainTextResponse

from app.api.routes import (
    agent,
    assignment,
    campaigns,
    customers,
    enterprise,
    inventory,
    knowledge,
    org,
    perf_sheets,
    pricing,
    rag,
    search,
    telegram,
    work,
)
from app.ai_lab.routes import router as ai_lab_router
from app.calendar.routes import router as calendar_router
from app.perf.routes import router as perf_router
from app.requests.routes import router as requests_router
from app.requests.teams import router as teams_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.metrics import async_timed_request, record_request, render_metrics
from app.core.permissions import AuthorizationError
from app.core.startup import assert_production_safe
from app.db.session import WorkerSessionLocal, get_db
from app.worker import start_background, stop_background


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    assert_production_safe(settings)
    if settings.worker_mode == "embedded" and (
        settings.telegram_mode != "off" or settings.bale_mode != "off"
    ):
        # نگه‌داشتن reference تا garbage collector تسک‌ها را نبندد
        _bg_tasks = await start_background(WorkerSessionLocal)
    yield
    await stop_background()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="CM Platform API",
        description="AI-native automotive ops — Core + Agents + CRM + LLM planner",
        version="0.17.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        
        async with async_timed_request(request.method, request.url.path):
            response = await call_next(request)
        
        response.headers["X-Request-ID"] = request_id
        record_request(request.method, str(response.status_code))
        return response

    routers = [
        org.router,
        work.router,
        inventory.router,
        telegram.router,
        search.router,
        rag.router,
        agent.router,
        assignment.router,
        knowledge.router,
        pricing.router,
        customers.router,
        campaigns.router,
        enterprise.router,
        perf_router,
        calendar_router,
        requests_router,
        teams_router,
        perf_sheets.router,
        ai_lab_router,
    ]
    for r in routers:
        app.include_router(r)
        app.include_router(r, prefix="/v1")

    @app.exception_handler(AuthorizationError)
    async def authz_handler(request: Request, exc: AuthorizationError):
        return JSONResponse(
            status_code=403,
            content={
                "detail": exc.message,
                "error": {
                    "code": 403,
                    "message": exc.message,
                    "request_id": getattr(request.state, "request_id", None),
                },
            },
        )

    @app.exception_handler(HTTPException)
    async def http_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error": {
                    "code": exc.status_code,
                    "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                    "request_id": getattr(request.state, "request_id", None),
                },
            },
        )

    @app.get("/health")
    @app.get("/health/live")
    async def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    @app.get("/health/ready")
    async def ready(db: AsyncSession = Depends(get_db)):
        try:
            await db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - readiness probe: any failure means not ready
            return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(exc)})
        return {"status": "ready"}

    @app.get("/health/detailed")
    async def health_detailed():
        from app.core.metrics import health_check_data
        return await health_check_data()

    @app.get("/metrics")
    async def metrics():
        return PlainTextResponse(render_metrics(), media_type="text/plain; version=0.0.4")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
