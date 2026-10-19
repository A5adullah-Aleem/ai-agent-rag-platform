
import re
from statistics import median


NUMBERED_HEADING = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*\.?\s+[A-Z]"
    r"|chapter\s+\d+\b"
    r"|section\s+\d+\b"
    r")",
    re.IGNORECASE,
)


def _is_heading(
    block: dict,
    median_font_size: float | None,
) -> bool:
    """Detect likely headings using document structure and formatting."""

    # Table rows must never be treated as section headings.
    if block.get("is_table"):
        return False

    text = block["text"].strip()

    if not text or len(text) > 120:
        return False

    source = block.get("source")
    style = (block.get("style") or "").strip().lower()

    if source == "docx":
        if re.fullmatch(r"heading\s+\d+", style):
            return True
        if style == "subtitle":
            return True

    if text.endswith((".", "?", "!", ";")):
        return False

    words = text.split()

    if len(words) > 12:
        return False

    if NUMBERED_HEADING.match(text):
        return True

    if source == "pdf":
        font_size = block.get("font_size")

        if (
            font_size is not None
            and median_font_size is not None
            and font_size >= median_font_size + 2
        ):
            return True

        if (
            block.get("is_bold")
            and 2 <= len(words) <= 8
            and len(text) >= 12
            and not text.endswith((".", "?", "!", ";", ":"))
        ):
            return True

    if source in {"txt", "docx"}:
        if (
            len(words) <= 8
            and text.isupper()
            and any(char.isalpha() for char in text)
        ):
            return True

    return False


def split_into_sections(blocks: list[dict]) -> list[dict]:
    """Group extracted blocks under detected headings."""

    pdf_sizes = [
        block["font_size"]
        for block in blocks
        if block.get("source") == "pdf"
        and block.get("font_size") is not None
    ]

    median_font_size = median(pdf_sizes) if pdf_sizes else None

    sections = []
    current_title = None
    current_blocks = []

    for block in blocks:
        text = block.get("text", "").strip()

        if not text:
            continue

        if _is_heading(block, median_font_size):
            if current_blocks:
                sections.append({
                    "section_title": current_title,
                    "blocks": current_blocks,
                })

            current_title = text
            current_blocks = [block]
        else:
            current_blocks.append(block)

    if current_blocks:
        sections.append({
            "section_title": current_title,
            "blocks": current_blocks,
        })

    return [
        section for section in sections
        if section["blocks"]
    ]


def _split_text(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split normal text into overlapping chunks."""

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Prefer a natural boundary when it is reasonably close.
        if end < len(text):
            boundary = max(
                text.rfind("\n", start, end),
                text.rfind(" ", start, end),
            )

            if boundary > start + chunk_size // 2:
                end = boundary

        content = text[start:end].strip()

        if content:
            chunks.append(content)

        if end >= len(text):
            break

        next_start = end - overlap

        # Avoid getting stuck if a boundary creates a tiny chunk.
        start = max(next_start, start + 1)

    return chunks


def _chunk_table_rows(
    rows: list[str],
    chunk_size: int,
) -> list[str]:
    """Group complete table rows without splitting them unnecessarily."""

    chunks = []
    current_rows = []
    current_length = 0

    for row in rows:
        row_length = len(row)

        if current_rows and current_length + 1 + row_length > chunk_size:
            chunks.append("\n".join(current_rows))
            current_rows = []
            current_length = 0

        # Keep an individual row intact, even if it exceeds chunk_size.
        current_rows.append(row)
        current_length += row_length + (1 if len(current_rows) > 1 else 0)

    if current_rows:
        chunks.append("\n".join(current_rows))

    return chunks


def chunk_text(
    blocks: list[dict],
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[dict]:
    """Create section-aware chunks while preserving table rows."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be between 0 and chunk_size - 1"
        )

    sections = split_into_sections(blocks)
    chunks = []

    for section in sections:
        section_title = section["section_title"]
        pending_text = []

        def flush_text():
            if not pending_text:
                return

            text = "\n".join(pending_text).strip()
            pending_text.clear()

            for content in _split_text(text, chunk_size, overlap):
                chunks.append({
                    "content": content,
                    "section_title": section_title,
                })

        index = 0
        section_blocks = section["blocks"]

        while index < len(section_blocks):
            block = section_blocks[index]

            if block.get("is_table"):
                flush_text()

                # Collect consecutive table rows together.
                table_rows = []

                while (
                    index < len(section_blocks)
                    and section_blocks[index].get("is_table")
                ):
                    row_text = section_blocks[index]["text"].strip()

                    if row_text:
                        table_rows.append(row_text)

                    index += 1

                for content in _chunk_table_rows(
                    table_rows, chunk_size
                ):
                    chunks.append({
                        "content": content,
                        "section_title": section_title,
                    })

                continue

            text = block["text"].strip()

            if text:
                pending_text.append(text)

            index += 1

        flush_text()

    return chunks
