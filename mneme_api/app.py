import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import spacy
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mneme.extract import TagExtractor

from mneme_api.api import MemoryService, RequestConflict
from mneme_api.router import router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        key = os.environ["MNEME_API_KEY"]
        if not key.strip():
            raise ValueError("MNEME_API_KEY must not be empty")
        if not spacy.util.is_package("en_core_web_sm"):
            raise RuntimeError("Install en_core_web_sm before starting the API")
        TagExtractor()("Memory service initialization", "user")
        app.state.api_key = key
        app.state.memory = MemoryService(Path(os.environ["MNEME_DATA_DIR"]))
        yield

    app = FastAPI(title="Mneme API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    app.add_exception_handler(RequestConflict, conflict)
    app.add_exception_handler(Exception, failure)
    return app


async def conflict(request: Request, error: RequestConflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


async def failure(request: Request, error: Exception) -> JSONResponse:
    logger.error("Memory operation failed: %s", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Memory operation failed; retry the request"})
