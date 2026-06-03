import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.session import check_db_connection, engine
from gateway.middleware import RequestIDMiddleware
from telemetry.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    logger.info("AegisFlow starting up")
    await check_db_connection()
    logger.info("All systems ready")
    yield
    await engine.dispose()
    logger.info("AegisFlow shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AegisFlow AI Gateway",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware — order matters: RequestID must be outermost
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from gateway.routes import tenant_router
    from gateway.proxy import proxy_router
    app.include_router(proxy_router, tags=["gateway"])
    app.include_router(tenant_router, prefix="/tenant", tags=["tenant"])

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
