from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas import HealthResponse


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    if (
        getattr(request.app.state, "chat_service", None) is None
        or getattr(request.app.state, "auth_service", None) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能体服务尚未就绪",
        )
    return HealthResponse(status="ready")
