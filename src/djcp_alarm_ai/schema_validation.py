from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


REQUIRED_OPERATIONAL_COLUMNS = {
    "asset": {
        "id",
        "parent_id",
        "code",
        "name",
        "node_kind",
        "asset_type",
        "manufacturer",
        "model_name",
        "serial_number",
        "rated_capacity",
        "rated_speed",
        "status",
        "system_name",
        "location",
        "criticality",
        "owner_dept",
        "owner_person",
        "install_date",
        "operation_time_tag_name",
        "last_alarm",
        "image_path",
        "description",
        "created_at",
    },
    "tag": {
        "id",
        "asset_id",
        "tag_code",
        "tag_name",
        "description",
        "unit",
        "alarm_high",
        "alarm_low",
        "alarm_enabled",
        "current_value",
        "last_updated_at",
        "created_at",
    },
    "alarm": {
        "id",
        "tag_id",
        "start_time",
        "end_time",
        "value",
        "setpoint",
        "severity",
        "state",
        "ack_by",
    },
    "maintenance": {
        "id",
        "asset_id",
        "work_name",
        "maint_type",
        "priority",
        "plan_start_dt",
        "plan_end_dt",
        "actual_end_dt",
        "owner",
        "owner_dept",
        "status",
        "outsource_company",
        "approver",
        "budget_cost",
        "actual_cost",
        "inspection_result",
        "next_due_date",
        "notes",
        "created_at",
    },
}

REQUIRED_FOREIGN_KEYS = {
    ("asset", "parent_id", "asset", "id"),
    ("tag", "asset_id", "asset", "id"),
    ("alarm", "tag_id", "tag", "id"),
    ("maintenance", "asset_id", "asset", "id"),
}

REQUIRED_NOT_NULL_COLUMNS = {
    "asset": {
        "id",
        "code",
        "name",
        "node_kind",
        "asset_type",
        "manufacturer",
        "model_name",
        "serial_number",
        "rated_capacity",
        "rated_speed",
        "status",
        "criticality",
        "system_name",
        "location",
        "owner_dept",
        "owner_person",
        "created_at",
    },
    "tag": {
        "id",
        "asset_id",
        "tag_code",
        "tag_name",
        "unit",
        "alarm_enabled",
        "created_at",
    },
    "alarm": {
        "id",
        "tag_id",
        "start_time",
        "value",
        "setpoint",
        "severity",
        "state",
    },
    "maintenance": {
        "id",
        "asset_id",
        "work_name",
        "maint_type",
        "priority",
        "owner",
        "owner_dept",
        "status",
        "created_at",
    },
}

SCHEMA_COLUMNS_SQL = text(
    """
    SELECT table_name, column_name, is_nullable
    FROM information_schema.columns
    WHERE table_schema = :schema_name
      AND table_name IN ('asset', 'tag', 'alarm', 'maintenance')
    ORDER BY table_name, ordinal_position
    """
)

SCHEMA_FOREIGN_KEYS_SQL = text(
    """
    SELECT
        tc.table_name,
        kcu.column_name,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON kcu.constraint_name = tc.constraint_name
     AND kcu.constraint_schema = tc.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
     AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = :schema_name
      AND tc.table_name IN ('asset', 'tag', 'alarm', 'maintenance')
    ORDER BY tc.table_name, kcu.ordinal_position
    """
)


def check_operational_schema(db: Session, schema_name: str = "public") -> dict[str, Any]:
    columns = db.execute(SCHEMA_COLUMNS_SQL, {"schema_name": schema_name}).mappings()
    foreign_keys = db.execute(
        SCHEMA_FOREIGN_KEYS_SQL,
        {"schema_name": schema_name},
    ).mappings()
    return build_schema_report(columns, foreign_keys=foreign_keys, schema_name=schema_name)


def build_schema_report(
    rows: Iterable[dict[str, Any]],
    *,
    foreign_keys: Iterable[dict[str, Any]] = (),
    schema_name: str = "public",
) -> dict[str, Any]:
    actual: dict[str, set[str]] = defaultdict(set)
    actual_not_null: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        table_name = str(row["table_name"])
        column_name = str(row["column_name"])
        actual[table_name].add(column_name)
        if str(row.get("is_nullable", "")).upper() == "NO":
            actual_not_null[table_name].add(column_name)

    missing_tables = sorted(set(REQUIRED_OPERATIONAL_COLUMNS) - set(actual))
    missing_columns = {
        table: sorted(required - actual.get(table, set()))
        for table, required in REQUIRED_OPERATIONAL_COLUMNS.items()
        if required - actual.get(table, set())
    }
    actual_foreign_keys = {
        (
            str(row["table_name"]),
            str(row["column_name"]),
            str(row["foreign_table_name"]),
            str(row["foreign_column_name"]),
        )
        for row in foreign_keys
    }
    missing_foreign_keys = [
        f"{table}.{column} -> {foreign_table}.{foreign_column}"
        for table, column, foreign_table, foreign_column in sorted(
            REQUIRED_FOREIGN_KEYS - actual_foreign_keys
        )
    ]
    nullable_contract_violations = [
        f"{table}.{column}"
        for table, required in REQUIRED_NOT_NULL_COLUMNS.items()
        for column in sorted(required & actual.get(table, set()) - actual_not_null.get(table, set()))
    ]
    return {
        "ok": (
            not missing_tables
            and not missing_columns
            and not missing_foreign_keys
            and not nullable_contract_violations
        ),
        "schema_name": schema_name,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "missing_foreign_keys": missing_foreign_keys,
        "nullable_contract_violations": nullable_contract_violations,
    }
