
from pathlib import Path
from uuid import uuid4
from app.models.document_chunk import DocumentChunk
from app.services.chunker import chunk_text
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.services.text_extractor import extract_text
from app.db.database import get_db
from app.models.document import Document
from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.models.membership import Membership
from app.services.embedding_service import generate_embedding
from app.schemas.document import SearchRequest
from app.services.semantic_search import semantic_search
from app.services.embedding_service import generate_embeddings

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
    
    
    
    

@router.post("/{organization_id}/documents/{document_id}/process")
def process_document(
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

    try:
        # 3. Extract text and create chunks
        blocks = extract_text(document.file_path)
        chunks = chunk_text(blocks)

        if not chunks:
            raise ValueError("No chunks generated from document")

        # 4. Delete previous chunks before reprocessing
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document.id
        ).delete(synchronize_session=False)

        total_chunks = len(chunks)
        batch_size = 4

        # 5. Generate embeddings and save in small batches
        for start in range(0, total_chunks, batch_size):
            batch = chunks[start:start + batch_size]

            texts = [chunk["content"] for chunk in batch]
            embeddings = generate_embeddings(
                texts,
                batch_size=batch_size,
            )

            chunk_records = []

            for offset, (chunk, embedding) in enumerate(
                zip(batch, embeddings)
            ):
                chunk_records.append(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=start + offset,
                        content=chunk["content"],
                        section_title=chunk["section_title"],
                        embedding=embedding,
                    )
                )

            db.add_all(chunk_records)
            db.flush()

            # Release references to this batch
            del chunk_records, embeddings, texts, batch

        # 6. Update document status
        document.status = "processed"
        db.commit()

        return {
            "message": "Document processed successfully",
            "document_id": document.id,
            "status": document.status,
            "characters_extracted": sum(
                len(block["text"]) for block in blocks
            ),
            "total_chunks": total_chunks,
            "embeddings_generated": total_chunks,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Document processing failed",
        )





@router.post("/{organization_id}/search")
def search_organization_documents(
    organization_id: int,
    request: SearchRequest,
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

    # Search the organization's document chunks
    results = semantic_search(
        db=db,
        organization_id=organization_id,
        query=request.query,
        top_k=request.top_k,
    )

    return {
        "query": request.query,
        "total_results": len(results),
        "results": results,
    }
