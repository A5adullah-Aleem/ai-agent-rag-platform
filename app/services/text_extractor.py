
from pathlib import Path
from collections import Counter

import pymupdf
from docx import Document as DocxDocument
from docx.text.paragraph import Paragraph
from docx.table import Table


def iter_docx_blocks(parent):
    """Yield DOCX paragraphs and tables in their original document order."""
    body = parent.element.body

    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def clean_cell(cell):
    """Convert a table cell into readable text."""
    if cell is None:
        return ""

    return " ".join(str(cell).split()).strip()


def format_table_rows(rows):
    """Convert table rows into header-aware text."""
    if not rows:
        return []

    cleaned_rows = [
        [clean_cell(cell) for cell in row]
        for row in rows
    ]

    # Find the first non-empty row to use as column headers.
    header_index = next(
        (
            index
            for index, row in enumerate(cleaned_rows)
            if any(row)
        ),
        None,
    )

    if header_index is None:
        return []

    headers = cleaned_rows[header_index]
    formatted_rows = []

    for row in cleaned_rows[header_index + 1:]:
        fields = []

        for index, value in enumerate(row):
            if not value:
                continue

            header = (
                headers[index]
                if index < len(headers)
                else ""
            )

            fields.append(
                f"{header}: {value}" if header else value
            )

        if fields:
            formatted_rows.append(" | ".join(fields))

    return formatted_rows


def detect_column_split(lines, page_width):
    """
    Estimate the vertical gutter between two PDF columns.

    Returns None when a reliable gutter cannot be identified.
    """
    usable_lines = [
        line
        for line in lines
        if line["x1"] - line["x0"] <= page_width * 0.72
    ]

    if len(usable_lines) < 6:
        return None

    # Search the central part of the page for the widest empty gutter.
    candidates = []
    start = int(page_width * 0.30)
    end = int(page_width * 0.70)

    for x in range(start, end, 2):
        crosses = any(
            line["x0"] < x < line["x1"]
            for line in usable_lines
        )

        if not crosses:
            candidates.append(x)

    if not candidates:
        return None

    gaps = []
    gap_start = previous = candidates[0]

    for x in candidates[1:]:
        if x > previous + 2:
            gaps.append((gap_start, previous))
            gap_start = x

        previous = x

    gaps.append((gap_start, previous))

    valid_gaps = []

    for left, right in gaps:
        if right - left < 12:
            continue

        midpoint = (left + right) / 2

        left_count = sum(
            line["x1"] <= midpoint
            for line in usable_lines
        )
        right_count = sum(
            line["x0"] >= midpoint
            for line in usable_lines
        )

        if left_count >= 3 and right_count >= 3:
            valid_gaps.append((right - left, midpoint))

    if not valid_gaps:
        return None

    return max(valid_gaps)[1]


def extract_text(file_path: str) -> list[dict]:
    """
    Extract PDF, DOCX, and TXT content for a RAG pipeline.

    Preserves structural metadata, improves two-column PDF ordering,
    extracts tables, and filters repeated page headers and footers.
    """
    path = Path(file_path)
    extension = path.suffix.lower()
    blocks = []

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    # ---------------------------------------------------------
    # PDF
    # ---------------------------------------------------------
    if extension == ".pdf":
        with pymupdf.open(str(path)) as pdf:
            page_data_list = []
            repeated_candidates = Counter()

            # First pass: collect page text and detect repeated
            # text located near page headers or footers.
            for page_number, page in enumerate(pdf, start=1):
                page_data = page.get_text("dict")
                raw_lines = []

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

                        x0, y0, x1, y1 = line["bbox"]

                        raw_lines.append({
                            "text": text,
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1,
                            "spans": spans,
                        })

                        # Only consider text close to the page edges.
                        if y0 < 35 or y1 > page.rect.height - 35:
                            repeated_candidates[text.casefold()] += 1

                page_data_list.append({
                    "page_number": page_number,
                    "page": page,
                    "lines": raw_lines,
                })

            total_pages = len(page_data_list)

            # Require the same edge text on multiple pages.
            repeated_headers_footers = {
                text
                for text, count in repeated_candidates.items()
                if count >= 2 and total_pages >= 2
            }

            # Second pass: extract content and order it.
            for page_info in page_data_list:
                page = page_info["page"]
                page_number = page_info["page_number"]
                raw_lines = page_info["lines"]

                try:
                    tables = page.find_tables().tables
                except (AttributeError, RuntimeError):
                    tables = []

                table_areas = [
                    pymupdf.Rect(table.bbox)
                    for table in tables
                ]

                # Exclude text inside detected tables to avoid duplicates.
                normal_lines = []

                for line in raw_lines:
                    text = line["text"]

                    if (
                        text.casefold() in repeated_headers_footers
                        and (
                            line["y0"] < 35
                            or line["y1"] > page.rect.height - 35
                        )
                    ):
                        continue

                    line_rect = pymupdf.Rect(
                        line["x0"],
                        line["y0"],
                        line["x1"],
                        line["y1"],
                    )

                    if any(
                        line_rect.intersects(area)
                        for area in table_areas
                    ):
                        continue

                    normal_lines.append(line)

                split_x = detect_column_split(
                    normal_lines,
                    page.rect.width,
                )

                page_items = []

                for line in normal_lines:
                    spans = line["spans"]
                    text = line["text"]

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

                    width = line["x1"] - line["x0"]
                    is_wide = width > page.rect.width * 0.72

                    if split_x is None:
                        column = 0
                    elif is_wide:
                        column = -1
                    elif line["x1"] <= split_x:
                        column = 0
                    elif line["x0"] >= split_x:
                        column = 1
                    else:
                        column = 0 if (
                            line["x0"] + line["x1"]
                        ) / 2 < split_x else 1

                    page_items.append({
                        "y": line["y0"],
                        "column": column,
                        "wide": is_wide,
                        "block": {
                            "text": text,
                            "source": "pdf",
                            "page": page_number,
                            "is_bold": is_bold,
                            "font_size": max(font_sizes, default=None),
                            "style": None,
                        },
                    })

                # Store each detected table as one coherent block.
                # This prevents table rows from interleaving with
                # paragraphs in the neighbouring PDF column.
                for table in tables:
                    rows = table.extract()
                    formatted_rows = format_table_rows(rows)

                    if not formatted_rows:
                        continue

                    table_text = (
                        f"Table on page {page_number}\n"
                        + "\n".join(formatted_rows)
                    )

                    table_x0, table_y0, table_x1, _ = table.bbox
                    table_width = table_x1 - table_x0
                    table_is_wide = (
                        table_width > page.rect.width * 0.72
                    )

                    if split_x is None:
                        table_column = 0
                    elif table_is_wide:
                        table_column = -1
                    else:
                        table_column = (
                            0
                            if (table_x0 + table_x1) / 2 < split_x
                            else 1
                        )

                    page_items.append({
                        "y": table_y0,
                        "column": table_column,
                        "wide": table_is_wide,
                        "block": {
                            "text": table_text,
                            "source": "pdf",
                            "page": page_number,
                            "is_bold": False,
                            "font_size": None,
                            "style": None,
                            "is_table": True,
                        },
                    })

                # If a full-width item separates sections, finish the
                # current column band before adding that item.
                page_items.sort(key=lambda item: item["y"])

                ordered_items = []
                current_band = []

                def flush_band():
                    current_band.sort(
                        key=lambda item: (
                            item["column"],
                            item["y"],
                        )
                    )
                    ordered_items.extend(current_band)
                    current_band.clear()

                for item in page_items:
                    if item["column"] == -1:
                        flush_band()
                        ordered_items.append(item)
                    else:
                        current_band.append(item)

                flush_band()

                blocks.extend(
                    item["block"] for item in ordered_items
                )

    # ---------------------------------------------------------
    # DOCX
    # ---------------------------------------------------------
    elif extension == ".docx":
        doc = DocxDocument(str(path))

        for item in iter_docx_blocks(doc):
            if isinstance(item, Paragraph):
                paragraph = item
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
                    if run.text.strip()
                    and run.font.size is not None
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

            elif isinstance(item, Table):
                rows = [
                    [cell.text for cell in row.cells]
                    for row in item.rows
                ]

                formatted_rows = format_table_rows(rows)

                for row_text in formatted_rows:
                    blocks.append({
                        "text": row_text,
                        "source": "docx",
                        "page": None,
                        "is_bold": False,
                        "font_size": None,
                        "style": None,
                        "is_table": True,
                    })

    # ---------------------------------------------------------
    # TXT
    # ---------------------------------------------------------
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
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    if not blocks:
        raise ValueError(
            "No extractable text found in the document"
        )

    return blocks
