#from pathlib import Path
#from app.services.text_extractor import extract_text

#blocks = extract_text("uploads/1/a658e9d91f254226950197a904d6d471.docx")

#for i, block in enumerate(blocks):
#    if block.get("is_table"):
#        print(f"\nTABLE BLOCK {i}:")
#


from app.services.chunker import chunk_text
from app.services.text_extractor import extract_text

blocks = extract_text("uploads/1/a658e9d91f254226950197a904d6d471.docx")



for i, block in enumerate(blocks):
    text = block["text"]

    if any(word in text.lower() for word in [
        "compensated",
        "operational hours",
        "leadership staff",
        "intellectual assets",
    ]):
        print(f"\nBLOCK {i}:")
        print(repr(text))