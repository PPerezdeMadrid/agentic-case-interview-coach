import argparse
import json
import re
from pathlib import Path


SECTION_HEADINGS = {
    "High Level Plan of Attack",
    "Recommended Solution",
    "Lay Out Your Thoughts",
    "Question",
    "Key Findings",
    "Recommendations",
    "Dig Deeper: Gather Facts",
    "Dig Deeper: Gather Facts/Make Calculations",
    "Question and Background Information:",
    "Suggested Questions:",
    'Suggested "Excellent" Response:',
    "Summary Comments:",
    "Background",
    "Response",
    "General Summary Comments",
}

STANDARD_RECOMMENDATION_PREFIXES = (
    "drop ",
    "match ",
    "scale back",
    "educate ",
    "become ",
    "offer ",
    "diversify ",
    "focus on ",
    "change ",
    "look into ",
    "negotiate ",
    "further analyze ",
    "cater ",
    "move out",
    "where possible",
    "this firm should",
    "collaborate ",
)

OPEN_ENDED_GUIDANCE_PREFIXES = (
    "This is an example of a case",
    "In this type of case",
    "Here are some of the initial questions",
    "These answers will help",
    "This type of case can be very intimidating",
    "There is no one right way to approach cases",
)

FINAL_RECOMMENDATION_PROMPTS = {
    "harvard_fast_food_restaurant": "Based on your diagnosis, what should the burger restaurant do next?",
    "harvard_the_video_store": "Based on your diagnosis, what should the video store owners do next?",
    "harvard_hospital": "What would you recommend to restore the hospital to break-even?",
}

PROMPT_OVERRIDES = {
    "harvard_retailer": "A major retailer of clothing and household products has experienced sluggish growth and lower-than-expected profits over the last few years. The CEO has asked you to determine what is driving the problem across its 15 metropolitan and suburban mall stores and how to improve growth and profitability.",
    "harvard_juice_producer": "A juice producer historically sold 18-ounce cartons, then introduced 36-ounce plastic gallons. Sales have continued to grow by roughly 20 percent per year, but profits have steadily declined. Diagnose the issue and recommend what the owner should do.",
    "harvard_chemical_manufacturer": "A chemical manufacturer that produces preservatives for packaged foods has increased market share, yet profits have declined. The CEO has hired you to explain why profitability is falling and what actions to take.",
    "harvard_world_view": "World View, a Canadian cable TV company, entered the US Northeast expecting to capture a large and weakly contested market. Despite that opportunity, the business has failed to make a profit. Determine why and advise management on the next move.",
    "harvard_beer_brew": "Beer Brew, a major US beer company, entered the UK market two years ago and is still losing money. Despite high per-capita beer consumption, sales have been disappointing. Explain what is going wrong and what the company should change.",
    "harvard_wheeler_dealer": "Wheeler Dealer, an auto service chain, expanded aggressively by opening 15 additional stores. For the first time in more than a decade, profits have turned negative. Diagnose why the expansion hurt returns and recommend next steps.",
    "harvard_travel_agency": "A travel agency earns a 10 percent commission on bookings and generates about $1 million of profit before tax, while comparable agencies earn $2 million to $3.5 million. Identify why this agency is underperforming on profitability.",
    "harvard_hospital": "A 350-bed hospital that had historically generated a 1 to 3 percent operating gain is now projecting a $12 million operating loss and could run out of cash within five years. The client wants to identify the source of the downturn and restore the hospital to break-even without layoffs.",
    "harvard_the_video_store": "Two entrepreneurs opened a video rental store near HBS and enjoyed strong initial growth, but after about a year profits fell sharply. Diagnose what happened and determine what the owners should do.",
    "harvard_fast_food_restaurant": "A classmate who bought a fast-food burger restaurant says the business has been steadily losing money for the last three months. Diagnose the issue, decide where to investigate first, and recommend what the owner should do next.",
}

PAGE_HEADER_RE = re.compile(r"^HBS Case Interview Guide, Page \d+$")
PRACTICE_CASE_RE = re.compile(r"^Practice Case \d+ \(.+\)$")
HARVARD_CASE_RE = re.compile(r"^(harvard_.+?)_\d{2}_clean_raw$")
SCRIPT_DIR = Path(__file__).resolve().parent


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def format_lines(chunks: list[str]) -> str:
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def case_id_from_path(path: Path) -> str:
    match = HARVARD_CASE_RE.match(path.stem)
    if not match:
        raise ValueError(f"Unexpected Harvard raw filename: {path.name}")
    return match.group(1)


def case_title_from_id(case_id: str) -> str:
    title = case_id.removeprefix("harvard_").replace("_", " ")
    return title.title()


def split_page_chunks(text: str) -> list[str]:
    raw_chunks = [chunk.strip().replace("\n", " ") for chunk in text.split("\n\n") if chunk.strip()]
    cleaned_chunks = []

    for chunk in raw_chunks:
        chunk = normalize_whitespace(chunk)
        if not chunk or PAGE_HEADER_RE.match(chunk) or PRACTICE_CASE_RE.match(chunk):
            continue

        if (
            cleaned_chunks
            and chunk not in SECTION_HEADINGS
            and not chunk.startswith(("•", "o ", "Candidate:", "Interviewer:"))
            and cleaned_chunks[-1] not in SECTION_HEADINGS
            and not cleaned_chunks[-1].startswith(("•", "o ", "Candidate:", "Interviewer:"))
            and chunk[:1].islower()
        ):
            cleaned_chunks[-1] = f"{cleaned_chunks[-1]} {chunk}"
            continue

        cleaned_chunks.append(chunk)

    return cleaned_chunks


def flatten_pages(pages_data: list[dict]) -> list[dict]:
    flat_chunks = []

    for page in pages_data:
        for chunk in split_page_chunks(page["text"]):
            flat_chunks.append({
                "page": page["source_page"],
                "text": chunk,
            })

    return flat_chunks


def detect_case_format(chunks: list[dict]) -> str:
    texts = {chunk["text"] for chunk in chunks}

    if "Question and Background Information:" in texts:
        return "open_ended"

    if "Background" in texts and any(chunk["text"].startswith("Candidate:") for chunk in chunks):
        return "dialogue"

    return "standard"


def is_recommendation_chunk(text: str) -> bool:
    normalized = text.lstrip("• ").lstrip("o ").strip().lower()
    if normalized.startswith("["):
        return False
    return any(normalized.startswith(prefix) for prefix in STANDARD_RECOMMENDATION_PREFIXES)


def should_keep_prompt_chunk(text: str) -> bool:
    if len(text.split()) <= 2:
        return False

    if text[:1].islower() and "?" not in text:
        return False

    return True


def build_block(case_id: str, block_type: str, block_number: int, title: str, visible: bool, source_page: int, content: str) -> dict:
    return {
        "block_id": f"{case_id.removeprefix('harvard_')}_{block_type}_{block_number:03d}",
        "block_type": block_type,
        "title": title,
        "visible_to_candidate": visible,
        "image": None,
        "source_page": source_page,
        "content": content.strip(),
    }


def build_standard_case(case_id: str, case_title: str, chunks: list[dict]) -> dict:
    first_page = min(chunk["page"] for chunk in chunks)
    first_page_chunks = [chunk for chunk in chunks if chunk["page"] == first_page]
    later_chunks = [chunk for chunk in chunks if chunk["page"] != first_page]

    prompt_chunks = [
        chunk["text"]
        for chunk in first_page_chunks
        if chunk["text"] not in SECTION_HEADINGS
        and not chunk["text"].startswith(("•", "o ", "Candidate:", "Interviewer:"))
        and should_keep_prompt_chunk(chunk["text"])
    ]

    guidance_chunks = [
        chunk["text"]
        for chunk in first_page_chunks
        if chunk["text"] not in SECTION_HEADINGS
        and chunk["text"] not in prompt_chunks
    ]

    analysis_chunks = []
    recommendation_chunks = []

    for chunk in later_chunks:
        text = chunk["text"]
        if text in SECTION_HEADINGS:
            continue
        if is_recommendation_chunk(text):
            recommendation_chunks.append(text)
        else:
            analysis_chunks.append(text)

    blocks = [
        build_block(
            case_id=case_id,
            block_type="prompt",
            block_number=1,
            title=f"Prompt #1 - {case_title}",
            visible=True,
            source_page=first_page,
            content=PROMPT_OVERRIDES.get(case_id) or " ".join(prompt_chunks) or f"The client case is {case_title}. Diagnose the profitability issue.",
        ),
        build_block(
            case_id=case_id,
            block_type="guidance",
            block_number=1,
            title="Interviewer Guidance - Prompt #1",
            visible=False,
            source_page=first_page,
            content=format_lines(guidance_chunks) or "Use the casebook's suggested probing path to steer the interview.",
        ),
    ]

    if analysis_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="expected_analysis",
                block_number=1,
                title="Expected Analysis - Prompt #1",
                visible=False,
                source_page=later_chunks[0]["page"],
                content=format_lines(analysis_chunks),
            )
        )

    blocks.append(
        build_block(
            case_id=case_id,
            block_type="final_recommendation",
            block_number=1,
            title="Final Recommendation",
            visible=True,
            source_page=max(chunk["page"] for chunk in chunks),
            content=FINAL_RECOMMENDATION_PROMPTS.get(
                case_id,
                "Based on your analysis, what recommendation would you give the client?",
            ),
        )
    )

    if recommendation_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="guidance",
                block_number=2,
                title="Interviewer Guidance - Final Recommendation",
                visible=False,
                source_page=max(chunk["page"] for chunk in chunks),
                content=format_lines(recommendation_chunks),
            )
        )

    return {"case_content": blocks}


def build_open_ended_case(case_id: str, case_title: str, chunks: list[dict]) -> dict:
    prompt_chunks = []
    guidance_chunks = []
    analysis_chunks = []
    summary_chunks = []
    mode = "prompt"

    for chunk in chunks:
        text = chunk["text"]

        if text == 'Suggested "Excellent" Response:':
            mode = "analysis"
            continue
        if text == "Summary Comments:":
            mode = "summary"
            continue
        if text == "Suggested Questions:":
            mode = "guidance"
            continue
        if text in {"Question and Background Information:"}:
            mode = "prompt"
            continue
        if text in SECTION_HEADINGS:
            continue

        if mode == "prompt":
            if text.startswith(OPEN_ENDED_GUIDANCE_PREFIXES):
                guidance_chunks.append(text)
            elif text.startswith("•"):
                guidance_chunks.append(text)
            elif not should_keep_prompt_chunk(text):
                guidance_chunks.append(text)
            else:
                prompt_chunks.append(text)
        elif mode == "guidance":
            guidance_chunks.append(text)
        elif mode == "analysis":
            analysis_chunks.append(text)
        else:
            summary_chunks.append(text)

    first_page = min(chunk["page"] for chunk in chunks)
    last_page = max(chunk["page"] for chunk in chunks)

    blocks = [
        build_block(
            case_id=case_id,
            block_type="prompt",
            block_number=1,
            title=f"Prompt #1 - {case_title}",
            visible=True,
            source_page=first_page,
            content=PROMPT_OVERRIDES.get(case_id) or format_lines(prompt_chunks) or f"Work through the {case_title} diagnosis case.",
        ),
        build_block(
            case_id=case_id,
            block_type="guidance",
            block_number=1,
            title="Interviewer Guidance - Prompt #1",
            visible=False,
            source_page=first_page,
            content=format_lines(guidance_chunks),
        ),
    ]

    if analysis_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="expected_analysis",
                block_number=1,
                title="Expected Analysis - Prompt #1",
                visible=False,
                source_page=first_page + 1 if last_page > first_page else first_page,
                content=format_lines(analysis_chunks),
            )
        )

    blocks.append(
        build_block(
            case_id=case_id,
            block_type="final_recommendation",
            block_number=1,
            title="Final Recommendation",
            visible=True,
            source_page=last_page,
            content=FINAL_RECOMMENDATION_PROMPTS.get(
                case_id,
                "Based on your diagnosis, what should the client do next?",
            ),
        )
    )

    if summary_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="guidance",
                block_number=2,
                title="Interviewer Guidance - Final Recommendation",
                visible=False,
                source_page=last_page,
                content=format_lines(summary_chunks),
            )
        )

    return {"case_content": blocks}


def build_dialogue_case(case_id: str, case_title: str, chunks: list[dict]) -> dict:
    prompt_chunks = []
    guidance_chunks = []
    dialogue_chunks = []
    summary_chunks = []
    mode = "prompt"

    for chunk in chunks:
        text = chunk["text"]

        if text == "General Summary Comments":
            mode = "summary"
            continue

        if text == "Response":
            mode = "dialogue"
            continue

        if text in {"Background", "Question"} or text in SECTION_HEADINGS:
            continue

        if text.startswith("This question addresses company profitability"):
            guidance_chunks.append(text)
            continue

        if mode == "prompt":
            if text.startswith(("Candidate:", "Interviewer:")):
                mode = "dialogue"
                dialogue_chunks.append(text)
            else:
                prompt_chunks.append(text)
        elif mode == "dialogue":
            if text.startswith("The candidate should fully address"):
                mode = "summary"
                summary_chunks.append(text)
            else:
                dialogue_chunks.append(text)
        else:
            summary_chunks.append(text)

    first_page = min(chunk["page"] for chunk in chunks)
    last_page = max(chunk["page"] for chunk in chunks)

    blocks = [
        build_block(
            case_id=case_id,
            block_type="prompt",
            block_number=1,
            title=f"Prompt #1 - {case_title}",
            visible=True,
            source_page=first_page,
            content=PROMPT_OVERRIDES.get(case_id) or format_lines(prompt_chunks) or f"Work through the {case_title} profitability case.",
        ),
    ]

    if guidance_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="guidance",
                block_number=1,
                title="Interviewer Guidance - Prompt #1",
                visible=False,
                source_page=first_page,
                content=format_lines(guidance_chunks),
            )
        )

    if dialogue_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="expected_analysis",
                block_number=1,
                title="Expected Analysis - Prompt #1",
                visible=False,
                source_page=first_page,
                content=format_lines(dialogue_chunks),
            )
        )

    blocks.append(
        build_block(
            case_id=case_id,
            block_type="final_recommendation",
            block_number=1,
            title="Final Recommendation",
            visible=True,
            source_page=last_page,
            content=FINAL_RECOMMENDATION_PROMPTS.get(
                case_id,
                "What would you recommend to the client?",
            ),
        )
    )

    if summary_chunks:
        blocks.append(
            build_block(
                case_id=case_id,
                block_type="guidance",
                block_number=2,
                title="Interviewer Guidance - Final Recommendation",
                visible=False,
                source_page=last_page,
                content=format_lines(summary_chunks),
            )
        )

    return {"case_content": blocks}


def convert_case(raw_path: Path, output_dir: Path) -> str:
    case_id = case_id_from_path(raw_path)
    case_title = case_title_from_id(case_id)
    pages_data = json.loads(raw_path.read_text(encoding="utf-8"))
    chunks = flatten_pages(pages_data)
    case_format = detect_case_format(chunks)

    if case_format == "standard":
        structured = build_standard_case(case_id, case_title, chunks)
    elif case_format == "open_ended":
        structured = build_open_ended_case(case_id, case_title, chunks)
    else:
        structured = build_dialogue_case(case_id, case_title, chunks)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{case_id}.json"
    output_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return case_id


def update_casebooks_json(casebooks_path: Path, case_ids: list[str]):
    casebooks = json.loads(casebooks_path.read_text(encoding="utf-8"))

    for casebook in casebooks:
        if casebook.get("casebook_id") != "harvard_business_school_case_interview_guide":
            continue

        casebook["cases_ids"] = case_ids
        break

    casebooks_path.write_text(json.dumps(casebooks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Convert Harvard raw case extracts into Duke-style structured JSON.")
    parser.add_argument(
        "--input-dir",
        default="../script/output/harvard_casebook_probitability",
        help="Directory containing Harvard *_clean_raw.json files.",
    )
    parser.add_argument(
        "--output-dir",
        default="../data_processed/harvard_cases",
        help="Directory where structured Harvard case JSON files will be written.",
    )
    parser.add_argument(
        "--casebooks-json",
        default="../data_processed/casebooks.json",
        help="Path to casebooks.json for updating Harvard case ids.",
    )
    args = parser.parse_args()

    input_dir = (SCRIPT_DIR / args.input_dir).resolve() if not Path(args.input_dir).is_absolute() else Path(args.input_dir)
    output_dir = (SCRIPT_DIR / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    casebooks_path = (SCRIPT_DIR / args.casebooks_json).resolve() if not Path(args.casebooks_json).is_absolute() else Path(args.casebooks_json)

    raw_paths = sorted(input_dir.glob("harvard_*_clean_raw.json"))
    if not raw_paths:
        raise FileNotFoundError(f"No Harvard raw JSON files found in {input_dir}")

    case_ids = [convert_case(path, output_dir) for path in raw_paths]
    update_casebooks_json(casebooks_path, case_ids)

    print(f"Converted {len(case_ids)} Harvard cases into {output_dir}")
    print("Updated casebooks index:", casebooks_path)


if __name__ == "__main__":
    main()
