"""健康检查接口。"""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    # Compatibility alias; details are available only from admin-only /health/detail.
    return {"status": "ok"}
