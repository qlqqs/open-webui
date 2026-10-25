"""Gateway model failures retain status/diagnostics, never becoming cached views."""

import asyncio
import hashlib
import json
from types import SimpleNamespace

import aiohttp
import httpx
import pytest
from fastapi import FastAPI, HTTPException

from open_webui.embed import gateway, models
from open_webui.embed.gateway import SUB2API_KEY
from open_webui.embed.settings import Settings


@pytest.mark.parametrize(
    'status,body,code,detail,message',
    [
        (
            403,
            {'code': 'INSUFFICIENT_BALANCE', 'message': 'Insufficient account balance'},
            'INSUFFICIENT_BALANCE',
            '账户余额不足',
            'Insufficient account balance',
        ),
        *[
            (401, {'code': code, 'message': 'key unavailable'}, code, '所选 Key 不可用', 'key unavailable')
            for code in sorted(models.KEY_UNAVAILABLE_CODES)
        ],
        (
            403,
            {'error': {'code': 'invalid_api_key', 'type': 'invalid_request_error', 'message': 'bad key'}},
            'invalid_api_key',
            '所选 Key 不可用',
            'bad key',
        ),
        (
            403,
            {'code': 'API_KEY_EXPIRED', 'message': 'API key 已过期'},
            'API_KEY_EXPIRED',
            '所选 Key 不可用',
            'API key 已过期',
        ),
        (
            403,
            {'error': {'type': 'INSUFFICIENT_BALANCE', 'message': '余额'}},
            'INSUFFICIENT_BALANCE',
            '账户余额不足',
            '余额',
        ),
        (
            429,
            {'error': {'code': None, 'type': 'rate_limit_error', 'message': 'slow down'}},
            'rate_limit_error',
            '请求过于频繁',
            'slow down',
        ),
        *[
            (429, {'code': code, 'message': 'slow down'}, code, '请求过于频繁', 'slow down')
            for code in ('RATE_LIMITED', 'INVALID_AUTH_RATE_LIMITED', 'API_KEY_RATE_LIMITED', 'USAGE_LIMIT_EXCEEDED')
        ],
        (400, {'code': 'RATE_LIMIT_EXCEEDED', 'message': 'wait'}, 'RATE_LIMIT_EXCEEDED', '请求过于频繁', 'wait'),
        (429, {'error': {'message': 'wait'}}, 'GATEWAY_ERROR', '请求过于频繁', 'wait'),
        (
            503,
            {'code': 'API_KEY_AUTH_OVERLOADED', 'message': 'later'},
            'API_KEY_AUTH_OVERLOADED',
            '网关模型列表不可用',
            'later',
        ),
        (401, {'code': 'USER_INACTIVE', 'message': 'inactive'}, 'USER_INACTIVE', '网关模型列表不可用', 'inactive'),
        (500, {'code': 'UNKNOWN', 'message': '错误😀' * 200}, 'UNKNOWN', '网关模型列表不可用', ('错误😀' * 200)[:300]),
        (
            502,
            {'code': ['bad'], 'error': {'code': {}, 'type': 'upstream_error', 'message': 'bad upstream'}},
            'upstream_error',
            '网关模型列表不可用',
            'bad upstream',
        ),
        (
            403,
            {
                'code': 'INSUFFICIENT_BALANCE',
                'message': 'top',
                'error': {'code': 'INVALID_API_KEY', 'message': 'nested'},
            },
            'INSUFFICIENT_BALANCE',
            '账户余额不足',
            'top',
        ),
    ],
)
def test_error_shapes_and_chinese_prompts(status, body, code, detail, message):
    error = models.GatewayModelError.from_body(status, json.dumps(body))
    assert error.status_code == status
    assert error.detail == detail
    assert error.gateway_error == {'status': status, 'code': code, 'message': message}


@pytest.mark.parametrize('text', ['', '<html>Bad gateway</html>', 'null', '[]', '"error"', '{malformed', '故障' * 301])
def test_non_json_or_non_object_error(text):
    error = models.GatewayModelError.from_body(503, text)
    assert error.gateway_error == {'status': 503, 'code': 'GATEWAY_ERROR', 'message': text[:300]}


@pytest.fixture
def gateway_stub(monkeypatch):
    monkeypatch.setattr(
        gateway,
        'settings',
        Settings.from_env(
            {
                'S2A_EMBED_MODE': '1',
                'S2A_GATEWAY_URL': 'http://127.0.0.1:28201',
            }
        ),
    )
    stub = SimpleNamespace(status=200, body={'data': [{'id': 'ok'}]}, error=None, calls=[])

    class Response:
        @property
        def status(self):
            return stub.status

        async def __aenter__(self):
            if stub.error:
                raise stub.error
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self, **kwargs):
            return json.dumps(stub.body)

        async def json(self):
            if isinstance(stub.body, Exception):
                raise stub.body
            return stub.body

    class Session:
        def __init__(self, **kwargs):
            assert kwargs['timeout'].total == 15

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, url, **kwargs):
            assert url == 'http://127.0.0.1:28201/v1/models'
            assert kwargs['allow_redirects'] is False
            stub.calls.append(kwargs['headers']['Authorization'])
            return Response()

    monkeypatch.setattr(models.aiohttp, 'ClientSession', Session)
    return stub


def request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={})))


async def get(req, key='test-key', refresh=False):
    token = SUB2API_KEY.set(key)
    try:
        return await models.gateway_models(req, refresh)
    finally:
        SUB2API_KEY.reset(token)


@pytest.mark.asyncio
async def test_failure_retry_refresh_and_other_key_cache(gateway_stub):
    stub, req = gateway_stub, request()
    await get(req, 'other-key')
    await get(req)
    assert len(stub.calls) == 2
    stub.status, stub.body = 403, {'code': 'INSUFFICIENT_BALANCE', 'message': 'Insufficient account balance'}
    for refresh in (True, False):
        with pytest.raises(models.GatewayModelError) as error:
            await get(req, refresh=refresh)
        assert error.value.status_code == 403
        assert set(req.app.state.SUB2API_MODEL_CACHE) == {hashlib.sha256(b'other-key').hexdigest()}
    assert len(stub.calls) == 4
    assert (await get(req, 'other-key'))['data'][0]['id'] == 'ok'
    assert len(stub.calls) == 4
    stub.status, stub.body = 200, {'data': [{'id': 'recovered'}]}
    assert (await get(req))['data'][0]['id'] == 'recovered'
    assert (await get(req))['data'][0]['id'] == 'recovered'
    assert len(stub.calls) == 5
    assert set(req.app.state.OPENAI_MODELS) == {'ok', 'recovered'}


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [aiohttp.ClientConnectionError('secret URL/key'), asyncio.TimeoutError('secret')])
async def test_network_errors_502_safe_and_not_cached(gateway_stub, error):
    req = request()
    gateway_stub.error = error
    for _ in range(2):
        with pytest.raises(models.GatewayModelError) as caught:
            await get(req)
        assert caught.value.status_code == 502
        assert caught.value.gateway_error == {
            'status': 502,
            'code': 'GATEWAY_UNREACHABLE',
            'message': 'Unable to reach gateway',
        }
        assert not req.app.state.SUB2API_MODEL_CACHE
        assert not req.app.state.OPENAI_MODELS
    assert len(gateway_stub.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [None, [], {}, {'data': {}}, ValueError('invalid JSON')])
async def test_invalid_success_payload_not_cached(gateway_stub, body):
    gateway_stub.body = body
    req = request()
    with pytest.raises(models.GatewayModelError) as error:
        await get(req)
    assert error.value.gateway_error['code'] == 'GATEWAY_INVALID_RESPONSE'
    assert error.value.status_code == 502
    assert not req.app.state.SUB2API_MODEL_CACHE


@pytest.mark.asyncio
async def test_cancellation_not_converted_to_gateway_error(gateway_stub):
    gateway_stub.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await get(request())


@pytest.mark.asyncio
async def test_registered_handler_flat_body_and_regular_http_errors_unchanged(gateway_stub):
    app = FastAPI()
    models.install_error_handler(app)
    req = request()

    @app.get('/api/models')
    async def route():
        return await get(req)

    @app.get('/ordinary-error')
    async def ordinary():
        raise HTTPException(401, 'original error')

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:28200') as client:
        gateway_stub.status, gateway_stub.body = 403, {
            'code': 'INSUFFICIENT_BALANCE',
            'message': 'Insufficient account balance',
        }
        response = await client.get('/api/models')
        assert response.status_code == 403
        assert response.json() == {
            'detail': '账户余额不足',
            's2a_gateway_error': {
                'status': 403,
                'code': 'INSUFFICIENT_BALANCE',
                'message': 'Insufficient account balance',
            },
        }
        gateway_stub.error = asyncio.TimeoutError()
        response = await client.get('/api/models')
        assert response.status_code == 502
        assert response.json()['s2a_gateway_error']['code'] == 'GATEWAY_UNREACHABLE'
        response = await client.get('/ordinary-error')
        assert response.status_code == 401 and response.json() == {'detail': 'original error'}
