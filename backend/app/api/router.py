"""汇总所有 API 路由。"""

from fastapi import APIRouter

from app.api.routes import analyze, assistant, demo
from app.platform.routes import router as platform_router

api_router = APIRouter()
api_router.include_router(platform_router)
api_router.include_router(demo.router)
api_router.include_router(analyze.router)
api_router.include_router(assistant.router)
