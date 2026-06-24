from fastapi import APIRouter, Request

from app.schemas.api import GenerateMinutesRequest, SuccessResponse
from app.schemas.workflow import MinutesGenerationCommand

router = APIRouter(prefix="/minutes", tags=["minutes"])


@router.post("/generate", response_model=SuccessResponse)
async def generate_minutes(payload: GenerateMinutesRequest, request: Request) -> SuccessResponse:
    workflow = request.app.state.container.minutes_workflow
    result = await workflow.execute(MinutesGenerationCommand(**payload.model_dump()))
    return SuccessResponse(data=result)
