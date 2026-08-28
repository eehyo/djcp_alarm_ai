from fastapi import FastAPI

from djcp_alarm_ai.api import router
from djcp_alarm_ai.config import get_settings
from djcp_alarm_ai.manual_api import router as manual_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.include_router(router)
    app.include_router(manual_router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
