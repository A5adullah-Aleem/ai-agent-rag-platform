
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.membership import Membership
from app.models.conversation import Conversation
from app.models.chat_message import ChatMessage
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ChatMessageResponse,
    ChatMessageCreate
)
from app.services.rag_service import answer_question

router = APIRouter(tags=["Conversations"])


def verify_membership(
    db: Session,
    organization_id: int,
    user_id: int,
) -> None:
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
        )
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )


def get_user_conversation(
    db: Session,
    organization_id: int,
    conversation_id: int,
    user_id: int,
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.user_id == user_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return conversation


@router.post(
    "/organizations/{organization_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    organization_id: int,
    request: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_membership(db, organization_id, current_user.id)

    title = request.title.strip() or "New Chat"

    conversation = Conversation(
        organization_id=organization_id,
        user_id=current_user.id,
        title=title[:255],
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


@router.get(
    "/organizations/{organization_id}/conversations",
    response_model=list[ConversationResponse],
)
def list_conversations(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_membership(db, organization_id, current_user.id)

    conversations = db.scalars(
        select(Conversation)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
        .order_by(desc(Conversation.updated_at), desc(Conversation.id))
    ).all()

    return conversations


@router.get(
    "/organizations/{organization_id}/conversations/{conversation_id}/messages",
    response_model=list[ChatMessageResponse],
)
def list_messages(
    organization_id: int,
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_membership(db, organization_id, current_user.id)

    get_user_conversation(
        db,
        organization_id,
        conversation_id,
        current_user.id,
    )

    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()

    return messages


@router.delete(
    "/organizations/{organization_id}/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    organization_id: int,
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_membership(db, organization_id, current_user.id)

    conversation = get_user_conversation(
        db,
        organization_id,
        conversation_id,
        current_user.id,
    )

    db.delete(conversation)
    db.commit()

    return None





@router.post(
    "/organizations/{organization_id}/conversations/{conversation_id}/messages",
    response_model=list[ChatMessageResponse],
)
def send_message(
    organization_id: int,
    conversation_id: int,
    request: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Verify organization membership
    verify_membership(db, organization_id, current_user.id)

    # 2. Verify conversation ownership
    conversation = get_user_conversation(
        db,
        organization_id,
        conversation_id,
        current_user.id,
    )

    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty",
        )

    # 3. Save user's message first
    user_message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=question,
    )

    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    try:
        # 4. Generate the RAG response
        rag_result = answer_question(
            db=db,
            organization_id=organization_id,
            question=question,
        )

        # 5. Save assistant answer and sources
        assistant_message = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=rag_result["answer"],
            sources=rag_result["sources"],
        )

        db.add(assistant_message)

        # Update conversation timestamp and title
        if conversation.title == "New Chat":
            conversation.title = question[:60]

        db.commit()
        db.refresh(assistant_message)

        return [user_message, assistant_message]

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate or save the AI response",
        )
