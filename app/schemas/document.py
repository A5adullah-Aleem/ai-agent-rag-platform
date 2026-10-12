
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: int
    organization_id: int
    uploaded_by_id: int | None
    filename: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)