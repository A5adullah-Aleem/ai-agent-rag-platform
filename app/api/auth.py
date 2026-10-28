from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.core.security import create_access_token, verify_password
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.api.dependencies import get_current_user
from app.schemas.password_reset import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.core.config import settings
from app.models.password_reset_token import PasswordResetToken
from app.core.email import send_password_reset_email
from app.core.config import settings


import secrets
import hashlib
from datetime import datetime, timedelta, timezone

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(
        select(User).where(User.email == user_data.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=hash_password(user_data.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user




@router.post("/login")
def login(
    user_data: UserLogin,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.email == user_data.email)
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        user_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
    
    
@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user






@router.post("/forgot-password")
def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    # Same response for existing and non-existing emails.
    response = {
        "message": (
            "If an account exists for this email, "
            "a password reset link will be sent."
        )
    }

    user = db.scalar(
        select(User).where(User.email == request.email)
    )

    if not user:
        return response

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    reset_record = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    try:
        # Invalidate previous reset links for this user.
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id
        ).delete(synchronize_session=False)

        db.add(reset_record)
        db.commit()

        reset_url = (
            f"{settings.FRONTEND_URL.rstrip('/')}"
            f"/reset-password?token={raw_token}"
        )

        send_password_reset_email(user.email, reset_url)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send the reset email. Please try again later.",
        )

    return response


@router.post("/reset-password")
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(
        request.token.encode("utf-8")
    ).hexdigest()

    reset_record = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
    )

    now = datetime.now(timezone.utc)

    if (
        not reset_record
        or reset_record.used_at is not None
        or reset_record.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or expired. Request a new link.",
        )

    user = db.get(User, reset_record.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or expired. Request a new link.",
        )

    user.password_hash = hash_password(request.new_password)
    reset_record.used_at = now

    # Invalidate every other outstanding reset token for this user.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.id != reset_record.id,
    ).delete(synchronize_session=False)

    db.commit()

    return {"message": "Password reset successful. You can now sign in."}