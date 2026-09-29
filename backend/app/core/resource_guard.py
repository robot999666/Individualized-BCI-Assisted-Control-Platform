"""Bound request resources before JSON/multipart parsing, including chunked bodies."""

import asyncio
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
import hashlib
import json
from tempfile import SpooledTemporaryFile
import time

from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.core.config import get_settings


class WindowLimiter:
    def __init__(self, max_keys=4096):
        self.entries = OrderedDict()
        self.max_keys = max_keys

    def allow(self, key, limit, seconds=60):
        now = time.monotonic()
        # Do not clear all counters when full: that would reset attackers' limits.
        while self.entries and next(iter(self.entries.values()))[-1] <= now-seconds:
            self.entries.popitem(last=False)
        recent = self.entries.get(key)
        if recent is None:
            if len(self.entries) >= self.max_keys:
                return False
            recent = deque()
            self.entries[key] = recent
        while recent and recent[0] <= now-seconds:
            recent.popleft()
        if len(recent) >= limit:
            return False
        recent.append(now)
        self.entries.move_to_end(key)
        return True


async def run_blocking(function, *args, **kwargs):
    """Cancellation must not free admission slots while a worker still owns arrays."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Retrieve errors from the completed worker.
        raise


class WorkSlots:
    def __init__(self, capacity):
        self.capacity = capacity
        self.active = 0

    @asynccontextmanager
    async def slot(self):
        if self.active >= self.capacity:
            raise HTTPException(503, "服务正在处理其他任务，请稍后重试", headers={"Retry-After": "2"})
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1


password_slots = WorkSlots(2)


class RequestLimitsMiddleware:
    def __init__(self, app):
        self.app = app
        self.settings = get_settings()
        self.limiter = WindowLimiter()
        self.active = 0
        self.heavy = 0
        self.heavy_owners = set()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        original_send = send

        async def send(message):
            if message['type'] == 'http.response.start':
                protected = {b'x-content-type-options': b'nosniff', b'x-frame-options': b'DENY',
                             b'referrer-policy': b'same-origin', b'cache-control': b'no-store',
                             b'content-security-policy': b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"}
                # Development API docs need their own scripts; production disables docs.
                if not self.settings.production and scope['path'] in {'/docs', '/redoc', '/docs/oauth2-redirect'}:
                    protected.pop(b'content-security-policy')
                existing = [(k,v) for k,v in message.get('headers', []) if k.lower() not in protected]
                message = {**message, 'headers': existing+list(protected.items())}
            await original_send(message)

        path = scope['path'].rstrip('/')
        method = scope['method']
        # Keep stop/control available when bulk processing is saturated.
        control = path.endswith(('/control', '/emergency-stop', '/auth/logout'))
        heavy = (path.endswith(('/analyze', '/signals', '/calibrate-demo', '/calibrate-upload',
                              '/evaluate', '/upload', '/eog-upload', '/analyze-upload', '/demo-analyze',
                              '/data-sources')) or (method == 'POST' and path.endswith('/sessions')))
        owner = hashlib.sha256(headers.get(b'cookie', b'')[:4096]).digest()
        ip = (scope.get('client') or ('unknown', 0))[0]

        async def reject(status, detail):
            response = JSONResponse({'detail': detail}, status_code=status,
                                    headers={'Retry-After': '2'} if status in (429, 503) else {})
            await response(scope, receive, send)

        if len(scope.get('query_string', b'')) > 4096 or sum(len(k)+len(v) for k,v in scope['headers']) > 16384 or len(scope['path']) > 2048:
            return await reject(431, '请求头或网址过长')
        if not control and not self.limiter.allow((ip, 'write' if method not in {'GET','HEAD','OPTIONS'} else 'read'),
                                                180 if method not in {'GET','HEAD','OPTIONS'} else 1800):
            return await reject(429, '请求过于频繁，请稍后重试')
        if self.active >= self.settings.max_active_requests+(8 if control else 0):
            return await reject(503, '服务繁忙，请稍后重试')
        if control and not self.limiter.allow((ip, 'control'), 600):
            return await reject(429, '控制请求过于频繁，请稍后重试')
        if heavy and (self.heavy >= self.settings.max_bulk_requests or owner in self.heavy_owners):
            return await reject(503, '数据处理任务正在运行，请稍后重试')
        if heavy and not self.limiter.allow((ip, 'bulk'), 60):
            return await reject(429, '数据处理请求过于频繁，请稍后重试')

        upload = headers.get(b'content-type', b'').lower().startswith(b'multipart/form-data')
        limit = (self.settings.max_upload_mb+1)*1024*1024 if upload else self.settings.max_json_body_kb*1024
        lengths = [value for name,value in scope['headers'] if name == b'content-length']
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                return await reject(400, '无效的 Content-Length')
            if len(lengths[0]) > 10 or int(lengths[0]) > limit:
                return await reject(413, '请求内容超过大小限制')
        if headers.get(b'content-encoding', b'identity').lower() != b'identity':
            return await reject(415, '不支持压缩请求体')
        self.active += 1
        if heavy:
            self.heavy += 1
            self.heavy_owners.add(owner)
        try:
            # Disk spooling bounds RAM even if a client omits Content-Length.
            with SpooledTemporaryFile(max_size=1024*1024) as body:
                size = 0
                try:
                    async with asyncio.timeout(self.settings.request_body_timeout_seconds):
                        while True:
                            message = await receive()
                            if message['type'] == 'http.disconnect':
                                return
                            chunk = message.get('body', b'')
                            size += len(chunk)
                            if size > limit:
                                return await reject(413, '请求内容超过大小限制')
                            body.write(chunk)
                            if not message.get('more_body', False):
                                break
                except TimeoutError:
                    return await reject(408, '请求内容接收超时')
                if lengths and size != int(lengths[0]):
                    return await reject(400, '请求长度不匹配')
                content_type=headers.get(b'content-type', b'').split(b';')[0].lower()
                if size and (not content_type or content_type == b'application/json' or content_type.endswith(b'+json')):
                    body.seek(0)
                    try:
                        parsed=json.loads(body.read())
                        pending=[(parsed, 0)]
                        while pending:
                            value,depth=pending.pop()
                            if depth > 64:
                                return await reject(422, 'JSON 嵌套层数超过限制')
                            if isinstance(value, (list, dict)):
                                pending.extend((item,depth+1) for item in (value.values() if isinstance(value,dict) else value))
                        del parsed, pending
                    except (ValueError, RecursionError):
                        return await reject(422, 'JSON 格式无效或嵌套过深')
                body.seek(0)
                delivered = 0

                async def bounded_receive():
                    nonlocal delivered
                    if delivered < size:
                        chunk = body.read(65536)
                        delivered += len(chunk)
                        return {'type': 'http.request', 'body': chunk, 'more_body': delivered < size}
                    if delivered == size:
                        delivered += 1
                        return {'type': 'http.request', 'body': b'', 'more_body': False}
                    return await receive()

                await self.app(scope, bounded_receive, send)
        finally:
            self.active -= 1
            if heavy:
                self.heavy -= 1
                self.heavy_owners.discard(owner)
