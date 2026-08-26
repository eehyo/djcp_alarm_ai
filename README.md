# DJCP Alarm AI

대전열병합(DJCP) 발전소의 태그·알람을 조회하여 원인·점검·조치를 설명하는 FastAPI
백엔드입니다. 태그·알람·설비·정비·LOTO·화면을 키 기반으로 조회하고, 태그 설명
지식(tag_description)과 TG 매뉴얼(벡터 검색)을 근거로 LLM이 구조화된 분석을 생성합니다.

## 아키텍처: 3개 데이터베이스

현장 기준에 맞춰 데이터가 3개 DB로 분리되어 있습니다(같은 PostgreSQL 서버, DB명만 다름).
모두 `public` 스키마를 사용합니다.

| DB | 역할 | 주요 테이블 |
|---|---|---|
| **FDAS** | 태그·알람·화면 | `TAG_INFO`, `TAG_INFO_EXT`, `ALARM_VALUE`, `ALARM_HIST`, `MIMIC_FILE`, `MIMIC_FILE_TAG` |
| **FDAS_AMS** | 설비·정비·LOTO | `asset`, `asset_tag_link`, `maintenance`, `maintenance_attachment`, `loto`, `loto_tag` |
| **djcp_alarm_ai** | AI 지식/RAG (pgvector) | `tag_description`, `manual_document`, `manual_chunk` |

DB가 물리적으로 분리되어 단일 SQL JOIN이 불가능하므로, 애플리케이션이 세 세션을
사용해 조회 결과를 조립합니다.

- 앱은 FDAS에서 태그·알람을 조회한 뒤 얻은 `TAG_ID`(정수)로 FDAS_AMS의
  `asset_tag_link → asset → maintenance/loto`를 조회합니다.
- LOTO는 두 경로를 합쳐서 제공합니다: ⓐ `loto.asset_id`(태그가 속한 설비),
  ⓑ `loto_tag.tag_code = TAG_INFO.TAG_NAME`(문자).
- 태그 지식(`tag_description`)과 매뉴얼 청크(`manual_chunk`, pgvector)는 djcp_alarm_ai에서
  조회합니다. 관련 태그(`related_tags`)는 `tag_description.related_tags`에서 나와 FDAS의
  `TAG_INFO`로 보강됩니다.

## 데이터 흐름

```text
ALARM_VALUE / ALARM_HIST / TAG_INFO (FDAS)
  → TAG_INFO + TAG_INFO_EXT
  → asset_tag_link → asset → maintenance, loto (FDAS_AMS)
  → tag_description, related_tags (djcp_alarm_ai + FDAS)
  → 질문 관련 시 manual_chunk 벡터 검색 (djcp_alarm_ai, 최대 2개)
  → 필요한 근거만 LLM에 전달
  → JSON 스키마 검증 후 응답
```

LLM에 전달하는 것: 태그, 알람, 과거 알람, 설비·설비트리, 정비 이력(worker 포함),
LOTO, tag_description(의미 필드), related_tags, 매뉴얼 청크(선택), 화면 이름(mimic_screens).
전달하지 않는 것: mimic 전체 경로, 정비의 내부키·비용·confirmer.

## 1. 필수 준비 사항

- Python 3.11 이상
- FDAS / FDAS_AMS / djcp_alarm_ai 세 DB에 접근 가능한 PostgreSQL 계정
- djcp_alarm_ai DB의 pgvector 확장
- `psql` 클라이언트
- 접근 가능한 Ollama 서버(답변 모델 + `bge-m3` 임베딩)

## 2. 설치

```bash
cd <project-root>/djcp_alarm_ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e .
```

## 3. 환경변수 (.env)

`.env.example`을 `.env`로 복사한 뒤 실제 서버 값으로 수정합니다.

```dotenv
FDAS_DATABASE_URL=postgresql+psycopg://<user>:<pw>@<host>:5432/FDAS
AMS_DATABASE_URL=postgresql+psycopg://<user>:<pw>@<host>:5432/FDAS_AMS
AI_DATABASE_URL=postgresql+psycopg://<user>:<pw>@<host>:5432/djcp_alarm_ai
AI_SCHEMA=public

LLM_BASE_URL=http://<ollama-host>:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3.5:9b            # 구조화 JSON 준수를 위해 9b 이상 권장
LLM_TEMPERATURE=0.0
LLM_TIMEOUT_SECONDS=120
LLM_MAX_TOKENS=2048            # 답변 JSON이 잘리지 않도록 충분히 크게

RECENT_ALARM_LIMIT=10
RECENT_MAINTENANCE_LIMIT=5
RELATED_TAG_LIMIT=20
ASK_MAX_TAGS=3                 # /ask에서 한 번에 분석할 최대 태그 수

MANUAL_RAG_ENABLED=true
EMBEDDING_BASE_URL=http://<ollama-host>:11434/v1
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
MANUAL_RAG_CANDIDATE_LIMIT=12
MANUAL_RAG_RESULT_LIMIT=2
MANUAL_RAG_CANDIDATE_MIN_SIMILARITY=0.50
MANUAL_RAG_MIN_SIMILARITY=0.60
MANUAL_RAG_HIGH_SIMILARITY=0.70
```

psql 명령용 URL은 아래처럼 별도 지정합니다(드라이버 표기만 다름).

```bash
export PSQL_URL_FDAS='postgresql://<user>:<pw>@<host>:5432/FDAS'
export PSQL_URL_AI='postgresql://<user>:<pw>@<host>:5432/djcp_alarm_ai'
```

## 4. Ollama 모델 준비

```bash
ollama pull qwen3.5:9b
ollama pull bge-m3
ollama list
```

`bge-m3`가 1024차원인지, 답변 모델 연결이 되는지 확인합니다.

```bash
djcp-llm-smoke-test
```

## 5. 기존 데이터 연결 확인

FDAS / FDAS_AMS는 이미 운영 데이터가 있습니다(조회만, 생성/덮어쓰기 금지).

```bash
psql "$PSQL_URL_FDAS" -c 'SELECT "TAG_ID","TAG_NAME" FROM public."TAG_INFO" LIMIT 5;'
```

## 6. AI 지식/RAG 테이블 준비 (djcp_alarm_ai)

pgvector와 `tag_description`, `manual_document`, `manual_chunk`를 준비합니다.

```bash
psql "$PSQL_URL_AI" -f data/lab_handover/ai_knowledge_ddl.sql
```

## 7. tag_description 적재

담당자가 제공한 태그 설명 데이터(SQL: CREATE + INSERT)를 djcp_alarm_ai에 적재합니다.

```bash
psql "$PSQL_URL_AI" -f data/lab_handover/tag_description.sql
psql "$PSQL_URL_AI" -c "SELECT count(*) FROM tag_description;"
```

## 8. 매뉴얼 임베딩·적재

`MANUAL_RAG_ENABLED` 상태와 무관하게 적재할 수 있습니다.

```bash
djcp-index-manual \
  --input data/tg_manual/tg_manual_search_chunks_003_015.jsonl \
  --source-name tg-emergency-manual \
  --document-version 003 \
  --parse-version 3
```

## 9. API 실행

```bash
uvicorn djcp_alarm_ai.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
# 문서: http://localhost:8000/docs
```

## 10. API 사용

### 최근 알람 목록
```http
GET /v2/analyses/recent-alarms
```

### 최근 알람 분석
```http
POST /v2/analyses/from-recent-alarm
{ "tag_id": 10014455, "timestamp": "2026-07-22T10:30:00+09:00", "question": "..." }
```
`tag_id`/`timestamp`는 최근 알람 목록에서 받은 값을 그대로 사용합니다.

### 과거 알람 분석
```http
POST /v2/analyses/from-history
{ "tag_id": 10014455, "timestamp": "...", "question": "..." }
```

### 태그 분석
```http
POST /v2/analyses/from-tag
{ "tag_name": "15ATA-118_D", "question": "..." }
```

### 자유질문 (태그 자동 인식)
```http
POST /v2/analyses/ask
{ "question": "15ATA-118_D 상태랑 최근 정비/LOTO 알려줘" }
```
태그명 매칭(우선) → 없으면 설명 키워드 → LLM이 질문에 필요한 태그를 **선별** →
선별된 태그별 개별 분석을 반환합니다.

```json
{ "question": "...", "analyses": [ { /* AnalysisResponse */ } ] }
```

## 11. 응답 구조 (AnalysisResponse)

```text
answer          summary(2~3문장 서술) + likely_causes[{cause,basis}] + checks + actions + warnings
alarm           선택된 ALARM_VALUE/HIST 이벤트
tag             TAG_INFO + TAG_INFO_EXT + 알람 설정값
asset           asset_tag_link로 연결된 설비
related_tags    tag_description.related_tags 해석 결과
maintenance     선택된 설비의 최근 정비(worker 포함)
loto            설비/태그에 발행된 LOTO 설치/해제 이력
mimic           관련 Mimic 파일
manual          답변에 반영된 매뉴얼 참조(최대 2개)
metrics         LLM 및 전체 분석 시간
```

`answer.likely_causes[].basis`는 `DATABASE`, `TAG_DESCRIPTION`, `MANUAL`, `INFERENCE` 중 하나입니다.

## 12. 가상 알람 데이터(테스트용)

`ALARM_VALUE`/`ALARM_HIST`가 비어 있으면 테스트용 이벤트를 넣을 수 있습니다.
FDAS 쓰기 권한이 필요하므로 관리자 계정으로 권한을 부여해야 합니다.

```bash
# 관리자(예: postgres) 계정으로 FDAS에 1회
psql "postgresql://postgres:<pw>@<host>:5432/FDAS" -f scripts/grant_alarm_insert.sql
# 이후 seed
djcp-seed-test-alarm --tag-id 10014455 --value 12.3 --priority 2 --message "TEST HI ALARM" --is-alm 1
```

## 13. 테스트

```bash
python -m pip install pytest
pytest -q
```

실행 중인 API 통합 시나리오:

```bash
djcp-test-scenarios --suite quick
```

## 관련 문서

- `data/lab_handover/ai_knowledge_ddl.sql`: AI 지식/RAG 테이블 DDL
- `data/lab_handover/tag_description.sql`: 태그 설명 데이터(적재용)
- `data/tg_manual/README.md`: 매뉴얼 원본/검색 청크 생성 규칙
- `scripts/verify_data_access.py`: 3-DB 조합 조회 검증 스크립트
