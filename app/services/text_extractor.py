
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document as DocxDocument


def extract_text(file_path: str) -> list[dict]:
    """
    Extract document content while preserving structural cues.
    PDF tables are converted into readable, header-aware rows.
    """
    path = Path(file_path)
    extension = path.suffix.lower()
    blocks = []

    if extension == ".pdf":
        with fitz.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                page_data = page.get_text("dict")
                tables = page.find_tables().tables

                # Save detected table areas so their text is not
                # extracted twice from the normal PDF text.
                table_areas = [
                    fitz.Rect(table.bbox) for table in tables
                ]

                page_items = []

                # Extract normal text outside detected tables.
                for block in page_data["blocks"]:
                    if "lines" not in block:
                        continue

                    block_rect = fitz.Rect(block["bbox"])

                    # Skip text blocks that overlap a detected table.
                    if any(
                        block_rect.intersects(area)
                        for area in table_areas
                    ):
                        continue

                    for line in block["lines"]:
                        spans = line.get("spans", [])
                        text = "".join(
                            span.get("text", "") for span in spans
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

                        page_items.append((
                            line["bbox"][1],
                            {
                                "text": text,
                                "source": "pdf",
                                "page": page_number,
                                "is_bold": is_bold,
                                "font_size": max(font_sizes, default=None),
                                "style": None,
                            },
                        ))

                # Extract tables as header-aware text rows.
                for table in tables:
                    rows = table.extract()

                    if not rows:
                        continue

                    headers = [
                        str(cell).strip() if cell is not None else ""
                        for cell in rows[0]
                    ]

                    table_y = table.bbox[1]

                    page_items.append((
                        table_y,
                        {
                            "text": f"Table on page {page_number}",
                            "source": "pdf",
                            "page": page_number,
                            "is_bold": False,
                            "font_size": None,
                            "style": None,
                        },
                    ))

                    for row_index, row in enumerate(rows[1:], start=1):
                        values = [
                            str(cell).strip() if cell is not None else ""
                            for cell in row
                        ]

                        fields = []
                        for col_index, value in enumerate(values):
                            if not value:
                                continue

                            header = (
                                headers[col_index]
                                if col_index < len(headers)
                                else ""
                            )

                            if header:
                                fields.append(f"{header}: {value}")
                            else:
                                fields.append(value)

                        if not fields:
                            continue

                        row_text = " | ".join(fields)

                        page_items.append((
                            table_y + row_index * 0.01,
                            {
                                "text": row_text,
                                "source": "pdf",
                                "page": page_number,
                                "is_bold": False,
                                "font_size": None,
                                "style": None,
                                "is_table": True,
                            },
                        ))

                # Preserve approximate reading order on each page.
                page_items.sort(key=lambda item: item[0])
                blocks.extend(item[1] for item in page_items)

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
        raise ValueError("No extractable text found in the document")

    return blocks
