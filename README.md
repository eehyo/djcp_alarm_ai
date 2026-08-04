# DJCP Alarm AI

대전열병합 테스트 PostgreSQL의 `test` 스키마를 조회하여 알람과 태그 상태를
설명하는 FastAPI 백엔드입니다.

## 데이터 흐름

```text
ALARM_VALUE 또는 ALARM_HIST
  -> TAG_INFO + TAG_INFO_EXT
  -> tag_description
  -> asset_tag_link -> asset -> maintenance
  -> MIMIC_FILE_TAG -> MIMIC_FILE
  -> 질문 의도 판정 -> 관련 매뉴얼 최대 2개 검색
  -> LLM 답변 생성
```

- `TAG_INFO.TAG_ID`가 전체 연결의 기준 키입니다.
- 최근 알람은 `ALARM_VALUE`의 PK인 `TIMESTAMP + TAG_ID`로 선택합니다.
- 과거 알람은 `ALARM_HIST`에서 같은 키로 조회합니다.
- `TAG_NAME`은 태그 검색, 관련 태그, Mimic 연결에만 사용합니다.
- Mimic 경로는 API 응답에 포함하지만 LLM 판단 근거로 전달하지 않습니다.

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
MANUAL_RAG_ENABLED=false
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
MANUAL_RAG_RESULT_LIMIT=2
MANUAL_RAG_MIN_SIMILARITY=0.70
MANUAL_RAG_HIGH_SIMILARITY=0.82
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
maintenance     선택된 asset.id의 최근 정비
mimic           관련 Mimic 파일
manual          실제 답변에 반영된 매뉴얼 참조(최대 2개)
metrics         LLM 및 전체 분석 시간
```

LLM에는 Mimic 파일 경로와 임베딩 벡터를 전달하지 않습니다.
정비이력의 비용·작업자·확인자·팀 메모와 태그 설명의 중복 표시 필드도 LLM 입력에서
제외합니다. 외부 응답에도 문서에서 제안한 필드만 포함합니다.

`answer.likely_causes`는 다음 구조입니다.

```json
{
  "cause": "가능 원인",
  "basis": "DATABASE|TAG_DESCRIPTION|MANUAL|INFERENCE"
}
```

## 매뉴얼 RAG

모델 설치부터 DB 적재, 검색 기준 시험과 최종 활성화까지의 실행 명령은
[`MANUAL_RAG_RUNBOOK.md`](data/lab_handover/MANUAL_RAG_RUNBOOK.md)에 정리되어 있습니다.

- `TAG_INFO`, `TAG_INFO_EXT`, `tag_description`, 설비, 정비, Mimic은 키 기반 정확
  조회입니다.
- Mimic은 화면 이동용 메타데이터이므로 LLM 입력과 벡터 검색에서 제외합니다.
- 매뉴얼은 `TAG_ID`와 직접 연결하지 않습니다. 질문, 태그 설명, 계통, 설비명과 알람
  메시지를 조합하여 요청 시점에 검색합니다.
- 값·단위·화면 위치처럼 매뉴얼이 필요하지 않은 질문에는 임베딩 검색을 수행하지 않습니다.
- 벡터 유사도, 핵심 용어 일치와 설비 일치를 함께 확인하고 관련성이 부족하면 빈 결과를
  사용합니다.
- LLM과 외부 응답에는 최대 2개만 반영하며 내부 유사도 점수는 노출하지 않습니다.
- 매뉴얼 검색 실패는 재시도하지 않고 매뉴얼 없이 기존 분석 흐름을 계속합니다.

### 초기 적재

먼저 pgvector 저장소를 생성합니다.

```bash
psql "$PSQL_URL" -f data/lab_handover/manual_rag.sql
```

목차 기준 후보 JSONL을 먼저 고정 규칙으로 검색용 청크로 변환합니다.

```bash
djcp-preprocess-manual
```

생성된 검색용 JSONL을 적재합니다. 검수 상태명은 런타임 검색 여부에 영향을 주지 않고,
현재 문서 버전의 `is_active`만 사용합니다.

```bash
djcp-index-manual \
  --input data/tg_manual/tg_manual_search_chunks_003_015.jsonl \
  --source-name tg-emergency-manual \
  --document-version 003 \
  --parse-version 3
```

적재 후 `MANUAL_RAG_ENABLED=true`로 변경합니다. 새 매뉴얼은 별도 `source-name`과
문서 버전으로 같은 적재 명령을 사용하며, 변경되지 않은 청크의 임베딩은 재사용합니다.

## LLM 안전 규칙

- `PRIORITY` 숫자를 임의의 심각도 명칭으로 바꾸지 않습니다.
- 값과 설정값만 보고 LL/LO/HI/HH 종류를 단정하지 않습니다.
- `IS_ALM=0` 이벤트는 해제 이벤트로 표현합니다.
- 입력에 없는 정비·사고·계측값을 만들지 않습니다.
- 태그 의미·값 변화 원인과 현재 점검·조치 근거는 `tag_description` 범위 안에서
  사용합니다.
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

### API 시나리오 일괄 테스트

실행 중인 API를 대상으로 태그·설비·정비이력·데이터 부족·알람 이벤트를
한 번에 검사하고 원본 응답과 판정 결과를 JSON으로 저장할 수 있습니다.

먼저 첫 번째 터미널에서 API를 실행합니다.

```bash
uvicorn djcp_alarm_ai.main:app --reload
```

두 번째 터미널에서 빠른 테스트를 실행합니다. Windows PowerShell에서도 같은
명령을 사용합니다.

```bash
djcp-test-scenarios --suite quick
```

`quick`은 대표 태그 4건과 최신 `ALARM_HIST` 1건을 검사하고, `ALARM_VALUE`가
비어 있지 않으면 최근 알람 1건도 검사합니다. 전체 태그 시나리오 7건을 실행하려면:

```bash
djcp-test-scenarios --suite full
```

결과는 `test_outputs/integration_YYYYMMDD_HHMMSS.json`에 UTF-8로 저장됩니다.
각 케이스에는 요청, 원본 API 응답, HTTP 상태, 실행시간, 세부 통과/실패 판정이
포함됩니다. `ALARM_HIST` 또는 `ALARM_VALUE`가 비어 있으면 해당 케이스는 실패가
아닌 `SKIP`으로 기록됩니다. 실패 케이스가 하나라도 있으면 프로세스 종료 코드는
1입니다.

응답의 `metrics.generation_mode`로 생성 경로를 확인할 수 있습니다.

- `LLM`: 첫 번째 LLM 답변 사용
- `RULE_BASED`: LLM을 설정하지 않은 실행

LLM 답변 요청은 OpenAI 호환 클라이언트의 `max_retries=1`을 사용하므로 일시적인
통신·서버 오류에는 최대 한 번 재시도할 수 있습니다. 첫 번째로 수신한 답변의 내용이
부족하거나 JSON 후처리·스키마 검증에 실패했다는 이유로 답변을 다시 생성하거나 규칙
기반 답변으로 보완하지는 않습니다. 검증 실패 시 API는 503을 반환하므로 모델의 현재
출력 품질을 그대로 확인할 수 있습니다.

코드를 갱신한 뒤 명령이 아직 등록되지 않은 Windows 환경에서는 한 번 실행합니다.

```powershell
python -m pip install -e .
```

콘솔 명령을 등록하지 않고 직접 실행할 수도 있습니다.

```powershell
python -m djcp_alarm_ai.cli.run_scenarios --suite quick
```

## 기준 자료 적재

`data/lab_handover/`와 `test_schema.sql`이 현재 설계의 기준 자료입니다. 전달 SQL은
실행 시 `search_path`를 `test, public`으로 설정하므로 새 데이터도 `test` 스키마에
적재됩니다.

전체 전달 데이터를 다시 적재해야 할 때 `build.sql`을 사용합니다.

전달 SQL에는 `tag_description` 4,105건, 설비 29건, 태그-설비 연결 4,107건,
정비이력 125건이 포함되어 있습니다.
