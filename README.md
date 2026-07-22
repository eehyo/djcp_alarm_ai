# DJCP Alarm AI

대전열병합 테스트 PostgreSQL의 `test` 스키마를 조회하여 알람과 태그 상태를
설명하는 FastAPI 백엔드입니다.

## 데이터 흐름

```text
ALARM_VALUE 또는 ALARM_HIST
  -> TAG_INFO + TAG_INFO_EXT
  -> tag_description
  -> asset_tag_link -> asset -> maintenance
  -> sop_document (데이터가 있을 때)
  -> MIMIC_FILE_TAG -> MIMIC_FILE
  -> LLM 답변 생성
```

- `TAG_INFO.TAG_ID`가 전체 연결의 기준 키입니다.
- 최근 알람은 `ALARM_VALUE`의 PK인 `TIMESTAMP + TAG_ID`로 선택합니다.
- 과거 알람은 `ALARM_HIST`에서 같은 키로 조회합니다.
- `TAG_NAME`은 태그 검색, 관련 태그, Mimic 연결에만 사용합니다.
- Mimic 경로는 API 응답에 포함하지만 LLM 판단 근거로 전달하지 않습니다.
- SOP는 `tag_id`를 우선 사용하고, 없으면
  `tag_description.sop_tag_name = sop_document.tag_name`으로 조회합니다.
  현재 데이터가 없으면 생략합니다.

실제 원격 스키마 계약은 `test_schema.sql`, 전달 자료는 `data/lab_handover/`에 있습니다.

## 환경 준비

Python 3.11 이상이 필요합니다.

```bash
python -m venv .venv
```

가상환경을 활성화한 후 설치합니다.

```bash
python -m pip install -e .
```

`.env.example`을 `.env`로 복사하고 실행 환경에 맞게 수정합니다.

```dotenv
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/djcp_alarm_ai
PSQL_URL=postgresql://<user>:<password>@<host>:5432/djcp_alarm_ai
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3.5:4b-q4_K_M
LLM_TEMPERATURE=0.0
LLM_TIMEOUT_SECONDS=120
RECENT_ALARM_LIMIT=10
RECENT_MAINTENANCE_LIMIT=5
RELATED_TAG_LIMIT=20
```

애플리케이션과 DB가 같은 서버에서 실행될 때만 DB 호스트로 `localhost`를 사용합니다.
`.env`는 Git에 커밋하지 않습니다.

## 테스트 알람 생성

현재 `ALARM_VALUE`가 비어 있으므로 최근 알람 API를 테스트하려면 가상 이벤트 한 건을
생성합니다. 임의 태그를 만들지 않고 반드시 `test.TAG_INFO`에 존재하는 `TAG_ID`를
사용합니다.

먼저 테스트할 태그를 찾습니다.

```sql
SELECT "TAG_ID", "TAG_NAME", "DESCRIPTION"
FROM test."TAG_INFO"
WHERE "TAG_NAME" = 'BBAIT-801';
```

Dry-run으로 입력 내용을 확인합니다.

```bash
djcp-seed-test-alarm \
  --tag-id 10011217 \
  --value 12.4 \
  --priority 4 \
  --message "TEST ALARM" \
  --dry-run
```

확인 후 `--dry-run`을 제거하면 같은 이벤트가 `ALARM_VALUE`와 `ALARM_HIST`에
하나의 트랜잭션으로 입력됩니다.

```bash
djcp-seed-test-alarm \
  --tag-id 10011217 \
  --value 12.4 \
  --priority 4 \
  --message "TEST ALARM"
```

`TAG_ID`, 값, 우선순위, 메시지는 실제 테스트 목적에 맞게 변경합니다. 명령은
`TAG_INFO`에서 태그명과 설명을 가져오므로 현재 테스트 서버의 마스터 정보만
사용합니다.

## API 실행

LLM을 포함해 실행합니다.

```bash
uvicorn djcp_alarm_ai.main:app --reload
```

LLM 없이 DB 조회와 rule-based 응답만 확인하려면:

```bash
LLM_BASE_URL= uvicorn djcp_alarm_ai.main:app --reload
```

상태 확인:

```bash
curl http://localhost:8000/health
```

API 문서:

```text
http://localhost:8000/docs
```

## API

### 최근 알람 목록

```http
GET /v2/analyses/recent-alarms
```

`ALARM_VALUE`에 데이터가 없으면 정상적으로 빈 배열을 반환합니다.

### 최근 알람 분석

```http
POST /v2/analyses/from-recent-alarm
Content-Type: application/json
```

```json
{
  "tag_id": 10011217,
  "timestamp": "2026-07-22T10:30:00+09:00",
  "question": "이 알람의 가능한 원인과 점검 항목을 알려줘."
}
```

`tag_id`와 `timestamp`는 최근 알람 목록에서 받은 값을 그대로 사용합니다.

### 과거 알람 분석

```http
POST /v2/analyses/from-history
Content-Type: application/json
```

```json
{
  "tag_id": 10011217,
  "timestamp": "2026-07-22T10:30:00+09:00",
  "question": "이 과거 알람의 원인과 조치 방향을 알려줘."
}
```

### 태그 질문

```http
POST /v2/analyses/from-tag
Content-Type: application/json
```

```json
{
  "tag_name": "BBAIT-801",
  "question": "이 태그에서 알람이 발생하면 무엇을 확인해야 해?"
}
```

현재 원격 데이터에서는 `TAG_NAME` 중복이 없지만, 코드에서는 중복 후보가 발견되면
409와 후보 `TAG_ID` 목록을 반환합니다.

## 응답 구조

내부 조회 컨텍스트에서 클라이언트에 필요한 근거만 최상위 멤버로 반환합니다.

```text
answer          LLM 또는 rule-based 최종 답변
alarm           선택한 ALARM_VALUE/HIST 이벤트
tag             TAG_INFO + TAG_INFO_EXT의 주요 정보와 알람 설정값
asset           asset_tag_link로 연결된 설비
related_tags    tag_description.related_tags 해석 결과
sop             같은 tag_id 또는 sop_tag_name으로 연결된 SOP
maintenance     선택된 asset.id의 최근 정비
mimic           관련 Mimic 파일
metrics         LLM 및 전체 분석 시간
```

LLM에는 Mimic 파일 경로와 임베딩 벡터를 전달하지 않습니다.
정비이력의 비용·작업자·확인자·팀 메모와 태그 설명의 중복 표시 필드도 LLM 입력에서
제외합니다. 외부 응답에도 문서에서 제안한 필드만 포함합니다.

`answer.likely_causes`는 다음 구조입니다.

```json
{
  "cause": "가능 원인",
  "basis": "DATABASE|TAG_DESCRIPTION|INFERENCE"
}
```

## RAG 적용 범위

- `TAG_INFO`, `TAG_INFO_EXT`, `tag_description`, 설비, 정비, Mimic은 키 기반 정확
  조회입니다.
- Mimic은 화면 이동용 메타데이터이므로 LLM 입력과 벡터 검색에서 제외합니다.
- SOP가 적재되면 `tag_id` 또는 `sop_tag_name`으로 정확 조회해 LLM 근거에 포함합니다.
- 현재 `sop_document.embedding`은 JSONB placeholder이고 원격 SOP 데이터도 비어
  있으므로 벡터 유사도 검색은 아직 수행하지 않습니다.
- 향후 pgvector 컬럼과 임베딩 모델이 확정되면 정확 조회 결과와 의미 검색 top-k를
  합치는 하이브리드 검색을 추가합니다. 정의되지 않은 벡터 컬럼은 현재 코드에서
  가정하지 않습니다.

## LLM 안전 규칙

- `PRIORITY` 숫자를 임의의 심각도 명칭으로 바꾸지 않습니다.
- 값과 설정값만 보고 LL/LO/HI/HH 종류를 단정하지 않습니다.
- `IS_ALM=0` 이벤트는 해제 이벤트로 표현합니다.
- 입력에 없는 정비·사고·계측값을 만들지 않습니다.
- SOP와 `tag_description`이 모두 있으면 함께 사용합니다. 태그 의미·값 변화 원인은
  `tag_description`, 점검·조치·안전 절차는 SOP를 우선하며 충돌 시 SOP를 따릅니다.
- 관련 태그의 현재 계측값이 없으면 동시 상승·하강을 단정하지 않습니다.

## 검증

로컬 DB 데이터가 원격과 달라도 실행 가능한 단위 테스트입니다.

```bash
pytest -q
```

Ollama 연결을 확인하려면:

```bash
djcp-llm-smoke-test
```

## 기준 자료와 SOP 적재

`data/lab_handover/`와 `test_schema.sql`이 현재 설계의 기준 자료입니다. 전달 SQL은
실행 시 `search_path`를 `test, public`으로 설정하므로 새 데이터도 `test` 스키마에
적재됩니다.

현재 원격에서 비어 있는 SOP만 적재하려면 다음 파일만 실행합니다.

```bash
psql "$PSQL_URL" -X -v ON_ERROR_STOP=1 \
  -f data/lab_handover/sop_document.sql
```

전체 전달 데이터를 다시 적재해야 할 때만 `build.sql`을 사용합니다.

전달 SQL에는 `tag_description` 4,105건과 이에 1:1로 대응하는 `sop_document`
4,105건, 설비 29건, 태그-설비 연결 4,107건, 정비이력 125건이 포함되어 있습니다.
SOP를 적재하면 별도 코드 변경 없이 태그별 정확 조회 결과가 `sop`과 LLM
근거에 포함됩니다.
