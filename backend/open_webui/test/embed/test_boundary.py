import asyncio
import json
from dataclasses import replace
import httpx
import pytest
from starlette.responses import JSONResponse
from open_webui.embed.settings import Settings
from open_webui.embed.sub2api_auth import Sub2APIAuthMiddleware
from open_webui.embed.gateway import (
    SUB2API_KEY,
    SUB2API_IMAGE_KEY,
    SUB2API_KEY_PLATFORM,
    SUB2API_CLIENT_IP,
    current_key,
)
from open_webui.embed import gateway
from open_webui.test.embed.smoke.run import identity

SETTINGS = Settings.from_env(
    {'S2A_EMBED_MODE': '1', 'S2A_GATEWAY_URL': 'http://127.0.0.1:28201', 'S2A_TRUSTED_PROXY_CIDRS': '127.0.0.1/32'}
)


async def echo(scope, receive, send):
    await asyncio.sleep(0.001)
    result = {
        'headers': {k.decode(): v.decode() for k, v in scope.get('headers', ())},
        'client': scope.get('client'),
        'key': SUB2API_KEY.get(),
        'image': SUB2API_IMAGE_KEY.get(),
        'platform': SUB2API_KEY_PLATFORM.get(),
        'ip': SUB2API_CLIENT_IP.get(),
    }
    await JSONResponse(result)(scope, receive, send)


def client(peer='127.0.0.1', app=echo, config=SETTINGS):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=Sub2APIAuthMiddleware(app, config), client=(peer, 43210)),
        base_url='http://test',
    )


@pytest.mark.asyncio
async def test_untrusted_peer_forgery_and_anonymous_static():
    async with client('192.0.2.1') as c:
        assert (await c.get('/api/config', headers=identity(1))).status_code == 403
        response = await c.get('/_app/test.js', headers=identity(1))
        assert response.status_code == 200
        assert not any(k.startswith('x-sub2api-') for k in response.json()['headers'])
        assert not response.json()['key']
        assert (await c.post('/static/a', headers=identity(1))).status_code == 403
        assert (await c.get('/api/config', headers={'Accept': 'text/html'})).status_code == 403
        assert (await c.get('/openai/config', headers={'Accept': 'text/html'})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'name,value',
    [
        ('X-Sub2API-Email', ''),
        ('X-Sub2API-Email', 'u2@sub2api.internal'),
        ('X-Sub2API-User-Id', '-1'),
        ('X-Sub2API-User-Id', '01'),
        ('X-Sub2API-User-Role', 'owner'),
        ('X-Sub2API-Key', 'a b'),
        ('X-Sub2API-Key-Platform', 'OpenAI'),
        ('X-Forwarded-For', '1.2.3.4, 5.6.7.8'),
    ],
)
async def test_missing_or_malformed_headers(name, value):
    async with client() as c:
        assert (await c.get('/api/config', headers={**identity(1), name: value})).status_code == 401


@pytest.mark.asyncio
async def test_duplicate_headers():
    async with client() as c:
        headers = list(identity(1).items()) + [('X-Sub2API-User-Role', 'admin')]
        assert (await c.get('/api/config', headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_context_isolation_and_reset_and_key_not_in_scope_headers():
    async with client() as c:

        async def one(uid):
            response = await c.get(
                '/api/config',
                headers={
                    **identity(uid),
                    'X-Sub2API-Key': f'key-{uid}',
                    'X-Sub2API-Image-Key': f'image-{uid}',
                    'X-Sub2API-Key-Platform': 'openai',
                },
            )
            body = response.json()
            assert body['key'] == f'key-{uid}' and body['image'] == f'image-{uid}'
            assert body['client'][0] == body['ip'] == f'203.0.113.{uid}'
            assert body['platform'] == 'openai'
            assert 'x-sub2api-key' not in body['headers']

        await asyncio.gather(*(one(uid) for uid in range(1, 30)))
    assert SUB2API_KEY.get() == SUB2API_IMAGE_KEY.get() == SUB2API_KEY_PLATFORM.get() == SUB2API_CLIENT_IP.get() == ''


@pytest.mark.asyncio
async def test_background_task_inherits_billing_context_after_parent_reset():
    ready = asyncio.Event()
    tasks = []

    async def app(scope, receive, send):
        async def worker():
            await ready.wait()
            return current_key()

        tasks.append(asyncio.create_task(worker()))
        await JSONResponse({})(scope, receive, send)

    async with client(app=app) as c:
        await c.get('/api/config', headers={**identity(1), 'X-Sub2API-Key': 'background-key'})
    assert SUB2API_KEY.get() == ''
    ready.set()
    assert await tasks[0] == 'background-key'


@pytest.mark.asyncio
async def test_exception_resets_context():
    async def failing(scope, receive, send):
        raise RuntimeError('test')

    async with client(app=failing) as c:
        with pytest.raises(RuntimeError):
            await c.get('/api/config', headers={**identity(1), 'X-Sub2API-Key': 'secret'})
    assert not SUB2API_KEY.get()


@pytest.mark.asyncio
async def test_websocket_and_polling_never_capture_key():
    captured = []

    async def socket_app(scope, receive, send):
        captured.append((SUB2API_KEY.get(), dict(scope['headers'])))

    scope = {
        'type': 'websocket',
        'path': '/ws/socket.io/',
        'client': ('127.0.0.1', 1234),
        'headers': [(k.lower().encode(), v.encode()) for k, v in {**identity(1), 'X-Sub2API-Key': 'stale'}.items()],
    }
    await Sub2APIAuthMiddleware(socket_app, SETTINGS)(scope, None, None)
    assert captured[0][0] == '' and b'x-sub2api-key' not in captured[0][1]
    async with client() as c:
        response = await c.get('/ws/socket.io/', headers={**identity(1), 'X-Sub2API-Key': 'stale'})
        assert response.json()['key'] == ''


@pytest.mark.asyncio
async def test_disabled_mode_is_passthrough():
    async with client('192.0.2.1', config=Settings()) as c:
        response = await c.get('/api/v1/memories', headers={'X-Sub2API-Key': 'untrusted'})
        assert response.status_code == 200
        assert response.json()['headers']['x-sub2api-key'] == 'untrusted'
        assert not response.json()['key']


def test_missing_key_and_image_fallback(monkeypatch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        current_key()
    assert error.value.status_code == 400 and error.value.detail == '请选择可用的 Key'
    token = SUB2API_KEY.set('dialog')
    try:
        assert current_key(image=True) == 'dialog'
        image = SUB2API_IMAGE_KEY.set('image')
        try:
            assert current_key(image=True) == 'image' and current_key() == 'dialog'
        finally:
            SUB2API_IMAGE_KEY.reset(image)
    finally:
        SUB2API_KEY.reset(token)


def test_gateway_origin_and_api_type(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(gateway, 'settings', SETTINGS)
    for url in ('http://127.0.0.1:28202/v1', 'http://127.0.0.1:28201@elsewhere/v1', 'https://127.0.0.1:28201/v1'):
        with pytest.raises(HTTPException):
            gateway.require_gateway_url(url)
    gateway.require_gateway_url('http://127.0.0.1:28201/v1')
    key = SUB2API_KEY.set('one')
    platform = SUB2API_KEY_PLATFORM.set('openai')
    try:
        assert gateway.connection() == ('http://127.0.0.1:28201/v1', 'one', {'api_type': 'responses'})
        with pytest.raises(HTTPException):
            gateway.reject_direct({'direct': True})
    finally:
        SUB2API_KEY.reset(key)
        SUB2API_KEY_PLATFORM.reset(platform)


def test_socket_identity_predicate(monkeypatch):
    from types import SimpleNamespace
    from open_webui.embed import sub2api_auth

    monkeypatch.setattr(sub2api_auth, 'settings', SETTINGS)
    environ = {'asgi.scope': {'headers': [(k.lower().encode(), v.encode()) for k, v in identity(1).items()]}}
    assert sub2api_auth.socket_identity_matches(SimpleNamespace(email='u1@sub2api.internal'), environ)
    assert not sub2api_auth.socket_identity_matches(SimpleNamespace(email='u2@sub2api.internal'), environ)
    assert not sub2api_auth.socket_identity_matches(SimpleNamespace(email='u1@sub2api.internal'), {})
    assert not sub2api_auth.socket_identity_matches(None, environ)


@pytest.mark.asyncio
@pytest.mark.parametrize('peer,expected', [('127.0.0.1', 401), ('192.0.2.1', 403)])
async def test_health_is_not_anonymous_exception(peer, expected):
    async with client(peer) as c:
        assert (await c.get('/health')).status_code == expected
        assert (await c.get('/static/favicon.png')).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'wire,expected',
    [
        ('Alice', 'Alice'),
        ('User%201', 'User 1'),
        ('%E7%94%A8%E6%88%B7%E5%90%8D', '用户名'),
        ('%e7%94%a8%e6%88%b7%e5%90%8d', '用户名'),
        ('%F0%9F%98%80', '😀'),
        ('%252F', '%2F'),
        ('A%2BB%20%26%20100%25', 'A+B & 100%'),
        ('A+B', 'A+B'),
        ('', ''),
    ],
)
async def test_trusted_percent_encoded_name_on_http_and_websocket(wire, expected):
    from urllib.parse import quote, unquote

    headers = {**identity(1), 'X-Sub2API-Name': wire}
    async with client() as c:
        response = await c.get('/api/config', headers=headers)
        assert response.status_code == 200, response.text
        name = response.json()['headers']['x-sub2api-name']
        assert name.isascii() and name == quote(expected, safe='')
        assert unquote(name, encoding='utf-8', errors='strict') == expected
    captured = []

    async def app(scope, receive, send):
        captured.append(dict(scope['headers'])[b'x-sub2api-name'])

    await Sub2APIAuthMiddleware(app, SETTINGS)(
        {
            'type': 'websocket',
            'path': '/ws/socket.io/',
            'client': ('127.0.0.1', 1234),
            'headers': [(k.lower().encode(), v.encode('ascii')) for k, v in headers.items()],
        },
        None,
        None,
    )
    assert captured == [quote(expected, safe='').encode('ascii')]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'wire',
    [
        b'%',
        b'%A',
        b'%GG',
        b'%ff',
        b'%C0%AF',
        b'%ED%A0%80',
        b'%F0%9F',
        b'%00',
        b'%0D%0A',
        b'%7F',
        '用户名'.encode('utf-8'),
        b'\xff',
    ],
)
async def test_invalid_name_rejected_before_upstream_http_or_websocket(wire):
    from unittest.mock import AsyncMock

    headers = [(k.lower().encode(), v.encode()) for k, v in identity(1).items() if k != 'X-Sub2API-Name']
    headers.append((b'x-sub2api-name', wire))
    async with client() as c:
        response = await c.get('/api/config', headers=headers)
        assert response.status_code == 401
        assert response.json() == {'detail': '无效的用户显示名'}
    app, send = AsyncMock(), AsyncMock()
    await Sub2APIAuthMiddleware(app, SETTINGS)(
        {
            'type': 'websocket',
            'path': '/ws/socket.io/',
            'client': ('127.0.0.1', 1234),
            'headers': headers,
        },
        None,
        send,
    )
    app.assert_not_awaited()
    send.assert_awaited_once_with({'type': 'websocket.close', 'code': 1008})


@pytest.mark.asyncio
async def test_config_mismatch_does_not_sync_stale_account(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from open_webui.embed import sub2api_auth

    user = SimpleNamespace(email='u1@sub2api.internal', role='admin')
    sync = AsyncMock(return_value=user)
    monkeypatch.setattr(sub2api_auth, 'sync_user', sync)
    assert await sub2api_auth.sync_config_user(user, {'x-sub2api-email': 'u2@sub2api.internal'}) is None
    sync.assert_not_awaited()
    assert user.role == 'admin'
    headers = {'x-sub2api-email': user.email, 'x-sub2api-user-role': 'admin'}
    assert await sub2api_auth.sync_config_user(user, headers) is user
    sync.assert_awaited_once_with(user, headers)
