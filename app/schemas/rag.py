
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class SourceResponse(BaseModel):
    document_id: int
    filename: str
    chunk_index: int
    similarity: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
