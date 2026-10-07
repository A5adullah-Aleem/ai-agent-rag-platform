from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
)


router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    organization_data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    organization = Organization(
        name=organization_data.name,
    )

    db.add(organization)
    db.flush()

    membership = Membership(
        user_id=current_user.id,
        organization_id=organization.id,
        role="owner",
    )

    db.add(membership)

    db.commit()
    db.refresh(organization)

    return organization