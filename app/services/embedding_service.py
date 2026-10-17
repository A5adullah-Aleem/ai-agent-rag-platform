
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)


def generate_embedding(text: str) -> list[float]:
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()