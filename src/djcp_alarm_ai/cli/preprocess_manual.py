import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[3]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "tg_manual" / "tg_manual_source.jsonl"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "tg_manual" / "tg_manual_search_chunks.jsonl"
)
MAX_CHUNK_CHARS = 1200

BRACKET_HEADING = re.compile(r"^\[([^\]]+)\]$")
NUMBERED_ITEM = re.compile(r"^(\d+)\)\s*(.+)$")


@dataclass(frozen=True)
class TextSection:
    heading: str
    lines: tuple[str, ...]


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def preprocess_records(
    records: list[dict],
    *,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> list[dict]:
    chunks: list[dict] = []
    for record in records:
        content = str(record["content"]).strip()
        if len(content) <= max_chunk_chars:
            chunks.extend(_keep_or_reject(record, max_chunk_chars=max_chunk_chars))
        else:
            chunks.extend(
                _split_long_record(record, max_chunk_chars=max_chunk_chars)
            )
    _validate_chunks(chunks, max_chunk_chars=max_chunk_chars)
    return chunks


def write_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = "\n".join(
        json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
        for chunk in chunks
    )
    path.write_text(value + "\n", encoding="utf-8")


def _split_long_record(record: dict, *, max_chunk_chars: int) -> list[dict]:
    prefix_lines, sections = _structural_sections(record["content"])

    segments: list[tuple[str | None, list[str]]] = []
    if _trim_blank_lines(prefix_lines):
        segments.append((None, prefix_lines))
    segments.extend((section.heading, list(section.lines)) for section in sections)
    if not segments:  # 구조적 소제목이 전혀 없는 장문
        segments = [(None, record["content"].splitlines())]

    produced: list[tuple[str, str]] = []
    for subheading, lines in segments:
        title = (
            _join_title(record["title"], subheading)
            if subheading
            else record["title"]
        )
        body = "\n".join(_trim_blank_lines(lines)).strip()
        if not body:
            continue
        if len(body) <= max_chunk_chars:
            produced.append((title, body))
            continue
        for window in _split_by_lines(
            lines,
            max_chunk_chars=max_chunk_chars,
            chunk_id=record["chunk_id"],
        ):
            produced.append((title, window))

    if not produced:
        return _keep_or_reject(record, max_chunk_chars=max_chunk_chars)

    return [
        _child_record(
            record,
            chunk_id=f"{record['chunk_id']}-s{index:02d}",
            title=title,
            content=content,
        )
        for index, (title, content) in enumerate(produced, start=1)
    ]


def _split_by_lines(
    lines: list[str],
    *,
    max_chunk_chars: int,
    chunk_id: str,
) -> list[str]:
    windows: list[str] = []
    current: list[str] = []
    current_len = 0
    for raw_line in lines:
        for piece in _atomic_pieces(
            raw_line.strip(),
            max_chunk_chars=max_chunk_chars,
            chunk_id=chunk_id,
        ):
            addition = len(piece) + (1 if current else 0)
            if current and current_len + addition > max_chunk_chars:
                windows.append("\n".join(current))
                current = [piece]
                current_len = len(piece)
            else:
                current.append(piece)
                current_len += addition
    if current:
        windows.append("\n".join(current))
    return windows


def _atomic_pieces(
    line: str,
    *,
    max_chunk_chars: int,
    chunk_id: str,
) -> list[str]:
    if not line:
        return []
    if len(line) <= max_chunk_chars:
        return [line]
    pieces = [
        piece.strip()
        for piece in re.split(r"(?<=[.다요])\s+", line)
        if piece.strip()
    ]
    for piece in pieces:
        if len(piece) > max_chunk_chars:
            raise ValueError(
                f"chunk exceeds {max_chunk_chars} chars without a safe heading: "
                f"{chunk_id}"
            )
    return pieces


def _structural_sections(
    content: str,
) -> tuple[list[str], list[TextSection]]:
    sections: list[TextSection] = []
    prefix_lines: list[str] = []
    current_group: str | None = None
    current_heading: str | None = None
    current_lines: list[str] = []
    found_heading = False

    def flush() -> None:
        nonlocal current_lines
        body = _trim_blank_lines(current_lines)
        if not body:
            current_lines = []
            return
        if current_heading is None:
            prefix_lines.extend(body)
        else:
            sections.append(
                TextSection(heading=current_heading, lines=tuple(body))
            )
        current_lines = []

    lines = [raw_line.strip() for raw_line in content.splitlines()]
    for index, line in enumerate(lines):
        bracket_match = BRACKET_HEADING.match(line)
        if bracket_match:
            flush()
            current_group = bracket_match.group(1).strip()
            current_heading = current_group
            found_heading = True
            continue

        if _is_standalone_heading(line, _next_nonblank(lines, index + 1)):
            flush()
            current_heading = _join_title(current_group, line)
            found_heading = True
            continue

        current_lines.append(line)
    flush()

    if not found_heading:
        return [], []
    return prefix_lines, sections


def _is_standalone_heading(line: str, next_line: str | None) -> bool:
    if not line or len(line) > 70:
        return False
    if NUMBERED_ITEM.match(line) or line.startswith("-"):
        return False
    if any(mark in line for mark in (".", ",", ":")):
        return False
    return bool(next_line and next_line.startswith("-"))


def _next_nonblank(lines: list[str], start: int) -> str | None:
    for line in lines[start:]:
        if line:
            return line
    return None


def _keep_or_reject(record: dict, *, max_chunk_chars: int) -> list[dict]:
    content = str(record["content"]).strip()
    if len(content) > max_chunk_chars:
        raise ValueError(
            f"chunk exceeds {max_chunk_chars} chars without a safe heading: "
            f"{record['chunk_id']}"
        )
    return [
        {
            "chunk_id": record["chunk_id"],
            "parent_chunk_id": None,
            "section_no": record["section_no"],
            "pdf_page": record["pdf_page"],
            "manual_page": record["manual_page"],
            "title": record["title"],
            "content": content,
        }
    ]


def _child_record(
    parent: dict,
    *,
    chunk_id: str,
    title: str,
    content: str,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "parent_chunk_id": parent["chunk_id"],
        "section_no": parent["section_no"],
        "pdf_page": parent["pdf_page"],
        "manual_page": parent["manual_page"],
        "title": title,
        "content": content,
    }


def _join_title(parent: str | None, child: str | None) -> str:
    values = [value.strip() for value in (parent or "", child or "") if value.strip()]
    return " - ".join(dict.fromkeys(values))


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return lines[start:end]


def _validate_chunks(chunks: list[dict], *, max_chunk_chars: int) -> None:
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("duplicate search chunk_id")
    for chunk in chunks:
        if not chunk["title"].strip() or not chunk["content"].strip():
            raise ValueError(f"empty search chunk: {chunk['chunk_id']}")
        if len(chunk["content"]) > max_chunk_chars:
            raise ValueError(f"search chunk too long: {chunk['chunk_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="검수 후보 매뉴얼을 고정 규칙으로 검색용 청크로 변환합니다.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-chars", type=int, default=MAX_CHUNK_CHARS)
    args = parser.parse_args()

    records = load_jsonl(args.input)
    chunks = preprocess_records(records, max_chunk_chars=args.max_chars)
    write_jsonl(args.output, chunks)
    print(
        f"manual preprocessing complete: source={len(records)} "
        f"search_chunks={len(chunks)} output={args.output}"
    )


if __name__ == "__main__":
    main()
