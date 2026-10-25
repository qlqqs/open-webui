"""Key-hash/60s model cache. Values contain metadata only, never keys or headers."""

import asyncio
import copy
import hashlib
import json
import time
import aiohttp
from fastapi import HTTPException
from starlette.responses import JSONResponse
from .gateway import connection, headers

CACHE_TTL = 60
MAX_CACHE_ENTRIES = 256


KEY_UNAVAILABLE_CODES = {
    'INVALID_API_KEY',
    'API_KEY_INVALID',
    'API_KEY_DISABLED',
    'API_KEY_EXPIRED',
    'API_KEY_REVOKED',
    'API_KEY_NOT_FOUND',
    'API_KEY_REQUIRED',
    'INVALID_KEY',
    'KEY_INVALID',
    'KEY_DISABLED',
    'KEY_EXPIRED',
    'KEY_REVOKED',
}


class GatewayModelError(HTTPException):
    """Keep gateway diagnostics separate from FastAPI's nested `detail` field."""

    def __init__(self, status, code, message):
        normalized = code.upper()
        if normalized == 'INSUFFICIENT_BALANCE':
            detail = '账户余额不足'
        elif normalized in KEY_UNAVAILABLE_CODES:
            detail = '所选 Key 不可用'
        elif status == 429 or 'RATE_LIMIT' in normalized or normalized == 'TOO_MANY_REQUESTS':
            detail = '请求过于频繁'
        else:
            detail = '网关模型列表不可用'
        super().__init__(status, detail)
        self.gateway_error = {'status': status, 'code': code, 'message': message[:300]}

    @classmethod
    def from_body(cls, status, text):
        try:
            body = json.loads(text)
        except (ValueError, TypeError):
            body = {}
        if not isinstance(body, dict):
            body = {}
        error = body.get('error')
        error = error if isinstance(error, dict) else {}
        code = next(
            (v for v in (body.get('code'), error.get('code'), error.get('type')) if isinstance(v, str) and v),
            'GATEWAY_ERROR',
        )
        message = next(
            (v for v in (body.get('message'), error.get('message')) if isinstance(v, str)),
            text,
        )
        return cls(status, code, message)


def install_error_handler(app):
    async def handle(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={'detail': exc.detail, 's2a_gateway_error': exc.gateway_error},
        )

    app.add_exception_handler(GatewayModelError, handle)


async def fetch_models(url):
    try:
        async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url + '/models', headers=headers(), allow_redirects=False) as response:
                if response.status != 200:
                    raise GatewayModelError.from_body(response.status, await response.text(errors='replace'))
                try:
                    body = await response.json()
                except (ValueError, aiohttp.ContentTypeError):
                    raise GatewayModelError(502, 'GATEWAY_INVALID_RESPONSE', 'Invalid gateway model list') from None
                if not isinstance(body, dict) or not isinstance(body.get('data'), list):
                    raise GatewayModelError(502, 'GATEWAY_INVALID_RESPONSE', 'Invalid gateway model list')
                return body
    except (aiohttp.ClientError, asyncio.TimeoutError):
        # Do not expose exception strings containing credentials, URLs or socket details.
        raise GatewayModelError(502, 'GATEWAY_UNREACHABLE', 'Unable to reach gateway') from None


async def gateway_models(request, refresh=False):
    url, key, _ = connection()
    digest = hashlib.sha256(key.encode()).hexdigest()
    state = request.app.state
    if not hasattr(state, 'SUB2API_MODEL_CACHE'):
        state.SUB2API_MODEL_CACHE = {}
        state.SUB2API_MODEL_LOCK = asyncio.Lock()
    async with state.SUB2API_MODEL_LOCK:
        cache = state.SUB2API_MODEL_CACHE
        entry = cache.get(digest)
        if not refresh and entry and time.monotonic() - entry[0] < CACHE_TTL:
            models = copy.deepcopy(entry[1])
        else:
            # Refresh failures invalidate only this Key, never cache a failure or serve its stale success.
            cache.pop(digest, None)
            body = await fetch_models(url)
            # Do not let a gateway metadata field turn a model into a pipe/direct URL.
            models = [
                {
                    'id': item['id'],
                    'name': item.get('name', item['id']),
                    'object': 'model',
                    'created': item.get('created', 0),
                    'owned_by': 'openai',
                    'connection_type': 'external',
                    'urlIdx': 0,
                }
                for item in body.get('data', [])
                if isinstance(item, dict) and isinstance(item.get('id'), str)
            ]
            if len(cache) >= MAX_CACHE_ENTRIES:
                cache.pop(next(iter(cache)))
            cache[digest] = (time.monotonic(), copy.deepcopy(models))
        state.OPENAI_MODELS.update({m['id']: copy.deepcopy(m) for m in models})
        return {'data': models}
