import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mneme_api.data_model import AddRequest, AddResponse, SearchRequest, SearchResponse

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def authenticate(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), request.app.state.api_key.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid API key", headers={"WWW-Authenticate": "Bearer"})


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/add", dependencies=[Depends(authenticate)])
def add(request: AddRequest, context: Request) -> AddResponse:
    return context.app.state.memory.add(request)


@router.post("/search", dependencies=[Depends(authenticate)])
def search(request: SearchRequest, context: Request) -> SearchResponse:
    return context.app.state.memory.search(request)
