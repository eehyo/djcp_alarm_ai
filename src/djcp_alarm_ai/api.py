from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from djcp_alarm_ai.db import get_db_ai, get_db_ams, get_db_fdas
from djcp_alarm_ai.errors import AmbiguousTagError, AnswerGenerationError, NotFoundError
from djcp_alarm_ai.generator import build_answer_generator
from djcp_alarm_ai.manual_rag import build_manual_retriever
from djcp_alarm_ai.repositories import DescriptionRepository, OperationalRepository
from djcp_alarm_ai.schemas import (
    AlarmAnalysisRequest,
    AlarmInfo,
    AnalysisResponse,
    TagAnalysisRequest,
)
from djcp_alarm_ai.service import AlarmAnalysisService


router = APIRouter(prefix="/v2/analyses", tags=["analyses-v2"])


def get_service(
    fdas_db: Session = Depends(get_db_fdas),
    ams_db: Session = Depends(get_db_ams),
    ai_db: Session = Depends(get_db_ai),
) -> AlarmAnalysisService:
    return AlarmAnalysisService(
        operational_repository=OperationalRepository(fdas_db, ams_db),
        description_repository=DescriptionRepository(ai_db, fdas_db),
        answer_generator=build_answer_generator(),
        manual_retriever=build_manual_retriever(ai_db),
    )


@router.get("/recent-alarms", response_model=list[AlarmInfo])
def list_recent_alarms(
    service: AlarmAnalysisService = Depends(get_service),
) -> list[AlarmInfo]:
    return service.list_recent_alarms()


@router.post("/from-recent-alarm", response_model=AnalysisResponse)
def analyze_recent_alarm(
    payload: AlarmAnalysisRequest,
    service: AlarmAnalysisService = Depends(get_service),
) -> AnalysisResponse:
    try:
        return service.analyze_recent_alarm(
            payload.tag_id,
            payload.timestamp,
            payload.question,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local LLM answer generation is unavailable.",
        ) from exc


@router.post("/from-history", response_model=AnalysisResponse)
def analyze_history(
    payload: AlarmAnalysisRequest,
    service: AlarmAnalysisService = Depends(get_service),
) -> AnalysisResponse:
    try:
        return service.analyze_history(
            payload.tag_id,
            payload.timestamp,
            payload.question,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local LLM answer generation is unavailable.",
        ) from exc


@router.post("/from-tag", response_model=AnalysisResponse)
def analyze_tag(
    payload: TagAnalysisRequest,
    service: AlarmAnalysisService = Depends(get_service),
) -> AnalysisResponse:
    try:
        return service.analyze_tag(payload.tag_name, payload.question)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AmbiguousTagError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "candidates": [candidate.model_dump() for candidate in exc.candidates],
            },
        ) from exc
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local LLM answer generation is unavailable.",
        ) from exc
