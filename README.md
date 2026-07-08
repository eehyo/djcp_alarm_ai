# DJCP Alarm AI

PostgreSQL에 저장된 실제 `alarm`, `tag`, `asset` 데이터를 기준으로 발전소 알람과
태그 상태를 설명하는 FastAPI 백엔드입니다. 태그별 설명 지식은
`data/tag_descriptions.json`에서 읽어 `ai.tag_description` 테이블에 저장합니다.

API는 다음 순서로 데이터를 찾습니다.

```text
alarm.id
-> alarm.tag_id = tag.id
-> tag.asset_id = asset.id
-> ai.tag_description.tag_id = tag.id
-> 응답 생성
```

태그명으로 질문할 때는 먼저 `tag.tag_name`으로 실제 `tag.id`를 찾습니다. 같은
`tag_name`이 여러 설비에 있으면 API 요청에 `asset_id`를 같이 넣어야 합니다.

> `data/tag_descriptions.json`의 내용은 초기 설명 지식입니다. 운영에 사용하기 전에는
> 발전소 운전/정비/계측 전문가가 태그 설명, 점검 항목, 조치 가이드, 장애 가이드를
> 검수해야 하며, 검수 결과에 따라 JSON 내용을 추가/수정/삭제한 뒤 다시 동기화해야
> 합니다. 검수 전 description은 참고용 지식으로만 사용합니다.

## 전체 실행 순서

처음 이 코드를 받은 사람은 아래 순서대로 진행하면 됩니다.

```text
1. PostgreSQL 설치 및 실행
2. Python 가상환경 생성 및 패키지 설치
3. .env 파일 생성
4. PostgreSQL 데이터베이스와 테이블 생성
5. 데모 운영 데이터 적재
6. Description JSON 태그 생성 및 동기화
7. DB-only 모드로 API 먼저 테스트
8. Ollama/Qwen 설치 및 LLM 테스트
9. LLM 모드로 API 테스트
```

DB-only 모드는 Qwen을 사용하지 않고 DB 연결과 Description 매핑만 확인하는 방식입니다.
먼저 DB-only 테스트가 성공한 뒤 Qwen을 붙이면 문제 원인을 나누어 확인하기 쉽습니다.

## 현재 폴더 구조

현재 작업 폴더는 `<project-root>/djcp_alarm_ai`입니다.

```text
.
|-- README.md
|-- pyproject.toml
|-- .env.example
|-- .gitignore
|-- data/
|   |-- demo_seed.sql
|   `-- tag_descriptions.json
|-- migrations/
|   |-- 000_create_operational_schema.sql
|   `-- 001_ai_tag_description.sql
|-- scripts/
|   |-- apply_migration.sh
|   |-- create_database.sh
|   `-- load_demo_data.sh
`-- src/
    |-- djcp_alarm_ai/
    |   |-- api.py
    |   |-- config.py
    |   |-- db.py
    |   |-- generator.py
    |   |-- main.py
    |   |-- repositories.py
    |   |-- schema_validation.py
    |   |-- schemas.py
    |   |-- service.py
    |   |-- cli/
    |   |-- knowledge/
    |   `-- prompts/
```

로컬에서 생성되는 파일:

```text
.env                         로컬 환경 변수 파일, gitignore 대상
.venv/                       Python 가상환경
src/djcp_alarm_ai.egg-info/   editable install 생성물
```

프로젝트 요구 Python 버전은 `pyproject.toml` 기준 `>=3.11`입니다.

## 1. PostgreSQL 설치

Ubuntu 기준 설치 방법입니다.

```bash
sudo apt update
sudo apt install -y postgresql postgresql-client jq
sudo systemctl enable --now postgresql
```

`jq`는 API 응답 JSON을 보기 좋게 출력하기 위한 도구입니다. `jq`가 없어도 API는
동작하지만, 아래 테스트 명령의 `| jq '.answer'` 부분은 사용할 수 없습니다.

설치 확인:

```bash
psql --version
createdb --version
sudo systemctl status postgresql --no-pager
```

이 프로젝트의 기본 `.env`는 DB 비밀번호를 `postgres`로 가정합니다. 로컬 개발용으로
아래처럼 비밀번호를 맞춥니다.

```bash
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"
```

## 2. Python 환경 설치

프로젝트 루트에서 실행합니다.

```bash
cd ~/workspace/djcp_alarm_ai
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
```

설치되는 CLI 명령:

```text
djcp-description-sync
djcp-seed-description-tags
djcp-schema-check
djcp-llm-smoke-test
```

## 3. 환경 변수 확인

`.env` 파일이 아래와 비슷한지 확인합니다.

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/djcp_alarm_ai
PSQL_URL=postgresql://postgres:postgres@localhost:5432/djcp_alarm_ai
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3.5:9b
LLM_TEMPERATURE=0.0
LLM_TIMEOUT_SECONDS=120
RECENT_ALARM_LIMIT=10
RECENT_MAINTENANCE_LIMIT=5
RELATED_TAG_LIMIT=20
```

`DATABASE_URL`은 FastAPI와 Python CLI가 DB에 접속할 때 사용합니다.
`PSQL_URL`은 `scripts/*.sh`가 `psql`로 DB에 접속할 때 사용합니다.
`LLM_BASE_URL`을 비우면 Qwen 없이 rule-based 답변을 생성합니다.

## 4. DB 생성 및 테이블 생성

스크립트 실행 권한을 부여하고 DB를 생성합니다.

```bash
chmod +x scripts/*.sh
PGPASSWORD=postgres PGUSER=postgres ./scripts/create_database.sh
```

이 스크립트는 `djcp_alarm_ai` DB를 만들고 아래 migration을 적용합니다.

```text
migrations/000_create_operational_schema.sql
migrations/001_ai_tag_description.sql
```

이미 DB가 있으면 스크립트는 중단합니다. 다른 이름으로 새 DB를 만들려면:

```bash
DB_NAME=djcp_alarm_ai_dev PGPASSWORD=postgres PGUSER=postgres ./scripts/create_database.sh
```

기존 DB에 migration 하나만 직접 적용하려면:

```bash
./scripts/apply_migration.sh migrations/001_ai_tag_description.sql
```

## 5. DB 구조 설명

이 프로젝트는 운영 데이터 테이블과 AI 설명 테이블을 분리합니다.

```text
asset
  설비 정보입니다. 발전소, 호기, 보일러 같은 설비 계층을 저장합니다.

tag
  센서/태그 정보입니다. 각 tag는 asset_id로 어느 설비에 붙어 있는지 연결됩니다.

alarm
  알람 이력입니다. 각 alarm은 tag_id로 어떤 태그에서 발생했는지 연결됩니다.

maintenance
  정비 이력입니다. 각 maintenance는 asset_id로 어느 설비의 정비인지 연결됩니다.

ai.tag_description
  AI 답변에 사용할 태그 설명 지식입니다. data/tag_descriptions.json 내용을
  실제 tag.id에 매핑해서 저장합니다.
```

관계는 아래처럼 이해하면 됩니다.

```text
asset.id
  <- tag.asset_id
      <- alarm.tag_id
      <- ai.tag_description.tag_id

asset.id
  <- maintenance.asset_id
```

API 응답에서 `context`는 DB에서 모은 근거 데이터이고, `answer`는 최종 답변입니다.

```text
context.question
context.alarm
context.tag
context.asset
context.asset_path
context.recent_alarms
context.recent_maintenance
context.related_tags
context.tag_knowledge

answer.summary
answer.likely_causes
answer.checks
answer.actions
answer.warnings
```


## 6. 데모 데이터 적재

데모 설비, 태그, 알람, 정비 이력을 넣습니다.

```bash
./scripts/load_demo_data.sh
```

Description JSON의 모든 `tag_name`을 데모 DB의 `tag` 테이블에 생성합니다.
`BB*` 태그는 `DEMO-BOILER-1`, `BC*` 태그는 `DEMO-BOILER-2`에 연결됩니다.

```bash
.venv/bin/djcp-seed-description-tags --split-boilers
```

그 다음 Description JSON 내용을 `ai.tag_description`에 동기화합니다.

```bash
.venv/bin/djcp-description-sync
```

운영 DB의 `tag_name` 매핑이 일부 비어 있거나 중복되어도 데모/증분 확인용으로
해석 가능한 항목만 쓰려면 `--allow-partial`을 사용합니다.

```bash
.venv/bin/djcp-description-sync --allow-partial
```

## 7. DB 적재 확인

스키마와 Description 매핑 상태를 확인합니다.

```bash
.venv/bin/djcp-schema-check
.venv/bin/djcp-description-sync --dry-run
```

정상이라면 대략 아래 값을 확인할 수 있습니다.

```text
schema ok = true
resolved_records = 163
missing_tag_names = []
```

실제 알람 ID를 확인하려면:

```bash
PGPASSWORD=postgres psql "postgresql://postgres:postgres@localhost:5432/djcp_alarm_ai" \
  -c "SELECT alarm.id, tag.tag_name, alarm.start_time, alarm.state FROM alarm JOIN tag ON tag.id = alarm.tag_id ORDER BY alarm.start_time DESC;"
```

## 8. DB-only API 테스트

먼저 Qwen 없이 API를 테스트합니다. 이 단계가 성공하면 PostgreSQL, demo data,
Description 동기화가 정상이라는 뜻입니다.

```bash
LLM_BASE_URL= .venv/bin/uvicorn djcp_alarm_ai.main:app --reload
```

다른 터미널에서 상태 확인:

```bash
curl http://localhost:8000/health
```

태그명 질문:

```bash
curl -s -X POST http://localhost:8000/v2/analyses/from-tag \
  -H 'Content-Type: application/json' \
  -d '{"tag_name":"BBAIT-801","question":"이 태그 값이 왜 상승했어?"}' \
  | jq '.answer'
```

다른 태그 예시:

```bash
curl -s -X POST http://localhost:8000/v2/analyses/from-tag \
  -H 'Content-Type: application/json' \
  -d '{"tag_name":"BBPIT-401","question":"압력이 비정상일 때 점검 순서를 알려줘"}' \
  | jq '.answer'
```

알람 ID 질문:

```bash
curl -s -X POST http://localhost:8000/v2/analyses/from-alarm/1 \
  -H 'Content-Type: application/json' \
  -d '{"question":"이 알람이 발생한 원인과 점검 순서를 알려줘"}' \
  | jq '.answer'
```

알람 ID가 `1`이 아닐 수 있습니다. 위의 SQL 조회 결과에서 나온 `alarm.id`로 바꿔서
호출하면 됩니다.

브라우저로 `http://localhost:8000/`에 접속하면 `404 Not Found`가 나올 수 있습니다.
루트 `/`는 만들지 않았기 때문에 정상입니다. 상태 확인은 `/health`로 합니다.

## 9. Ollama/Qwen 설치 및 확인

Ollama 설치:

```bash
sudo apt install -y curl ca-certificates
curl -fsSL https://ollama.com/install.sh | sh
```

Qwen 모델 다운로드:

```bash
ollama pull qwen3.5:9b
```

간단한 실행 확인:

```bash
ollama run qwen3.5:9b "Do not show reasoning. Answer only one short Korean sentence: 정상 작동 확인"
```

Qwen 계열 모델은 thinking 출력을 길게 보여줄 수 있습니다. 단순 테스트에서는 아래처럼
`/no_think`를 붙여볼 수 있습니다.

```bash
ollama run qwen3.5:9b "/no_think 한국어로 한 문장만 답해줘: 정상 작동 확인"
```

프로젝트의 LLM smoke test:

```bash
.venv/bin/djcp-llm-smoke-test
```

이 명령이 JSON 형태의 `summary`, `likely_causes`, `checks`, `actions`, `warnings`를
출력하면 Qwen 연결이 정상입니다.

## 10. LLM 모드 API 테스트

DB-only 테스트와 LLM smoke test가 모두 성공한 뒤 LLM 모드로 API를 실행합니다.
API에서 LLM을 호출할 때는 Qwen thinking 출력을 줄이기 위해 질문 앞에 `/no_think`를 자동으로 붙입니다.

```bash
.venv/bin/uvicorn djcp_alarm_ai.main:app --reload
```

다른 터미널에서:

```bash
curl -s -X POST http://localhost:8000/v2/analyses/from-tag \
  -H 'Content-Type: application/json' \
  -d '{"tag_name":"BBAIT-801","question":"이 태그 값이 왜 상승했어?"}' \
  | jq '.answer'
```

정상 응답 예시는 아래 구조입니다.

```json
{
  "summary": "요약 문장",
  "likely_causes": [
    "가능 원인"
  ],
  "checks": [
    "점검 항목"
  ],
  "actions": [
    "조치 방향"
  ],
  "warnings": [
    "주의 사항"
  ]
}
```

API가 `503 Local LLM answer generation is unavailable.`를 반환하면 DB 조회는 되었지만
Qwen 답변 생성이 실패한 것입니다. 이때는 아래 순서로 확인합니다.

```bash
systemctl status ollama --no-pager
ollama list
.venv/bin/djcp-llm-smoke-test
```

Qwen 문제를 제외하고 DB/API만 다시 확인하려면:

```bash
LLM_BASE_URL= .venv/bin/uvicorn djcp_alarm_ai.main:app --reload
```

## Description 테이블 필드

Description은 `ai.tag_description` 단일 테이블에 저장됩니다. 런타임 조회는 항상
`tag.id` 기준입니다.

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
source_version
content_hash
is_verified
created_at
updated_at
```

`tag_name`은 동기화 시 `tag.tag_name`과 매칭해서 실제 `tag.id`를 찾는 용도입니다.
동기화 중 DB에 같은 `tag_name`이 여러 개 있으면 해당 항목은 ambiguous로 보고됩니다.
API 호출에서는 같은 경우 `asset_id`를 함께 전달해 태그를 확정합니다.
