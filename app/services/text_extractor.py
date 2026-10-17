
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document as DocxDocument


def extract_text(file_path: str) -> list[dict]:
    """
    Extract document content while preserving structural cues.

    Each returned block contains:
    - text
    - source format
    - bold information
    - font size, when available
    - paragraph style, when available
    """

    path = Path(file_path)
    extension = path.suffix.lower()
    blocks = []

    if extension == ".pdf":
        with fitz.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                page_data = page.get_text("dict")

                for block in page_data["blocks"]:
                    if "lines" not in block:
                        continue

                    for line in block["lines"]:
                        spans = line.get("spans", [])

                        text = "".join(
                            span.get("text", "")
                            for span in spans
                        ).strip()

                        if not text:
                            continue

                        font_sizes = [
                            span.get("size", 0)
                            for span in spans
                            if span.get("text", "").strip()
                        ]

                        is_bold = any(
                            "bold" in span.get("font", "").lower()
                            or bool(span.get("flags", 0) & 16)
                            for span in spans
                        )

                        blocks.append({
                            "text": text,
                            "source": "pdf",
                            "page": page_number,
                            "is_bold": is_bold,
                            "font_size": max(font_sizes, default=None),
                            "style": None,
                        })

    elif extension == ".docx":
        doc = DocxDocument(str(path))

        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()

            if not text:
                continue

            style_name = (
                paragraph.style.name
                if paragraph.style is not None
                else None
            )

            font_sizes = [
                run.font.size.pt
                for run in paragraph.runs
                if run.text.strip() and run.font.size is not None
            ]

            is_bold = any(
                run.bold is True
                for run in paragraph.runs
                if run.text.strip()
            )

            blocks.append({
                "text": text,
                "source": "docx",
                "page": None,
                "is_bold": is_bold,
                "font_size": max(font_sizes, default=None),
                "style": style_name,
            })

    elif extension == ".txt":
        text = path.read_text(encoding="utf-8-sig")

        for line in text.splitlines():
            line = line.strip()

            if not line:
                continue

            blocks.append({
                "text": line,
                "source": "txt",
                "page": None,
                "is_bold": False,
                "font_size": None,
                "style": None,
            })

    else:
        raise ValueError("Unsupported file format")

    if not blocks:
        raise ValueError(
            "No extractable text found in the document"
        )

    return blocks