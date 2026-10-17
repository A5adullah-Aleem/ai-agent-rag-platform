
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

    text = block["text"].strip()

    if not text or len(text) > 120:
        return False

    source = block.get("source")
    style = (block.get("style") or "").strip().lower()

    # 1. DOCX: use paragraph styles.
    if source == "docx":
        if re.fullmatch(r"heading\s+\d+", style):
            return True

        if style == "subtitle":
            return True

    # Avoid treating complete sentences as headings.
    if text.endswith((".", "?", "!", ";")):
        return False

    words = text.split()

    if len(words) > 12:
        return False

    # 2. Numbered headings: e.g. "2.1 System Design".
    if NUMBERED_HEADING.match(text):
        return True

    # 3. PDF: use font size and boldness.
    if source == "pdf":
        font_size = block.get("font_size")

    # Strong evidence: noticeably larger font.
        if (
            font_size is not None
            and median_font_size is not None
            and font_size >= median_font_size + 2
            and len(words) <= 12
        ):
        
            return True

    # Boldness alone is weak evidence.
    # Don't classify short bold table labels as headings.
    if (
        block.get("is_bold")
        and 2 <= len(words) <= 8
        and len(text) >= 12
        and not text.endswith((".", "?", "!", ";", ":"))
    ):
        return True

    # 4. TXT and DOCX without heading styles:
    # accept short, standalone uppercase headings.
    if source in {"txt", "docx"}:
        if (
            len(words) <= 8
            and text.isupper()
            and any(char.isalpha() for char in text)
        ):
            return True

    # Otherwise, don't guess.
    return False


def split_into_sections(blocks: list[dict]) -> list[dict]:
    """Group blocks under detected headings."""

    pdf_sizes = [
        block["font_size"]
        for block in blocks
        if block.get("source") == "pdf"
        and block.get("font_size") is not None
    ]

    median_font_size = median(pdf_sizes) if pdf_sizes else None

    sections = []
    current_title = None
    current_lines = []

    for block in blocks:
        text = block["text"].strip()

        if not text:
            continue

        if _is_heading(block, median_font_size):
            if current_lines:
                sections.append({
                    "section_title": current_title,
                    "text": "\n".join(current_lines).strip(),
                })

            current_title = text
            current_lines = [text]
        else:
            current_lines.append(text)

    if current_lines:
        sections.append({
            "section_title": current_title,
            "text": "\n".join(current_lines).strip(),
        })

    return [
        section
        for section in sections
        if section["text"]
    ]


def chunk_text(
    blocks: list[dict],
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[dict]:
    """Create chunks while preserving section metadata."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be between 0 and chunk_size - 1"
        )

    sections = split_into_sections(blocks)
    chunks = []

    for section in sections:
        content = section["text"]
        start = 0

        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunk_content = content[start:end].strip()

            if chunk_content:
                chunks.append({
                    "content": chunk_content,
                    "section_title": section["section_title"],
                })

            if end == len(content):
                break

            start = end - overlap

    return chunks
