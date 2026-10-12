from app.services.text_extractor import extract_text

file_path = "uploads/1/7c623b9b21254efa92b024d6f94df589.pdf"

text = extract_text(file_path)

print("Extracted text:")
print(text[:2000])
print("\nTotal characters:", len(text))