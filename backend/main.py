"""FastAPI composition root.

Spec §8.6:
  - Enable CORS for http://localhost:5173
  - All routes live under /api
  - Create /tmp/genshin_lyre/ on startup
  - Global exception handler → uniform error envelope
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.errors import ApiError, ApiErrorPayload
from api.routes_generate import router as generate_router
from api.routes_parse import get_store, router as parse_router
from api.routes_search import router as search_router
from api.store import ParsedFileStore
from utils.cache import DEFAULT_CACHE_DIR, ensure_cache_dir


file_store = ParsedFileStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    yield


app = FastAPI(title="Genshin Lyre Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Both origins are required: the browser treats localhost and 127.0.0.1
    # as distinct origins, and Vite serves dev builds on whichever the user
    # opens. The regex covers any localhost port for dev convenience.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.dependency_overrides[get_store] = lambda: file_store


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_payload().model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ApiErrorPayload(
            error="INTERNAL_ERROR",
            message="服务暂时不可用，请稍后再试。",
            detail=str(exc),
        ).model_dump(),
    )


app.include_router(search_router)
app.include_router(parse_router)
app.include_router(generate_router)
