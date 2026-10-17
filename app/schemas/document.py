
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    id: int
    organization_id: int
    uploaded_by_id: int | None
    filename: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
    
    
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)