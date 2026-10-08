from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr
from enum import Enum


class OrganizationRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class OrganizationCreate(BaseModel):
    name: str


class OrganizationResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
    
class OrganizationWithRoleResponse(BaseModel):
    id: int
    name: str
    role: str
    created_at: datetime
    
    
class OrganizationMemberCreate(BaseModel):
    email: EmailStr
    role: OrganizationRole = OrganizationRole.MEMBER


class OrganizationMemberResponse(BaseModel):
    user_id: int
    email: EmailStr
    full_name: str
    role: str
    joined_at: datetime
    
    
class OrganizationMemberRoleUpdate(BaseModel):
    role: OrganizationRole