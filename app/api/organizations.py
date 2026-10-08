from fastapi import APIRouter, Depends, status ,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.api.dependencies import get_current_user, require_role
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationRole,
    OrganizationWithRoleResponse,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationMemberRoleUpdate,
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



@router.get(
    "/",
    response_model=list[OrganizationWithRoleResponse],
)
def get_my_organizations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = db.scalars(
        select(Membership)
        .where(Membership.user_id == current_user.id)
    ).all()

    return [
        OrganizationWithRoleResponse(
            id=membership.organization.id,
            name=membership.organization.name,
            role=membership.role,
            created_at=membership.organization.created_at,
        )
        for membership in memberships
    ]
    
    
    
@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_organization_member(
    organization_id: int,
    member_data: OrganizationMemberCreate,
    current_user: User = Depends(
    require_role("owner", "admin")
),
    db: Session = Depends(get_db),
):
    # 1. Check that the organization exists
    organization = db.get(Organization, organization_id)

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # 2. Check that the user being added exists
    user = db.scalar(
        select(User).where(User.email == member_data.email)
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )



    # 3. Check if the user is already a member
    existing_membership = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.organization_id == organization_id,
        )
    )

    if existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this organization",
        )

    # 4. Create membership
    membership = Membership(
        user_id=user.id,
        organization_id=organization_id,
        role=member_data.role,
    )

    db.add(membership)
    db.commit()
    db.refresh(membership)

    # 6. Return member information
    return OrganizationMemberResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        joined_at=membership.created_at,
    )
    
    
    
    
@router.get(
    "/{organization_id}/members",
    response_model=list[OrganizationMemberResponse],
)
def get_organization_members(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Check that the organization exists
    organization = db.get(Organization, organization_id)

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # 2. Check that the current user belongs to this organization
    current_membership = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == current_user.id,
            Membership.organization_id == organization_id,
        )
    )

    if current_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    # 3. Get all members
    memberships = db.scalars(
        select(Membership)
        .where(Membership.organization_id == organization_id)
    ).all()

    # 4. Convert memberships into response objects
    return [
        OrganizationMemberResponse(
            user_id=membership.user.id,
            email=membership.user.email,
            full_name=membership.user.full_name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for membership in memberships
    ]
    
    
    
@router.patch(
    "/{organization_id}/members/{user_id}",
    response_model=OrganizationMemberResponse,
)
def update_member_role(
    organization_id: int,
    user_id: int,
    role_data: OrganizationMemberRoleUpdate,
    current_user: User = Depends(
        require_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    # 1. Find the member
    membership = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this organization",
        )

    # 2. Prevent changing the owner's role
    if membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The owner's role cannot be changed",
        )

    # 3. Admins cannot assign the owner role
    if (
        role_data.role == OrganizationRole.OWNER
        and membership.role != "owner"
    ):
        current_membership = db.scalar(
            select(Membership)
            .where(
                Membership.user_id == current_user.id,
                Membership.organization_id == organization_id,
            )
        )

        if current_membership.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can assign the owner role",
            )

    # 4. Update role
    membership.role = role_data.role.value

    db.commit()
    db.refresh(membership)

    return OrganizationMemberResponse(
        user_id=membership.user.id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        role=membership.role,
        joined_at=membership.created_at,
    )
    
    
    
@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_organization_member(
    organization_id: int,
    user_id: int,
    current_user: User = Depends(
        require_role("owner", "admin")
    ),
    db: Session = Depends(get_db),
):
    # 1. Find the membership
    membership = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in this organization",
        )

    # 2. Owner cannot be removed
    if membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The organization owner cannot be removed",
        )

    # 3. Remove the membership
    db.delete(membership)
    db.commit()

    return None