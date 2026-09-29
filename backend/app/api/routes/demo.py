"""内置 S3 科研数据回放接口。"""

from fastapi import APIRouter, Query
from app.core.resource_guard import run_blocking

from app.api.deps import bci_service, inference_semaphore
from app.core.config import get_settings
from app.schemas.api import DemoSignalsResponse
from app.services.bci_response import build_bci_response

router = APIRouter(tags=["demo"])


@router.get("/demo/signals", response_model=DemoSignalsResponse)
async def get_demo_signals(
    trial_count: int = Query(8, ge=4, le=32),
) -> DemoSignalsResponse:
    settings = get_settings()
    count = min(trial_count, settings.max_intent_windows)
    x, y = bci_service.demo_batch(count)
    async with inference_semaphore:
        probabilities = await run_blocking(bci_service.predict_proba, x)
    return build_bci_response(
        source="demo",
        filename=None,
        x=x,
        y=y,
        probabilities=probabilities,
    )
