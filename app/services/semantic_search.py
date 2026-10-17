
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import generate_embedding


def semantic_search(
    db: Session,
    organization_id: int,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    # 1. Convert the user's question into a vector
    query_embedding = generate_embedding(query)

    # 2. Calculate cosine distance and find relevant chunks
    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    )

    results = (
        db.query(DocumentChunk, distance.label("distance"))
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .filter(
            Document.organization_id == organization_id,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(top_k)
        .all()
    )

    # 3. Return readable text, not just vectors
    return [
        {
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "similarity": round(1 - float(chunk_distance), 4),
        }
        for chunk, chunk_distance in results
    ]
