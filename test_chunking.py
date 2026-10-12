
from app.services.chunker import chunk_text

sample_text = "This is a sample document. " * 150

chunks = chunk_text(sample_text)

print("Total chunks:", len(chunks))

for index, chunk in enumerate(chunks):
    print(f"\nChunk {index + 1}")
    print("Characters:", len(chunk))
    print(chunk[:100])