"""测试公共配置：确保 backend 目录可导入 app 包。"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def reset_request_limits():
    # Each test is a separate traffic scenario; testclient shares a fixed IP.
    from app.main import app
    from app.core.resource_guard import RequestLimitsMiddleware
    from app.platform.routes import login_attempts
    if app.middleware_stack is None:
        app.middleware_stack=app.build_middleware_stack()
    middleware=app.middleware_stack
    while hasattr(middleware, 'app'):
        if isinstance(middleware, RequestLimitsMiddleware):
            middleware.limiter.entries.clear()
            break
        middleware=middleware.app
    login_attempts.clear()

