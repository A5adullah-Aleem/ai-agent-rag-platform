
from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        device="cpu",
    )


def generate_embedding(text: str) -> list[float]:
    model = get_embedding_model()

    vector = model.encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return vector.tolist()


def generate_embeddings(
    texts: list[str],
    batch_size: int = 4,
) -> list[list[float]]:
    model = get_embedding_model()

    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return vectors.tolist()
