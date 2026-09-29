"""NPZ 批量冷启动分析接口。"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from app.core.resource_guard import run_blocking
from app.core.config import get_settings

from app.api.deps import bci_service, inference_semaphore
from app.schemas.api import AnalyzeResponse
from app.services.bci_response import build_bci_response
from app.services.npz_reader import read_bci_npz

router = APIRouter(tags=["analyze"])
LOGGER = logging.getLogger(__name__)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    file: UploadFile = File(...),
    sampling_rate_hz: int = Form(250),
    unit: str = Form("uV", max_length=16),
) -> AnalyzeResponse:
    content = await file.read(get_settings().max_upload_mb*1024*1024+1)
    filename = file.filename or "upload.npz"
    try:
        batch = await run_blocking(read_bci_npz, filename, content, sampling_rate_hz, unit)
        del content
        if not bci_service.ready:
            raise HTTPException(
                status_code=503,
                detail="BCI 模型未就绪，请稍后重试",
            )
        async with inference_semaphore:
            probabilities = await run_blocking(
                bci_service.predict_proba, batch.x
            )
        return build_bci_response(
            source="upload",
            filename=filename,
            x=batch.x,
            y=batch.y,
            probabilities=probabilities,
        )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("BCI analyze failed filename=%s", filename)
        raise HTTPException(status_code=500, detail=f"模型推理失败：{type(exc).__name__}")
