
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.services.text_extractor import extract_text
from app.db.database import get_db
from app.models.document import Document
from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.models.membership import Membership

router = APIRouter(prefix="/organizations", tags=["Documents"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/{organization_id}/documents",
    response_model=DocumentResponse,
)
async def upload_document(
    organization_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify organization access
    membership = db.query(Membership).filter(
    Membership.user_id == current_user.id,
    Membership.organization_id == organization_id,
    ).first()

    if membership is None:
        raise HTTPException(
        status_code=403,
        detail="You are not a member of this organization",
    )

    # Validate file extension
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOCX, and TXT files are allowed",
        )

    # Read and validate file size
    contents = await file.read(MAX_FILE_SIZE + 1)

    if not contents:
        raise HTTPException(status_code=400, detail="File is empty")

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Maximum file size is 10 MB")

    # Generate a unique storage filename
    storage_name = f"{uuid4().hex}{suffix}"
    organization_dir = UPLOAD_DIR / str(organization_id)
    organization_dir.mkdir(parents=True, exist_ok=True)
    file_path = organization_dir / storage_name

    try:
        file_path.write_bytes(contents)

        document = Document(
            organization_id=organization_id,
            uploaded_by_id=current_user.id,
            filename=file.filename or storage_name,
            file_path=str(file_path),
            status="uploaded",
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        return document

    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    
    


@router.get(
    "/{organization_id}/documents",
    response_model=list[DocumentResponse],
)
def list_documents(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify organization membership
    membership = db.query(Membership).filter(
        Membership.user_id == current_user.id,
        Membership.organization_id == organization_id,
    ).first()

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    # Fetch documents belonging to this organization
    documents = (
        db.query(Document)
        .filter(Document.organization_id == organization_id)
        .order_by(Document.created_at.desc())
        .all()
    )

    return documents


@router.delete(
    "/{organization_id}/documents/{document_id}",
)
def delete_document(
    organization_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Verify organization membership
    membership = db.query(Membership).filter(
        Membership.user_id == current_user.id,
        Membership.organization_id == organization_id,
    ).first()

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    # 2. Find document inside this organization
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.organization_id == organization_id,
    ).first()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # 3. Delete the database record
    file_path = Path(document.file_path)

    try:
        db.delete(document)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # 4. Remove the physical file after successful commit
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        # Database record is already deleted; file cleanup may need retrying.
        pass

    return {
        "message": "Document deleted successfully",
        "document_id": document_id,
    }
    
    
    
    
@router.post(
    "/{organization_id}/documents/{document_id}/process"
)
def process_document(
    organization_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify organization membership
    membership = db.query(Membership).filter(
        Membership.user_id == current_user.id,
        Membership.organization_id == organization_id,
    ).first()

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    # Find the document within this organization
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.organization_id == organization_id,
    ).first()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:
        text = extract_text(document.file_path)

        document.status = "processed"
        db.commit()

        return {
            "message": "Document processed successfully",
            "document_id": document.id,
            "status": document.status,
            "characters_extracted": len(text),
            "text_preview": text[:500],
        }

    except ValueError as exc:
        document.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Document processing failed",
        )