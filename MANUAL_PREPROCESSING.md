# 매뉴얼 전처리·벡터화 가이드

매뉴얼(.docx)을 검색·임베딩용 청크로 변환해 pgvector(`manual_chunk`)에 적재하는
표준 절차입니다. 같은 템플릿으로 만든 문서라면 종류와 무관하게 동일하게 동작합니다.

## 1. 파이프라인 개요

```text
DOCX  ──parse──▶  원본 JSONL  ──preprocess──▶  검색 청크 JSONL  ──index──▶  manual_chunk
 (원본)          (섹션 후보)      (≤1,200자 청크)              (임베딩 + pgvector)
```

- 모든 단계는 **LLM을 쓰지 않으며**, 같은 입력에서 항상 같은 결과를 냅니다.
- CLI 3단계(파일로 확인하며 진행)와 업로드 API(원격 1회 실행) 둘 다 **같은 코드**를
  사용합니다.

| 단계 | 명령 | 입력 → 출력 | 구현 |
| --- | --- | --- | --- |
| 파싱 | `djcp-parse-manual-docx` | `.docx` → `tg_manual_source.jsonl` | `cli/parse_manual_docx.py` |
| 전처리 | `djcp-preprocess-manual` | `source.jsonl` → `search_chunks.jsonl` | `cli/preprocess_manual.py` |
| 적재 | `djcp-index-manual` | `search_chunks.jsonl` → DB | `cli/index_manual.py` |

## 2. 문서 작성 규칙 (필수)

파서는 Word **스타일 이름**으로 구조를 인식합니다. 새 매뉴얼은 아래 스타일을 사용하세요.

| 스타일 | 용도 |
| --- | --- |
| `Title` / `Subtitle` | 문서 제목 |
| `메타데이터` | 문서 정보. `문서번호: FV-TG-OM-001` 처럼 `키: 값` 한 줄씩 |
| `toc 1` / `toc 2` / `toc 3` | 목차. `섹션번호 제목<TAB>인쇄페이지` (Word 자동 목차면 충족) |
| `Heading 1`~`Heading 4` | 장/절 계층 |
| `Normal` | 설명문 |
| `절차 항목` / `절차 항목 2` | 번호 절차(`1. …`) |
| `List Bullet` / `List Bullet 2` | 항목(불릿) |

> 표는 관계를 보존한 텍스트(불릿/절차)로 풀어 두고, 그림·복잡한 계통도는 초기
> 색인에서 제외합니다. `문서번호`는 기본 `source_name`, `문서 버전`은 기본
> `document_version`으로 쓰입니다.

## 3. 청킹 규칙

- **리프 단위**: 내용을 가진 `Heading 3`(하위 절이 없으면 `Heading 2`).
- 리프 아래 `Heading 4`는 `[소제목]`으로 본문에 포함합니다.
- **1,200자 이하면 절 전체를 그대로 유지**하고, 초과할 때만 분리합니다.
  - `[소제목]` 경계에서 분리하며, 소제목 앞 개요문은 앞선 청크로 유지합니다.
  - 소제목이 없는 장문은 문장·줄 경계에서 1,200자 이하 창으로 나눕니다.
  - 번호 절차(`N.`)나 Trip 조건 개별 항목으로는 자르지 않습니다.
- 제목은 계층 경로를 `섹션번호 + " - " 결합`으로 보존합니다.
  예: `1.2.2 비상시 조치사항 - TBN/GEN Trip 시 조치사항 - ESV Close 후 …`
- 인쇄 페이지는 목차에서 섹션번호로 조회합니다(`pdf_page = manual_page`).
- 분리 청크는 `-sNN` 접미사를 쓰고 원본 절을 `parent_chunk_id`로 가리킵니다.

현재 문서 기준: **284개 섹션 → 500개 검색 청크**(최대 본문 1,193자).

## 4. CLI로 적재하기

```bash
# 1) DOCX → 원본 JSONL
djcp-parse-manual-docx \
  --input "docs/새매뉴얼.docx" \
  --output data/tg_manual/tg_manual_source.jsonl

# 2) 원본 JSONL → 검색 청크 JSONL
djcp-preprocess-manual \
  --input data/tg_manual/tg_manual_source.jsonl \
  --output data/tg_manual/tg_manual_search_chunks.jsonl

# 3) 임베딩 후 manual_document / manual_chunk 적재
djcp-index-manual \
  --input data/tg_manual/tg_manual_search_chunks.jsonl \
  --source-name fv-tg-om-001 \
  --document-version 1.0 \
  --parse-version docx-1
```

인자를 생략하면 위 기본 경로/값을 사용합니다. 1·2단계는 임베딩 서버 없이 실행되며,
3단계만 임베딩 서버(`EMBEDDING_BASE_URL`)와 `djcp_alarm_ai` DB가 필요합니다.

## 5. 업로드 API로 적재하기

서버 실행 후(`uvicorn djcp_alarm_ai.main:app`):

```http
POST /v2/manual/documents          # .docx 업로드 → 파싱·전처리·임베딩·적재
POST /v2/manual/documents/preview  # 임베딩·DB 없이 파싱·전처리 결과만 미리보기
GET  /v2/manual/documents          # 적재된 매뉴얼 문서 목록
```

```bash
# 파이프라인 점검 (임베딩 서버 불필요) — 섹션/청크 수, 최대 길이, 샘플 5개 반환
curl -F "file=@docs/새매뉴얼.docx" \
  http://localhost:8000/v2/manual/documents/preview

# 실제 벡터화·적재
curl -F "file=@docs/새매뉴얼.docx" \
  -F "source_name=fv-tg-om-001" -F "document_version=1.0" \
  http://localhost:8000/v2/manual/documents
```

- `source_name`/`document_version`을 생략하면 문서 `메타데이터`에서 채웁니다.
- `.docx`가 아니거나(415), 25MB 초과(413), 구조를 해석할 수 없으면(422) 거부합니다.

## 6. 재적재와 갱신

- 같은 `source_name`으로 다시 적재하면 이전 청크는 삭제하지 않고
  `is_active = FALSE`로 비활성화합니다.
- 내용 해시(`content_hash`)와 임베딩 모델이 같은 청크는 **재임베딩 없이 재사용**하므로,
  일부만 바뀐 문서를 다시 올려도 변경분만 임베딩합니다.
- 임베딩 모델을 바꾸면(`EMBEDDING_MODEL`) 차원과 기존 색인을 함께 교체해야 합니다
  (`bge-m3` = 1024차원).

## 7. 관련 파일

- `docs/…​.docx` — 원본 매뉴얼(전달본)
- `data/tg_manual/tg_manual_source.jsonl` — 파싱 결과(검수 후보)
- `data/tg_manual/tg_manual_search_chunks.jsonl` — 검색·임베딩용 청크
- `src/djcp_alarm_ai/manual_ingest.py` — 파싱→전처리→적재 오케스트레이션(CLI·API 공용)
- `src/djcp_alarm_ai/manual_api.py` — 업로드 API 라우터
- `data/lab_handover/ai_knowledge_ddl.sql` — `manual_document`/`manual_chunk` DDL
