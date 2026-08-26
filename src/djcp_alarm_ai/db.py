from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from djcp_alarm_ai.config import get_settings


settings = get_settings()

# 신규 3-DB 엔진 (모두 같은 서버, DB명만 다름)
#   FDAS         : 태그·알람·화면
#   FDAS_AMS     : 설비·정비·LOTO
#   djcp_alarm_ai: AI 지식/RAG (pgvector)
fdas_engine = create_engine(settings.fdas_database_url, pool_pre_ping=True)
ams_engine = create_engine(settings.ams_database_url, pool_pre_ping=True)
ai_engine = create_engine(settings.ai_database_url, pool_pre_ping=True)

FdasSession = sessionmaker(bind=fdas_engine, autoflush=False, autocommit=False)
AmsSession = sessionmaker(bind=ams_engine, autoflush=False, autocommit=False)
AiSession = sessionmaker(bind=ai_engine, autoflush=False, autocommit=False)


def get_db_fdas() -> Generator[Session, None, None]:
    db = FdasSession()
    try:
        yield db
    finally:
        db.close()


def get_db_ams() -> Generator[Session, None, None]:
    db = AmsSession()
    try:
        yield db
    finally:
        db.close()


def get_db_ai() -> Generator[Session, None, None]:
    db = AiSession()
    try:
        yield db
    finally:
        db.close()
