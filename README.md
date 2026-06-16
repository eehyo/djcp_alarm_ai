# DJCP Alarm AI

PostgreSQL의 실제 `alarm.id`, `tag.id`, `asset.id`를 기준으로 알람과 태그 상태를
설명하는 FastAPI 프로젝트입니다.

핵심 조회 흐름:

```text
alarm.id
-> alarm.tag_id = tag.id
-> tag.asset_id = asset.id
-> ai.tag_description.tag_id = tag.id
-> 응답 생성
```

태그명 질문은 먼저 `tag.tag_name`으로 실제 `tag.id`를 확정한 뒤 같은 흐름으로
Description을 조회합니다.

## 남긴 파일 구조

```text
data/
  tag_descriptions.json     태그 Description 원본
  demo_seed.sql             새 환경 통합 테스트용 샘플 데이터
migrations/
  000_create_operational_schema.sql
  001_ai_tag_description.sql
scripts/
  create_database.sh
  apply_migration.sh
  load_demo_data.sh
src/djcp_alarm_ai/
  FastAPI 앱, DB 조회, Description 동기화, LLM 응답 생성
.env.example
pyproject.toml
```

## 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

## PostgreSQL DB 생성

PostgreSQL이 실행 중이어야 합니다.

```bash
chmod +x scripts/*.sh
PGUSER=postgres ./scripts/create_database.sh
```

`psql` 또는 `createdb`가 PATH에 없으면 경로를 지정합니다.

```bash
PSQL_BIN=/opt/homebrew/opt/postgresql@15/bin/psql \
CREATEDB_BIN=/opt/homebrew/opt/postgresql@15/bin/createdb \
PGUSER=postgres \
./scripts/create_database.sh
```

이미 DB가 있으면 스크립트는 중단합니다. 새로 만들고 싶으면 기존 DB를 직접 삭제하거나
`DB_NAME`을 바꿉니다.

```bash
DB_NAME=djcp_alarm_ai_dev PGUSER=postgres ./scripts/create_database.sh
```

생성 후 `.env`의 DB URL을 확인합니다.

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/djcp_alarm_ai
PSQL_URL=postgresql://postgres:postgres@localhost:5432/djcp_alarm_ai
```

## 데모 데이터 적재

새 환경에서 바로 확인할 수 있도록 데모 설비, 태그, 알람, 정비 이력을 넣습니다.

```bash
./scripts/load_demo_data.sh
```

`psql` 경로가 필요하면:

```bash
PSQL_BIN=/opt/homebrew/opt/postgresql@15/bin/psql ./scripts/load_demo_data.sh
```

Description JSON의 모든 `tag_name`을 데모 태그로 생성합니다. `BB*` 태그는
`DEMO-BOILER-1`, `BC*` 태그는 `DEMO-BOILER-2`에 연결됩니다.

```bash
.venv/bin/djcp-seed-description-tags --split-boilers
.venv/bin/djcp-description-sync
```

정상 확인:

```bash
.venv/bin/djcp-description-sync --dry-run
.venv/bin/djcp-schema-check
```

기대값:

```text
resolved_records = 163
missing_tag_names = []
schema ok = true
```

## Ollama 설정

RTX 5070 12GB 기준 추천 모델은 `qwen3.5:9b`입니다.

```bash
ollama pull qwen3.5:9b
OLLAMA_CONTEXT_LENGTH=4096 ollama serve
```

다른 터미널에서 확인:

```bash
ollama run qwen3.5:9b "한국어로 한 문장만 답해줘: 정상 작동 확인"
ollama ps
```

`.env`의 LLM 설정:

```dotenv
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3.5:9b
LLM_TEMPERATURE=0.0
LLM_TIMEOUT_SECONDS=120
```

LLM 연결만 먼저 확인:

```bash
.venv/bin/djcp-llm-smoke-test
```

## API 실행

LLM을 사용하려면 `.env`의 `LLM_BASE_URL`을 그대로 두고 실행합니다.

```bash
.venv/bin/uvicorn djcp_alarm_ai.main:app --reload
```

LLM 없이 DB와 Description 연결만 확인하려면:

```bash
LLM_BASE_URL= .venv/bin/uvicorn djcp_alarm_ai.main:app --reload
```

상태 확인:

```bash
curl http://localhost:8000/health
```

태그명 질문:

```bash
curl -X POST http://localhost:8000/v2/analyses/from-tag \
  -H 'Content-Type: application/json' \
  -d '{"tag_name":"BBAIT-801","question":"이 태그 값이 왜 상승했어?"}'
```

알람 ID 질문:

```bash
curl -X POST http://localhost:8000/v2/analyses/from-alarm/1 \
  -H 'Content-Type: application/json' \
  -d '{"question":"이 알람이 발생한 원인과 점검 순서를 알려줘"}'
```

## Description 구조

Description은 `ai.tag_description` 단일 테이블에 저장됩니다.

```text
tag_id
tag_name_snapshot
description
tag_nm
tag_rmk
tag_desc
equipment_description
tag_description
value_change_meaning
key_check_points
action_guidance
failure_guidance
```

`tag_name`은 동기화 시 `tag.tag_name`과 매칭해서 실제 `tag.id`를 찾는 용도입니다.
런타임 조회는 항상 `tag.id` 기준입니다.
