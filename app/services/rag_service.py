
from sqlalchemy.orm import Session

from app.services.semantic_search import semantic_search
from app.services.llm_service import generate_answer
from app.models.document import Document


def answer_question(
    db: Session,
    organization_id: int,
    question: str,
) -> dict:
    # 1. Retrieve relevant chunks from this organization
    chunks = semantic_search(
        db=db,
        organization_id=organization_id,
        query=question,
        top_k=5,
    )

    # 2. Handle cases where no chunks were found
    if not chunks:
        return {
            "answer": (
                "I could not find relevant information "
                "in the uploaded documents."
            ),
            "sources": [],
        }

    # 3. Prepare context for the LLM
    context_parts = []

    for chunk in chunks:
        context_parts.append(
            f"[Document ID: {chunk['document_id']}, "
            f"Chunk: {chunk['chunk_index']}]\n"
            f"{chunk['content']}"
        )

    context = "\n\n".join(context_parts)

    # 4. Generate an answer using Groq
    answer = generate_answer(
        question=question,
        context=context,
    )

    # 5. Fetch source filenames
    document_ids = list({
        chunk["document_id"] for chunk in chunks
    })

    documents = (
        db.query(Document)
        .filter(
            Document.organization_id == organization_id,
            Document.id.in_(document_ids),
        )
        .all()
    )

    filenames = {
        document.id: document.filename
        for document in documents
    }

    # 6. Return the answer and source references
    sources = [
        {
            "document_id": chunk["document_id"],
            "filename": filenames.get(
                chunk["document_id"],
                "Unknown document",
            ),
            "chunk_index": chunk["chunk_index"],
            "similarity": chunk["similarity"],
        }
        for chunk in chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
    }
