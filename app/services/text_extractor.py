from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    elif extension == ".docx":
        doc = DocxDocument(str(path))
        text = "\n".join(
            paragraph.text
            for paragraph in doc.paragraphs
        )

    elif extension == ".txt":
        text = path.read_text(encoding="utf-8-sig")

    else:
        raise ValueError("Unsupported file format")

    text = text.strip()

    if not text:
        raise ValueError(
            "No extractable text found in the document"
        )

    return text