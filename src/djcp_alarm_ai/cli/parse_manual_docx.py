"""표준 매뉴얼 DOCX를 검수·전처리용 원본 JSONL로 변환합니다.

향후 매뉴얼은 아래 구조의 Word(.docx)로 전달됩니다.

- Title / Subtitle: 문서 제목
- ``메타데이터``: 문서 정보(문서명·문서번호·문서 버전 등 ``키: 값``)
- 목차(``toc 1/2/3``): ``섹션번호 제목<TAB>인쇄페이지``
- 본문 ``Heading 1~4``: 장/절 계층
- 본문 콘텐츠: ``Normal``(설명문), ``절차 항목``(번호 절차), ``List Bullet``(항목)

변환 규칙은 ``data/tg_manual/README.md``의 기존 원칙을 그대로 따릅니다.

- 리프 청크 단위는 내용을 가진 ``Heading 3``(또는 하위 절이 없는 ``Heading 2``)입니다.
- 리프 아래 ``Heading 4``는 ``[소제목]`` 형태로 본문에 포함하여, 1,200자 초과 시에만
  기존 ``djcp-preprocess-manual`` 규칙이 소제목 경계에서 분리할 수 있게 합니다.
- 제목은 상위 계층 경로를 ``섹션번호 + " - " 결합`` 형태로 보존합니다.
- 인쇄 페이지는 목차에서 섹션번호로 조회하며, DOCX에는 PDF 페이지가 없으므로
  ``pdf_page``와 ``manual_page`` 모두 인쇄 페이지를 사용합니다.
- 숫자·단위·기기 코드와 절차 순서는 원문 그대로 보존합니다.

같은 입력에서는 항상 같은 청크 ID와 결과가 생성됩니다(LLM 미사용).
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import docx
from docx.oxml.text.paragraph import CT_P
from docx.text.paragraph import Paragraph


PROJECT_ROOT = Path(__file__).parents[3]
DEFAULT_INPUT = PROJECT_ROOT / "docs" / "TG매뉴얼 & 비상시 조치사항.docx"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "tg_manual" / "tg_manual_source.jsonl"
DEFAULT_CHUNK_PREFIX = "tg-manual"

HEADING_STYLES = {
    "Heading 1": 1,
    "Heading 2": 2,
    "Heading 3": 3,
    "Heading 4": 4,
}
BULLET_STYLES = {"List Bullet", "List Bullet 2"}
PROCEDURE_STYLES = {"절차 항목", "절차 항목 2"}
NORMAL_STYLES = {"Normal"}
METADATA_STYLE = "메타데이터"
TOC_STYLES = {"toc 1", "toc 2", "toc 3"}

# 리프 경계가 되는 최대 헤딩 레벨. 이 레벨 이하 헤딩에서 새 리프가 시작되고,
# 더 깊은 헤딩(H4)은 [소제목]으로 본문에 포함됩니다.
LEAF_LEVEL = 3

_METADATA_KEY = re.compile(r"^([^:：]+)[:：]\s*(.+)$")
_TOC_ENTRY = re.compile(r"^(?P<number>[\d.]+)\s+(?P<title>.*?)\t+(?P<page>\d+)\s*$")


@dataclass
class _Section:
    number: str
    path: tuple[str, ...]
    lines: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        joined = " - ".join(part for part in self.path if part)
        return f"{self.number} {joined}".strip()


@dataclass(frozen=True)
class ParsedManual:
    metadata: dict[str, str]
    records: list[dict]


def iter_paragraphs(document: docx.document.Document) -> list[tuple[str, str]]:
    """문서 순서대로 (스타일명, 텍스트)를 반환합니다."""
    return [
        (Paragraph(child, document).style.name, Paragraph(child, document).text)
        for child in document.element.body.iterchildren()
        if isinstance(child, CT_P)
    ]


def extract_metadata(blocks: list[tuple[str, str]]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for style, text in blocks:
        if style != METADATA_STYLE:
            continue
        match = _METADATA_KEY.match(text.strip())
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()
    return metadata


def extract_toc_pages(blocks: list[tuple[str, str]]) -> dict[str, int]:
    """섹션번호(예 ``1.2.1``) → 인쇄 페이지 매핑을 목차에서 추출합니다."""
    pages: dict[str, int] = {}
    for style, text in blocks:
        if style not in TOC_STYLES:
            continue
        match = _TOC_ENTRY.match(text.strip())
        if match:
            pages[match.group("number")] = int(match.group("page"))
    return pages


def _render_line(style: str, text: str) -> str | None:
    value = text.strip()
    if not value:
        return None
    if style in HEADING_STYLES:  # Heading 4 (소제목)
        return f"[{value}]"
    if style in BULLET_STYLES:
        return value if value.startswith("-") else f"- {value}"
    if style in PROCEDURE_STYLES or style in NORMAL_STYLES:
        return value
    return None


def _build_sections(blocks: list[tuple[str, str]]) -> list[_Section]:
    body_start = next(
        (i for i, (style, _) in enumerate(blocks) if style == "Heading 1"),
        None,
    )
    if body_start is None:
        raise ValueError("본문 Heading을 찾지 못했습니다.")

    counters = [0, 0, 0, 0]
    headings: list[str] = ["", "", "", ""]
    sections: list[_Section] = []
    current: _Section | None = None

    for style, text in blocks[body_start:]:
        level = HEADING_STYLES.get(style)
        if level is not None:
            counters[level - 1] += 1
            for deeper in range(level, 4):
                counters[deeper] = 0
            headings[level - 1] = text.strip()
            for deeper in range(level, 4):
                headings[deeper] = ""

            if level <= LEAF_LEVEL:
                current = _Section(
                    number=".".join(
                        str(counters[i]) for i in range(level)
                    ),
                    path=tuple(headings[i] for i in range(level)),
                )
                sections.append(current)
            elif current is not None:  # Heading 4 → 현재 리프의 소제목
                line = _render_line(style, text)
                if line:
                    current.lines.append(line)
            continue

        if current is None:
            continue
        line = _render_line(style, text)
        if line:
            current.lines.append(line)

    return [section for section in sections if section.lines]


def _drop_trailing_subheadings(lines: list[str]) -> list[str]:
    """콘텐츠가 뒤따르지 않는 말단 ``[소제목]`` 줄은 제거합니다."""
    end = len(lines)
    while end > 0 and lines[end - 1].startswith("[") and lines[end - 1].endswith("]"):
        end -= 1
    return lines[:end]


def build_records(
    parsed_sections: list[_Section],
    toc_pages: dict[str, int],
    *,
    chunk_prefix: str = DEFAULT_CHUNK_PREFIX,
) -> list[dict]:
    records: list[dict] = []
    for index, section in enumerate(parsed_sections, start=1):
        lines = _drop_trailing_subheadings(section.lines)
        if not lines:
            continue
        page = _lookup_page(section.number, toc_pages)
        records.append(
            {
                "chunk_id": f"{chunk_prefix}-{index:03d}",
                "section_no": index,
                "section_number": section.number,
                "pdf_page": page,
                "manual_page": page,
                "title": section.title,
                "content": "\n".join(lines).strip(),
                "review_status": "pending",
            }
        )
    return records


def _lookup_page(number: str, toc_pages: dict[str, int]) -> str:
    if number in toc_pages:
        return str(toc_pages[number])
    # 목차에 없으면 상위 섹션의 페이지를 상속합니다.
    parts = number.split(".")
    while len(parts) > 1:
        parts = parts[:-1]
        parent = ".".join(parts)
        if parent in toc_pages:
            return str(toc_pages[parent])
    return "0"


def parse_manual_docx(
    source: Path | str | BinaryIO,
    *,
    chunk_prefix: str = DEFAULT_CHUNK_PREFIX,
) -> ParsedManual:
    """DOCX(경로 또는 열린 바이너리 스트림)를 원본 후보로 파싱합니다."""
    document = docx.Document(
        str(source) if isinstance(source, (str, Path)) else source
    )
    blocks = iter_paragraphs(document)
    metadata = extract_metadata(blocks)
    toc_pages = extract_toc_pages(blocks)
    sections = _build_sections(blocks)
    records = build_records(sections, toc_pages, chunk_prefix=chunk_prefix)
    if not records:
        raise ValueError("추출된 섹션이 없습니다.")
    return ParsedManual(metadata=metadata, records=records)


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    )
    path.write_text(value + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="표준 매뉴얼 DOCX를 검수·전처리용 원본 JSONL로 변환합니다.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunk-prefix", default=DEFAULT_CHUNK_PREFIX)
    args = parser.parse_args()

    parsed = parse_manual_docx(args.input, chunk_prefix=args.chunk_prefix)
    write_jsonl(args.output, parsed.records)
    document_no = parsed.metadata.get("문서번호", "-")
    version = parsed.metadata.get("문서 버전", "-")
    print(
        f"manual docx parse complete: sections={len(parsed.records)} "
        f"document_no={document_no} version={version} output={args.output}"
    )


if __name__ == "__main__":
    main()
