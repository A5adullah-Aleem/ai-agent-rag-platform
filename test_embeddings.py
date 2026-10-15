from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

text = "This is a sample document chunk."

embedding = model.encode(text)

print("Vector dimensions:", len(embedding))
print("First 5 values:", embedding[:5])