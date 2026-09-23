from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Text = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class BaseRequest(BaseModel):
    user_id: Text


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: Text
    timestamp: Annotated[int, Field(ge=0, strict=True)] | None = None


class AddRequest(BaseRequest):
    request_id: Text
    session_id: Text
    messages: Annotated[list[Message], Field(min_length=1)]


class SearchRequest(BaseRequest):
    query: Text
    top_k: Annotated[int, Field(ge=1, strict=True)]
    options: list[str] | None = None


class AddResponse(BaseModel):
    success: Literal[True] = True
    request_id: str
    user_id: str
    session_id: str


class Evidence(BaseModel):
    id: str
    content: str
    created_at: str


class SearchResponse(BaseModel):
    data: list[Evidence]
