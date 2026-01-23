from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.core.auth import auth_client
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME}")

    if settings.MARLO_API_KEY:
        try:
            import marlo

            marlo.init(api_key=settings.MARLO_API_KEY)
            logger.info("Marlo SDK initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Marlo: {e}")

    app.state.auth_client = auth_client

    yield

    logger.info(f"Shutting down {settings.APP_NAME}")

    if settings.MARLO_API_KEY:
        try:
            import marlo

            marlo.shutdown()
        except Exception:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    description="AI email & calendar assistant powered by Marlo and Auth0",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.AUTH0_SECRET,
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "healthy", "app": settings.APP_NAME}
