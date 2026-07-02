import argparse
import os
import re
import json
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
import pandas as pd


# -------------------------
# Configuration
# -------------------------

SKIP_PAGE_KEYWORDS = [
    "Behavioral Questions"
]

USEFUL_TABLE_KEYWORDS = [
    "sales",
    "average",
    "cost",
    "price",
    "revenue",
    "profit",
    "contracts",
    "option",
    "year"
]

MIN_IMAGE_WIDTH = 250
MIN_IMAGE_HEIGHT = 180
MIN_IMAGE_AREA = 80_000
PAGE_NUMBER_MIN_X_RATIO = 0.90
PAGE_NUMBER_MIN_Y_RATIO = 0.90
HEADER_MAX_Y_RATIO = 0.14
MULTI_COLUMN_MIN_BLOCKS = 2
BLOCK_MERGE_MAX_VERTICAL_GAP = 12
BLOCK_MERGE_MAX_X_DRIFT = 30
EXPECTED_CASEBOOK_CASE_COUNT = 18
SECTION_HEADING_MAX_WORDS = 8
SECTION_HEADING_MIN_ALPHA_CHARS = 4
LINE_BBOX_EPSILON = 0.5
NON_CASEBOOK_TITLES = {
    "industryoverviews",
    "resourcesfeedback",
}
PRACTICE_CASE_TITLE_RE = re.compile(
    r"^practice case\s+\d+\s*(?:\(([^)]+)\))?$",
    re.IGNORECASE,
)


# -------------------------
# Helpers
# -------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\u000c", "")
    text = text.replace("￾", "-")

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)

    return "\n".join(lines)


def normalize_inline_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def case_title_from_id(case_id: str) -> str:
    tail = case_id.split("_", 1)[-1]
    return tail.replace("_", " ").strip()


def slugify_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "_", ascii_text)
    ascii_text = re.sub(r"_+", "_", ascii_text).strip("_")
    return ascii_text or "untitled_case"


def normalize_case_title(text: str) -> str:
    text = normalize_inline_whitespace(text)
    return text.title() if text.isupper() else text


def load_case_titles_from_markdown(markdown_path: str | Path) -> list[str]:
    titles = []

    with open(markdown_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = normalize_inline_whitespace(raw_line.strip().lstrip("-*").strip())

            if not line:
                continue

            if line.lower().startswith("cases from "):
                continue

            titles.append(normalize_case_title(line))

    deduped_titles = list(dict.fromkeys(titles))

    if not deduped_titles:
        raise ValueError(f"No case titles found in markdown file: {markdown_path}")

    return deduped_titles


def should_skip_page(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in SKIP_PAGE_KEYWORDS)


def is_page_marker_line(text: str) -> bool:
    return bool(re.fullmatch(r"page\s+\d+", text.strip(), re.IGNORECASE))


def normalize_image_path(path: Path) -> str:
    """
    Store image path in the style you want for the JSON.
    Example: IMG/duke_yachtco_page_6_img_1.png
    """
    return f"IMG/{path.name}"


def extract_nonempty_lines_from_page(page) -> list[str]:
    lines = []

    for raw_line in page.get_text("text").splitlines():
        line = normalize_inline_whitespace(raw_line)
        if line and not is_page_marker_line(line):
            lines.append(line)

    return lines


def extract_text_lines_with_metadata(page) -> list[dict]:
    extracted_lines = []

    for block_index, block in enumerate(page.get_text("dict").get("blocks", [])):
        if block.get("type") != 0:
            continue

        for line_index, line in enumerate(block.get("lines", [])):
            spans = line.get("spans", [])
            raw_text = "".join(span.get("text", "") for span in spans)
            text = normalize_inline_whitespace(raw_text.replace("￾", "-").replace("\u000c", ""))

            if not text:
                continue

            x0, y0, x1, y1 = line["bbox"]
            is_bold = any("bold" in span.get("font", "").lower() for span in spans)

            extracted_lines.append({
                "block_index": block_index,
                "line_index": line_index,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": text,
                "is_bold": is_bold,
            })

    return extracted_lines


def is_useful_image(width: int, height: int) -> bool:
    """
    Filters out logos, icons, tiny decorative elements, etc.
    """
    area = width * height

    if width < MIN_IMAGE_WIDTH:
        return False

    if height < MIN_IMAGE_HEIGHT:
        return False

    if area < MIN_IMAGE_AREA:
        return False

    return True


def render_page_snapshot(pdf_doc, page_index: int, output_img_dir: Path, case_id: str) -> str:
    page = pdf_doc[page_index]
    image_filename = f"{case_id}_page_{page_index + 1}_full.png"
    image_path = output_img_dir / image_filename

    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pixmap.save(image_path)

    return normalize_image_path(image_path)


def extract_useful_images_from_page(pdf_doc, page_index: int, output_img_dir: Path, case_id: str):
    page = pdf_doc[page_index]
    image_list = page.get_images(full=True)

    image_paths = []

    for img_index, img in enumerate(image_list):
        xref = img[0]

        try:
            base_image = pdf_doc.extract_image(xref)
        except Exception:
            continue

        image_bytes = base_image.get("image")
        image_ext = base_image.get("ext", "png")
        width = base_image.get("width", 0)
        height = base_image.get("height", 0)

        if not image_bytes:
            continue

        if not is_useful_image(width, height):
            continue

        image_filename = f"{case_id}_page_{page_index + 1}_img_{img_index + 1}.{image_ext}"
        image_path = output_img_dir / image_filename

        with open(image_path, "wb") as f:
            f.write(image_bytes)

        image_paths.append(normalize_image_path(image_path))

    return image_paths


def is_probable_page_number(text: str, x0: float, y0: float, page_rect) -> bool:
    cleaned = text.strip()
    return (
        cleaned.isdigit()
        and len(cleaned) <= 3
        and x0 >= page_rect.width * PAGE_NUMBER_MIN_X_RATIO
        and y0 >= page_rect.height * PAGE_NUMBER_MIN_Y_RATIO
    )


def is_generic_top_header(text: str, y0: float, page_rect, page_number: int, case_title: str) -> bool:
    if page_number <= 1:
        return False

    if y0 > page_rect.height * HEADER_MAX_Y_RATIO:
        return False

    return canonicalize_text(text) == canonicalize_text(case_title)


def split_block_lines(text: str) -> list[str]:
    lines = []

    for raw_line in text.splitlines():
        line = normalize_inline_whitespace(raw_line.replace("￾", "-").replace("\u000c", ""))
        if line:
            lines.append(line)

    if not lines:
        return []

    merged_lines = [lines[0]]

    for line in lines[1:]:
        prev = merged_lines[-1]

        if re.match(
            r"^(?:Prompt #\d+:|Interviewer Guidance.*:|Option \d+:|Recommendation\b|Exhibit #?\d* Guidance:|Analysis:)",
            line
        ):
            merged_lines.append(line)
            continue

        if prev in {"-", "–", "•"}:
            merged_lines[-1] = f"{prev} {line}"
            continue

        if re.fullmatch(r"\d+\)", prev):
            merged_lines[-1] = f"{prev} {line}"
            continue

        if prev.endswith("-") and line and line[0].islower():
            merged_lines[-1] = f"{prev}{line}"
            continue

        if re.match(r"^(?:[•\-–]\s+|\d+\))", line):
            merged_lines.append(line)
            continue

        if prev.endswith(":") and len(prev.split()) <= 4:
            merged_lines.append(line)
            continue

        if line.endswith(":") and len(line.split()) <= 4:
            merged_lines.append(line)
            continue

        merged_lines[-1] = f"{prev} {line}"

    return merged_lines


def sort_blocks_in_reading_order(blocks: list[dict], page_rect) -> list[dict]:
    if not blocks:
        return []

    midpoint = page_rect.width / 2
    left_blocks = [block for block in blocks if block["x1"] <= midpoint]
    right_blocks = [block for block in blocks if block["x0"] >= midpoint]

    if len(left_blocks) < MULTI_COLUMN_MIN_BLOCKS or len(right_blocks) < MULTI_COLUMN_MIN_BLOCKS:
        return sorted(blocks, key=lambda block: (block["y0"], block["x0"]))

    prelude_cutoff = min(
        min(block["y0"] for block in left_blocks),
        min(block["y0"] for block in right_blocks),
    ) + 20

    prelude_blocks = []
    left_column_blocks = []
    right_column_blocks = []
    trailing_blocks = []

    for block in blocks:
        if block["x0"] < midpoint < block["x1"] and block["y1"] <= prelude_cutoff:
            prelude_blocks.append(block)
        elif block["x1"] <= midpoint:
            left_column_blocks.append(block)
        elif block["x0"] >= midpoint:
            right_column_blocks.append(block)
        else:
            trailing_blocks.append(block)

    ordered_blocks = []
    ordered_blocks.extend(sorted(prelude_blocks, key=lambda block: (block["y0"], block["x0"])))
    ordered_blocks.extend(sorted(left_column_blocks, key=lambda block: (block["y0"], block["x0"])))
    ordered_blocks.extend(sorted(right_column_blocks, key=lambda block: (block["y0"], block["x0"])))
    ordered_blocks.extend(sorted(trailing_blocks, key=lambda block: (block["y0"], block["x0"])))

    return ordered_blocks


def merge_adjacent_blocks(blocks: list[dict]) -> list[dict]:
    if not blocks:
        return []

    merged_blocks = [blocks[0].copy()]

    for block in blocks[1:]:
        prev = merged_blocks[-1]
        vertical_gap = block["y0"] - prev["y1"]
        same_column = abs(block["x0"] - prev["x0"]) <= BLOCK_MERGE_MAX_X_DRIFT

        if (
            same_column
            and 0 <= vertical_gap <= BLOCK_MERGE_MAX_VERTICAL_GAP
            and not starts_with_standalone_heading(block["text"])
        ):
            prev["text"] = "\n".join(split_block_lines(f"{prev['text']}\n{block['text']}"))
            prev["x0"] = min(prev["x0"], block["x0"])
            prev["y0"] = min(prev["y0"], block["y0"])
            prev["x1"] = max(prev["x1"], block["x1"])
            prev["y1"] = max(prev["y1"], block["y1"])
            continue

        merged_blocks.append(block.copy())

    return merged_blocks


def starts_with_standalone_heading(text: str) -> bool:
    first_line = text.splitlines()[0].strip() if text else ""

    return bool(re.match(
        r"^(?:Prompt #\d+:|Interviewer Guidance.*:|Option \d+:|Recommendation|Exhibit #?\d* Guidance:|Analysis:)$",
        first_line
    ))


def looks_like_uppercase_case_cover(title: str) -> bool:
    letters_only = re.sub(r"[^A-Za-z]+", "", title)
    return bool(letters_only) and title == title.upper() and len(title.split()) >= 2


def looks_like_section_heading(text: str, is_bold: bool) -> bool:
    if not is_bold:
        return False

    cleaned = normalize_inline_whitespace(text)
    letters_only = re.sub(r"[^A-Za-z]+", "", cleaned)

    if len(letters_only) < SECTION_HEADING_MIN_ALPHA_CHARS:
        return False

    if cleaned != cleaned.upper():
        return False

    if len(cleaned.split()) > SECTION_HEADING_MAX_WORDS:
        return False

    return True


def detect_case_start_title(lines: list[str], next_lines: list[str]) -> str | None:
    if not lines:
        return None

    first_line = lines[0]
    first_line_canonical = canonicalize_text(first_line)
    joined_top = " ".join(lines[:8]).lower()

    if first_line_canonical in NON_CASEBOOK_TITLES:
        return None

    for line in lines[:6]:
        practice_case_match = PRACTICE_CASE_TITLE_RE.match(line)
        if practice_case_match:
            practice_case_title = practice_case_match.group(1) or line
            return normalize_case_title(practice_case_title)

    if first_line.lower().startswith("mock case:") and len(lines) > 1:
        return normalize_case_title(lines[1])

    if "provided by bcg" in joined_top:
        title_parts = []
        for line in lines[:4]:
            line_lower = line.lower()
            if "provided by" in line_lower or line.isdigit():
                break
            title_parts.append(line)

        if title_parts:
            return normalize_case_title(" ".join(title_parts).title())

    if "(provided by" in joined_top and "accenture" in joined_top:
        title = lines[0].split("(provided by")[0].strip()
        if title:
            return normalize_case_title(title)

    if "quantitative level" in joined_top and "qualitative level" in joined_top:
        return normalize_case_title(first_line)

    title_candidate_parts = []
    for line in lines[:3]:
        if line.isdigit() or line == "•":
            break
        title_candidate_parts.append(line)

    title_candidate = normalize_inline_whitespace(" ".join(title_candidate_parts))

    if not title_candidate:
        return None

    if looks_like_uppercase_case_cover(title_candidate) and next_lines:
        next_title = normalize_case_title(next_lines[0])
        if canonicalize_text(next_title) == canonicalize_text(title_candidate):
            return normalize_case_title(title_candidate.title())

    return None


def detect_case_ranges(pdf_path: str, expected_case_count: int = EXPECTED_CASEBOOK_CASE_COUNT):
    pdf_doc = fitz.open(pdf_path)
    page_lines = [extract_nonempty_lines_from_page(page) for page in pdf_doc]
    case_starts = []

    for page_index, lines in enumerate(page_lines):
        next_lines = page_lines[page_index + 1] if page_index + 1 < len(page_lines) else []
        title = detect_case_start_title(lines, next_lines)

        if not title:
            continue

        case_starts.append({
            "case_number": len(case_starts) + 1,
            "title": title,
            "start_page": page_index + 1,
        })

    for index, case_info in enumerate(case_starts):
        next_start = case_starts[index + 1]["start_page"] if index + 1 < len(case_starts) else pdf_doc.page_count + 1
        case_info["end_page"] = next_start - 1
        case_info["slug"] = slugify_text(case_info["title"])

    pdf_doc.close()

    if expected_case_count and len(case_starts) != expected_case_count:
        raise ValueError(
            f"Expected {expected_case_count} cases in the casebook, but detected {len(case_starts)}."
        )

    return case_starts


def detect_heading_sections(pdf_path: str) -> list[dict]:
    pdf_doc = fitz.open(pdf_path)
    headings = []

    for page_index, page in enumerate(pdf_doc):
        for line in extract_text_lines_with_metadata(page):
            if not looks_like_section_heading(line["text"], line["is_bold"]):
                continue

            title = normalize_case_title(line["text"])
            headings.append({
                "title": title,
                "slug": slugify_text(title),
                "start_page": page_index + 1,
                "start_y": line["y0"],
                "content_start_y": line["y1"] + LINE_BBOX_EPSILON,
            })

    if not headings:
        pdf_doc.close()
        raise ValueError(f"No bold uppercase section headings detected in {pdf_path}.")

    for index, section in enumerate(headings):
        next_heading = headings[index + 1] if index + 1 < len(headings) else None
        section["end_page"] = next_heading["start_page"] if next_heading else pdf_doc.page_count
        section["end_y"] = next_heading["start_y"] - LINE_BBOX_EPSILON if next_heading else None

    pdf_doc.close()
    return headings


def filter_sections_by_allowed_titles(sections: list[dict], allowed_titles: list[str]) -> list[dict]:
    allowed_lookup = {
        canonicalize_text(title): title
        for title in allowed_titles
    }
    matched_counts = {key: 0 for key in allowed_lookup}
    filtered_sections = []

    for section in sections:
        canonical_title = canonicalize_text(section["title"])
        allowed_title = allowed_lookup.get(canonical_title)

        if not allowed_title:
            continue

        matched_counts[canonical_title] += 1
        filtered_sections.append({
            **section,
            "title": allowed_title,
            "slug": slugify_text(allowed_title),
        })

    missing_titles = [
        allowed_lookup[key]
        for key, count in matched_counts.items()
        if count == 0
    ]
    duplicate_titles = [
        allowed_lookup[key]
        for key, count in matched_counts.items()
        if count > 1
    ]

    if missing_titles or duplicate_titles:
        errors = []

        if missing_titles:
            errors.append(f"Missing allowed case headings: {', '.join(missing_titles)}")

        if duplicate_titles:
            errors.append(f"Duplicate allowed case headings: {', '.join(duplicate_titles)}")

        raise ValueError("; ".join(errors))

    for case_number, section in enumerate(filtered_sections, start=1):
        section["case_number"] = case_number

    return filtered_sections


def extract_page_text_segment(
    page,
    page_number: int,
    case_title: str,
    start_y: float | None = None,
    end_y: float | None = None,
    skip_case_title_heading: bool = False,
) -> str:
    filtered_blocks = []

    for raw_block in page.get_text("dict").get("blocks", []):
        if raw_block.get("type") != 0:
            continue

        selected_lines = []
        x0_values = []
        y0_values = []
        x1_values = []
        y1_values = []

        for line in raw_block.get("lines", []):
            spans = line.get("spans", [])
            raw_text = "".join(span.get("text", "") for span in spans)
            line_text = normalize_inline_whitespace(raw_text.replace("￾", "-").replace("\u000c", ""))

            if not line_text:
                continue

            x0, y0, x1, y1 = line["bbox"]

            if start_y is not None and y1 <= start_y:
                continue

            if end_y is not None and y0 >= end_y:
                continue

            if (
                skip_case_title_heading
                and canonicalize_text(line_text) == canonicalize_text(case_title)
                and any("bold" in span.get("font", "").lower() for span in spans)
            ):
                continue

            if is_probable_page_number(line_text, x0, y0, page.rect):
                continue

            if is_page_marker_line(line_text):
                continue

            if is_generic_top_header(line_text, y0, page.rect, page_number, case_title):
                continue

            selected_lines.append(line_text)
            x0_values.append(x0)
            y0_values.append(y0)
            x1_values.append(x1)
            y1_values.append(y1)

        if not selected_lines:
            continue

        block_text = "\n".join(split_block_lines("\n".join(selected_lines)))

        filtered_blocks.append({
            "x0": min(x0_values),
            "y0": min(y0_values),
            "x1": max(x1_values),
            "y1": max(y1_values),
            "text": block_text,
        })

    ordered_blocks = sort_blocks_in_reading_order(filtered_blocks, page.rect)
    merged_blocks = merge_adjacent_blocks(ordered_blocks)
    ordered_text = [block["text"] for block in merged_blocks if block["text"]]

    return "\n\n".join(ordered_text).strip()


def extract_page_text(page, page_number: int, case_title: str) -> str:
    raw_blocks = page.get_text("blocks")
    filtered_blocks = []

    for raw_block in raw_blocks:
        x0, y0, x1, y1, raw_text, *_ = raw_block
        lines = split_block_lines(raw_text)

        if not lines:
            continue

        block_text = "\n".join(lines)

        if is_probable_page_number(block_text, x0, y0, page.rect):
            continue

        if is_page_marker_line(block_text):
            continue

        if is_generic_top_header(block_text, y0, page.rect, page_number, case_title):
            continue

        filtered_blocks.append({
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "text": block_text,
        })

    ordered_blocks = sort_blocks_in_reading_order(filtered_blocks, page.rect)
    merged_blocks = merge_adjacent_blocks(ordered_blocks)
    ordered_text = [block["text"] for block in merged_blocks if block["text"]]

    return "\n\n".join(ordered_text).strip()


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    """
    Manual markdown converter so you do not depend on tabulate.
    """
    df = df.fillna("")
    headers = [str(col).strip() for col in df.columns]
    rows = df.astype(str).values.tolist()

    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"

    for row in rows:
        cleaned_row = [cell.replace("\n", " ").strip() for cell in row]
        md += "| " + " | ".join(cleaned_row) + " |\n"

    return md


def looks_like_real_table(df: pd.DataFrame) -> bool:
    """
    Avoids treating text boxes as real tables.
    """
    if df.empty:
        return False

    rows, cols = df.shape

    # Most fake tables from slides are one-column text boxes.
    if cols < 2:
        return False

    # Very tiny tables are often layout artefacts.
    if rows < 2:
        return False

    non_empty_per_row = df.apply(
        lambda row: sum(bool(str(cell).strip()) for cell in row),
        axis=1
    )

    # Text boxes often become 2-column artefacts with only one populated cell per row.
    if non_empty_per_row.max() < 2:
        return False

    if non_empty_per_row.mean() < 1.8:
        return False

    text = " ".join(df.astype(str).fillna("").values.flatten()).lower()

    keyword_hits = sum(1 for kw in USEFUL_TABLE_KEYWORDS if kw in text)
    numeric_cells = sum(
        bool(re.search(r"\d", str(cell)))
        for cell in df.astype(str).fillna("").values.flatten()
    )

    # A useful table in casebooks usually has numbers or business keywords.
    if keyword_hits == 0 and numeric_cells < 3:
        return False

    return True


def clean_table_dataframe(table) -> pd.DataFrame:
    df = pd.DataFrame(table)

    # Drop fully empty rows/columns
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")
    df = df.fillna("")

    if df.empty:
        return df

    # Use first row as header if it looks like a header.
    first_row = [str(x).strip() for x in df.iloc[0].tolist()]
    has_header_text = sum(bool(re.search(r"[A-Za-z]", x)) for x in first_row) >= max(1, len(first_row) // 2)

    if len(df) > 1 and has_header_text:
        df.columns = first_row
        df = df.iloc[1:]

    # Remove duplicated whitespace/newlines in cells
    df = df.map(lambda x: re.sub(r"\s+", " ", str(x)).strip())

    return df


def extract_real_tables_from_page(pdf_path: str, page_number: int):
    """
    Extracts only tables that look like actual data tables.
    page_number is 1-indexed.
    """
    tables_markdown = []

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]

        tables = page.extract_tables({
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 5,
            "snap_tolerance": 3,
            "join_tolerance": 3,
        })

        for table_index, table in enumerate(tables):
            if not table:
                continue

            df = clean_table_dataframe(table)

            if not looks_like_real_table(df):
                continue

            markdown_table = dataframe_to_markdown(df)

            tables_markdown.append({
                "table_id": f"table_{table_index + 1}",
                "markdown": markdown_table
            })

    return tables_markdown


def infer_page_block_type(text: str) -> str:
    """
    Rough classification useful for your later JSON conversion.
    """
    lower = text.lower()

    if "exhibit" in lower and "calculation" in lower:
        return "solution"

    if "exhibit" in lower and ("steel price" in lower or "option 1" in lower):
        return "exhibit"

    if "recommendation" in lower and "ceo" in lower:
        return "final_recommendation"

    if "interviewer guidance" in lower and "good candidate" in lower:
        return "expected_analysis"

    if "prompt #" in lower:
        return "prompt"

    return "text"


def should_render_snapshot(block_type: str, text: str) -> bool:
    lower = text.lower()
    first_line = text.splitlines()[0].lower() if text else ""

    if block_type == "exhibit":
        return True

    return "exhibit" in first_line and ("analysis:" in lower or "guidance:" in lower)


# -------------------------
# Main extraction
# -------------------------

def write_intermediate_outputs(
    pages_data,
    output_dir: Path,
    case_id: str,
    display_title: str | None = None,
    write_markdown: bool = True,
):
    raw_json_path = output_dir / f"{case_id}_clean_raw.json"
    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(pages_data, f, indent=2, ensure_ascii=False)

    print("Extraction complete.")
    print(f"Clean JSON saved to: {raw_json_path}")

    if write_markdown:
        markdown_path = output_dir / f"{case_id}_clean.md"
        write_markdown_intermediate(
            pages_data=pages_data,
            markdown_path=markdown_path,
            case_id=case_id,
            display_title=display_title,
        )
        print(f"Clean Markdown saved to: {markdown_path}")

    return raw_json_path

def extract_pdf_to_intermediate(
    pdf_path: str,
    case_id: str,
    output_dir: str = "output",
    skip_behavioral: bool = True,
    start_page: int | None = None,
    end_page: int | None = None,
    case_title: str | None = None,
    write_markdown: bool = True,
    extract_tables: bool = True,
    extract_page_snapshots: bool = True,
):
    pdf_path = str(pdf_path)
    output_dir = Path(output_dir)
    img_dir = output_dir / "IMG"

    output_dir.mkdir(parents=True, exist_ok=True)
    if extract_page_snapshots:
        img_dir.mkdir(parents=True, exist_ok=True)

    pdf_doc = fitz.open(pdf_path)
    case_title = case_title or case_title_from_id(case_id)
    first_page = start_page or 1
    last_page = end_page or pdf_doc.page_count

    if first_page < 1 or last_page > pdf_doc.page_count or first_page > last_page:
        pdf_doc.close()
        raise ValueError(
            f"Invalid page range for {case_id}: start_page={first_page}, end_page={last_page}, total_pages={pdf_doc.page_count}"
        )

    pages_data = []

    for page_index in range(first_page - 1, last_page):
        page_number = page_index + 1
        page = pdf_doc[page_index]

        text = extract_page_text(page, page_number=page_number, case_title=case_title)

        if skip_behavioral and should_skip_page(text):
            continue

        block_type = infer_page_block_type(text)
        page_image = None

        if extract_page_snapshots and should_render_snapshot(block_type, text):
            page_image = render_page_snapshot(
                pdf_doc=pdf_doc,
                page_index=page_index,
                output_img_dir=img_dir,
                case_id=case_id
            )

        tables = []
        if extract_tables:
            tables = extract_real_tables_from_page(
                pdf_path=pdf_path,
                page_number=page_number
            )

        page_data = {
            "source_page": page_number,
            "block_type_guess": block_type,
            "text": text,
            "image": page_image,
            "page_image": page_image,
            "tables": tables
        }

        pages_data.append(page_data)

    pdf_doc.close()

    write_intermediate_outputs(
        pages_data=pages_data,
        output_dir=output_dir,
        case_id=case_id,
        display_title=case_title,
        write_markdown=write_markdown,
    )

    if extract_page_snapshots:
        print(f"Useful images saved to: {img_dir}")

    return pages_data


def extract_casebook_to_intermediates(
    pdf_path: str,
    output_dir: str = "output/duke_casebook_2017_profitability_18",
    skip_behavioral: bool = True,
    casebook_prefix: str = "duke",
    expected_case_count: int = EXPECTED_CASEBOOK_CASE_COUNT,
    write_markdown: bool = True,
    extract_tables: bool = True,
    extract_page_snapshots: bool = True,
):
    detected_cases = detect_case_ranges(pdf_path, expected_case_count=expected_case_count)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extracted_cases = []

    for case_info in detected_cases:
        case_id = f"{casebook_prefix}_{case_info['slug']}_{case_info['case_number']:02d}"

        extract_pdf_to_intermediate(
            pdf_path=pdf_path,
            case_id=case_id,
            output_dir=str(output_dir),
            skip_behavioral=skip_behavioral,
            start_page=case_info["start_page"],
            end_page=case_info["end_page"],
            case_title=case_info["title"],
            write_markdown=write_markdown,
            extract_tables=extract_tables,
            extract_page_snapshots=extract_page_snapshots,
        )

        extracted_cases.append({
            **case_info,
            "case_id": case_id,
            "json_path": str(output_dir / f"{case_id}_clean_raw.json"),
        })
        if write_markdown:
            extracted_cases[-1]["markdown_path"] = str(output_dir / f"{case_id}_clean.md")

    print(f"Detected and extracted {len(extracted_cases)} cases from the casebook:")
    for case_info in extracted_cases:
        print(
            f"{case_info['case_number']:02d}. {case_info['title']} "
            f"(pages {case_info['start_page']}-{case_info['end_page']}) -> {case_info['case_id']}"
        )

    return extracted_cases


def extract_heading_casebook_to_intermediates(
    pdf_path: str,
    allowed_case_titles: list[str],
    output_dir: str = "output/agsm_casebook_2002",
    casebook_prefix: str = "agsm",
    write_markdown: bool = False,
):
    detected_sections = detect_heading_sections(pdf_path)
    selected_cases = filter_sections_by_allowed_titles(detected_sections, allowed_case_titles)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extracted_cases = []
    pdf_doc = fitz.open(pdf_path)

    for case_info in selected_cases:
        case_id = f"{casebook_prefix}_{case_info['slug']}_{case_info['case_number']:02d}"
        pages_data = []

        for page_number in range(case_info["start_page"], case_info["end_page"] + 1):
            page = pdf_doc[page_number - 1]
            start_y = case_info["content_start_y"] if page_number == case_info["start_page"] else None
            end_y = case_info["end_y"] if page_number == case_info["end_page"] else None

            text = extract_page_text_segment(
                page=page,
                page_number=page_number,
                case_title=case_info["title"],
                start_y=start_y,
                end_y=end_y,
                skip_case_title_heading=(page_number == case_info["start_page"]),
            )

            if not text:
                continue

            pages_data.append({
                "source_page": page_number,
                "block_type_guess": "text",
                "text": text,
                "image": None,
                "page_image": None,
                "tables": [],
            })

        write_intermediate_outputs(
            pages_data=pages_data,
            output_dir=output_dir,
            case_id=case_id,
            display_title=case_info["title"],
            write_markdown=write_markdown,
        )

        extracted_cases.append({
            **case_info,
            "case_id": case_id,
            "json_path": str(output_dir / f"{case_id}_clean_raw.json"),
        })
        if write_markdown:
            extracted_cases[-1]["markdown_path"] = str(output_dir / f"{case_id}_clean.md")

    pdf_doc.close()

    print(f"Detected and extracted {len(extracted_cases)} allowlisted cases from the casebook:")
    for case_info in extracted_cases:
        print(
            f"{case_info['case_number']:02d}. {case_info['title']} "
            f"(pages {case_info['start_page']}-{case_info['end_page']}) -> {case_info['case_id']}"
        )

    return extracted_cases


def write_markdown_intermediate(pages_data, markdown_path: Path, case_id: str, display_title: str | None = None):
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(f"# {display_title or case_id}\n\n")

        for page in pages_data:
            f.write("---\n\n")
            f.write(f"## Source page {page['source_page']}\n\n")
            f.write(f"**Block type guess:** `{page['block_type_guess']}`\n\n")

            if page.get("page_image"):
                f.write("### Page Snapshot\n\n")
                f.write(f"![Source page snapshot]({page['page_image']})\n\n")

            if page["text"]:
                f.write("### Extracted text\n\n")
                f.write(page["text"])
                f.write("\n\n")

            if page["tables"]:
                f.write("### Extracted real tables\n\n")
                for table in page["tables"]:
                    f.write(f"#### {table['table_id']}\n\n")
                    f.write(table["markdown"])
                    f.write("\n\n")

def main():
    parser = argparse.ArgumentParser(description="Extract case PDFs into JSON and Markdown.")
    parser.add_argument("--mode", choices=["single", "casebook"], default="casebook")
    parser.add_argument("--pdf-path", default="../Duke-Casebook-2017-Profitability-18.pdf")
    parser.add_argument("--output-dir", default="output/duke_casebook_2017_profitability_18")
    parser.add_argument("--case-id", default="duke_yachtco")
    parser.add_argument("--casebook-prefix", default="duke")
    parser.add_argument("--expected-case-count", type=int, default=EXPECTED_CASEBOOK_CASE_COUNT)
    parser.add_argument("--case-list-path")
    parser.add_argument("--start-page", type=int)
    parser.add_argument("--end-page", type=int)
    parser.add_argument(
        "--write-markdown",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--extract-tables",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--extract-page-snapshots",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--skip-behavioral",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    if args.mode == "single":
        extract_pdf_to_intermediate(
            pdf_path=args.pdf_path,
            case_id=args.case_id,
            output_dir=args.output_dir,
            skip_behavioral=args.skip_behavioral,
            start_page=args.start_page,
            end_page=args.end_page,
            write_markdown=args.write_markdown,
            extract_tables=args.extract_tables,
            extract_page_snapshots=args.extract_page_snapshots,
        )
        return

    if args.case_list_path:
        allowed_case_titles = load_case_titles_from_markdown(args.case_list_path)
        extract_heading_casebook_to_intermediates(
            pdf_path=args.pdf_path,
            allowed_case_titles=allowed_case_titles,
            output_dir=args.output_dir,
            casebook_prefix=args.casebook_prefix,
            write_markdown=args.write_markdown,
        )
        return

    extract_casebook_to_intermediates(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        skip_behavioral=args.skip_behavioral,
        casebook_prefix=args.casebook_prefix,
        expected_case_count=args.expected_case_count,
        write_markdown=args.write_markdown,
        extract_tables=args.extract_tables,
        extract_page_snapshots=args.extract_page_snapshots,
    )


if __name__ == "__main__":
    main()
