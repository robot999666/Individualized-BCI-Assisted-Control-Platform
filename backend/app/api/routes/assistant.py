"""项目 RAG 智能问答接口。"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import assistant_service
from app.schemas.assistant import (
    AssistantChatResponse,
    AssistantHealthResponse,
    AssistantQuestion,
)
from app.services.project_assistant import (
    AssistantConfigurationError,
    AssistantBusyError,
    AssistantProviderError,
)

router = APIRouter(prefix="/assistant", tags=["project-assistant"])


@router.get("/health", response_model=AssistantHealthResponse)
def assistant_health() -> AssistantHealthResponse:
    index = assistant_service.index
    return AssistantHealthResponse(
        status="ok" if index.ready and assistant_service.provider_configured else "degraded",
        rag_ready=index.ready,
        document_count=len(index.documents),
        chunk_count=len(index.chunks),
        provider_configured=assistant_service.provider_configured,
        model=assistant_service.settings.openai_model,
        error=index.error,
    )


@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(payload: AssistantQuestion) -> AssistantChatResponse:
    try:
        return await assistant_service.chat(payload.question)
    except AssistantBusyError as exc:
        raise HTTPException(status_code=429, detail="智答正在处理其他问题，请稍后再试。") from exc
    except AssistantConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="项目知识服务暂时不可用，请稍后再试。",
        ) from exc
    except AssistantProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="项目知识服务暂时不可用，请稍后再试。",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="项目知识服务暂时不可用，请稍后再试。",
        ) from exc
