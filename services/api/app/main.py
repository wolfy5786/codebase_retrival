"""
CodeGraph API Gateway — FastAPI application.
Serves /api/v1 endpoints for auth, codebases, ingestion, query, and admin.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env from mounted project (Docker) or project root (local) — fixes env_file not loading on Windows
# override=True: Docker may set empty vars; we must replace them with values from .env
_me = Path(__file__).resolve()
_env_paths = [
    Path("/mnt/project/.env"),  # Docker volume mount
]
# parents[3] = project root when run locally; in Docker (/app/app/main.py) only 3 parents exist
if len(_me.parents) >= 4:
    _env_paths.append(_me.parents[3] / ".env")
_env_paths.extend([
    Path.cwd() / ".env",
    Path.cwd().parent / ".env",
])
for _p in _env_paths:
    if _p.exists():
        load_dotenv(_p, override=True)
        break
else:
    load_dotenv(override=True)

from app.queue.redis import redis_connection
from app.routers import admin, auth, codebases, ingestion, query


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify Redis connectivity. Shutdown: no-op."""
    logger.info("lifespan redis_ping started")
    async with redis_connection() as client:
        await client.ping()
    logger.info("lifespan redis_ping ended")
    yield
    logger.info("lifespan shutdown")


app = FastAPI(
    title="CodeGraph API",
    description="REST API for CodeGraph — codebase management, ingestion, query, and admin operations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(codebases.router, prefix="/api/v1/codebases", tags=["codebases"])
app.include_router(ingestion.router, prefix="/api/v1/codebases", tags=["ingestion"])
app.include_router(query.router, prefix="/api/v1/codebases", tags=["query"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    """Return JSON error so errors surface in response body."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {"status": "ok"}
