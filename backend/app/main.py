from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    agent,
    assignment,
    campaigns,
    customers,
    inventory,
    knowledge,
    org,
    rag,
    search,
    telegram,
    work,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.permissions import AuthorizationError
from app.db.session import AsyncSessionLocal
from app.integrations.telegram.runtime import start_background, stop_background


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.telegram_mode != "off" or settings.bale_mode != "off":
        start_background(AsyncSessionLocal)
    yield
    await stop_background()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="CM Platform API",
        description="AI-native automotive ops — Core + Agents + CRM + LLM planner",
        version="0.16.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(org.router)
    app.include_router(work.router)
    app.include_router(inventory.router)
    app.include_router(telegram.router)
    app.include_router(search.router)
    app.include_router(rag.router)
    app.include_router(agent.router)
    app.include_router(assignment.router)
    app.include_router(knowledge.router)
    app.include_router(customers.router)
    app.include_router(campaigns.router)

    @app.exception_handler(AuthorizationError)
    async def authz_handler(_request: Request, exc: AuthorizationError):
        return JSONResponse(status_code=403, content={"detail": exc.message})

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
