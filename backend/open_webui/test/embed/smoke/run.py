"""Local-only stage-1 integration smoke.

Run with the slim venv Python. Ports: backend 28200, gateway 28201, proxy 28202.
Temporary DB/logs are isolated; no existing deployment, key or database is used.
"""

import asyncio
import base64
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import uuid
import socketio
import time
import zipfile
from urllib.parse import quote

import aiohttp
from aiohttp import web
import httpx

BACKEND = Path(__file__).resolve().parents[4]
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=')


def pdf():
    text = b'BT /F1 18 Tf 72 720 Td (PDF-STAGE1-MARKER) Tj ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length %d >>\nstream\n' % len(text) + text + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = io.BytesIO()
    out.write(b'%PDF-1.4\n')
    offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f'{n} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = out.tell()
    out.write(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets:
        out.write(f'{offset:010d} 00000 n \n'.encode())
    out.write(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return out.getvalue()


def docx():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr(
            'word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX-STAGE1-MARKER</w:t></w:r></w:p></w:body></w:document>',
        )
    return out.getvalue()


def display_name(uid):
    return '用户名 😀 + 100% %2F' if str(uid) == '1' else f'User {uid}'


def identity(uid, role='user'):
    return {
        'X-Sub2API-User-Id': str(uid),
        'X-Sub2API-Email': f'u{uid}@sub2api.internal',
        'X-Sub2API-Name': quote(display_name(uid), safe=''),
        'X-Sub2API-User-Role': role,
        'X-Forwarded-For': f'203.0.113.{uid}',
        'X-Real-IP': f'203.0.113.{uid}',
    }


class Harness:
    def __init__(self):
        self.records = []
        self.directory = Path(tempfile.mkdtemp(prefix='s2a-stage1-'))
        self.runners = []
        self.sockets = []
        self.process = None
        self.log = None
        self.response_image_url = None
        self.model_errors = {}

    async def gateway(self, request):
        body = None
        if request.can_read_body:
            if request.content_type == 'application/json':
                body = await request.json()
            else:
                body = {'multipart': True}
        key = request.headers.get('Authorization', '')
        self.records.append(
            {
                'path': request.path,
                'key': key,
                'xff': request.headers.get('X-Forwarded-For'),
                'cookie': request.headers.get('Cookie'),
                'body': body,
            }
        )
        if request.path == '/v1/models':
            if key in self.model_errors:
                status, body = self.model_errors[key]
                if isinstance(body, str):
                    return web.Response(status=status, text=body)
                return web.json_response(body, status=status)
            suffix = key.rsplit('-', 1)[-1]
            return web.json_response({'data': [{'id': 'common'}, {'id': 'only-' + suffix}]})
        if request.path in ('/v1/images/generations', '/v1/images/edits'):
            item = (
                {'url': self.response_image_url}
                if self.response_image_url
                else {'b64_json': base64.b64encode(PNG).decode()}
            )
            return web.json_response({'data': [item]})
        if request.path == '/image.png':
            return web.Response(body=PNG, content_type='image/png')
        if request.path == '/redirect.png':
            raise web.HTTPFound('http://127.0.0.1:28203/forbidden')
        if request.path == '/v1/embeddings':
            return web.json_response({'data': [{'embedding': [0.1, 0.2]}]})
        if request.path == '/v1/responses':
            response = {
                'id': 'resp_stage1',
                'object': 'response',
                'status': 'completed',
                'model': body['model'],
                'output': [
                    {
                        'id': 'msg_stage1',
                        'type': 'message',
                        'role': 'assistant',
                        'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'Stage1 response', 'annotations': []}],
                    }
                ],
                'usage': {'input_tokens': 8, 'output_tokens': 4, 'total_tokens': 12},
            }
            if body.get('stream'):
                events = [
                    {'type': 'response.created', 'response': {**response, 'output': []}},
                    {'type': 'response.output_item.added', 'output_index': 0, 'item': response['output'][0]},
                    {
                        'type': 'response.output_text.delta',
                        'output_index': 0,
                        'content_index': 0,
                        'delta': 'Stage1 response',
                    },
                    {'type': 'response.output_item.done', 'output_index': 0, 'item': response['output'][0]},
                    {'type': 'response.completed', 'response': response},
                ]
                return web.Response(
                    text=''.join('data: ' + json.dumps(e) + '\n\n' for e in events), content_type='text/event-stream'
                )
            return web.json_response(response)
        if request.path == '/v1/chat/completions':
            await asyncio.sleep(0.02)  # make concurrent billing-context leakage observable
            response = {
                'id': 'chat-stage1',
                'object': 'chat.completion',
                'created': 0,
                'model': body['model'],
                'choices': [
                    {
                        'index': 0,
                        'message': {'role': 'assistant', 'content': '{"title":"Stage1 title"}'},
                        'finish_reason': 'stop',
                    }
                ],
                'usage': {'prompt_tokens': 8, 'completion_tokens': 4, 'total_tokens': 12},
            }
            tool_call = (
                any('NATIVE-IMAGE-C1' in str(m.get('content', '')) for m in body.get('messages', []))
                and not any(m.get('role') == 'tool' for m in body.get('messages', []))
                and any(t.get('function', {}).get('name') == 'generate_image' for t in body.get('tools', []))
            )
            if body.get('stream'):
                chunk = {
                    **response,
                    'object': 'chat.completion.chunk',
                    'choices': [
                        {'index': 0, 'delta': {'role': 'assistant', 'content': 'Stage1 stream'}, 'finish_reason': None}
                    ],
                }
                if tool_call:
                    chunk['choices'] = [
                        {
                            'index': 0,
                            'delta': {
                                'role': 'assistant',
                                'tool_calls': [
                                    {
                                        'index': 0,
                                        'id': 'call-native-image',
                                        'type': 'function',
                                        'function': {
                                            'name': 'generate_image',
                                            'arguments': json.dumps({'prompt': 'NATIVE-IMAGE-C1'}),
                                        },
                                    }
                                ],
                            },
                            'finish_reason': 'tool_calls',
                        }
                    ]
                return web.Response(
                    text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n', content_type='text/event-stream'
                )
            return web.json_response(response)
        return web.json_response({'error': 'unexpected gateway route'}, status=404)

    async def proxy(self, request):
        if not request.path.startswith('/_chat/'):
            return web.Response(status=404)
        uid = request.cookies.get('smoke_user', '')
        if uid not in ('1', '2', '3'):
            return web.Response(status=401)
        headers = {
            k: v
            for k, v in request.headers.items()
            if not k.lower().startswith(('x-sub2api-', 'x-forwarded-'))
            and k.lower() not in ('host', 'content-length', 'x-real-ip', 'forwarded', 'cookie')
        }
        # Preserve only the OWUI token cookie, as a real reverse proxy does during account switching.
        if request.cookies.get('token'):
            headers['Cookie'] = 'token=' + request.cookies['token']
        headers['Accept-Encoding'] = 'identity'
        headers.update(identity(uid, 'admin' if uid == '3' else 'user'))
        # Fake ownership validation: IDs 1/2 belong exclusively to corresponding user.
        if request.headers.get('X-Sub2API-Key-Id') == uid:
            headers['X-Sub2API-Key'] = 'smoke-chat-' + uid
            headers['X-Sub2API-Key-Platform'] = 'openai' if uid == '2' else 'anthropic'
        if request.headers.get('X-Sub2API-Image-Key-Id') == uid:
            headers['X-Sub2API-Image-Key'] = 'smoke-image-' + uid
        url = (
            'http://127.0.0.1:28200'
            + request.path[len('/_chat') :]
            + ('?' + request.query_string if request.query_string else '')
        )
        async with aiohttp.ClientSession(trust_env=False) as session:
            websocket = web.WebSocketResponse()
            if websocket.can_prepare(request).ok:
                headers = {
                    k: v
                    for k, v in headers.items()
                    if not k.lower().startswith('sec-websocket-') and k.lower() not in ('connection', 'upgrade')
                }
                for name in ('X-Sub2API-Key', 'X-Sub2API-Image-Key', 'X-Sub2API-Key-Platform'):
                    headers.pop(name, None)
                async with session.ws_connect(url, headers=headers) as upstream:
                    await websocket.prepare(request)

                    async def pipe(source, target):
                        async for message in source:
                            if message.type == aiohttp.WSMsgType.TEXT:
                                await target.send_str(message.data)
                            elif message.type == aiohttp.WSMsgType.BINARY:
                                await target.send_bytes(message.data)
                        await target.close()

                    tasks = [
                        asyncio.create_task(pipe(websocket, upstream)),
                        asyncio.create_task(pipe(upstream, websocket)),
                    ]
                    _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                return websocket
            async with session.request(
                request.method, url, headers=headers, data=await request.read(), allow_redirects=False
            ) as response:
                out = web.Response(body=await response.read(), status=response.status)
                for key, value in response.headers.items():
                    if key.lower() in ('content-type', 'set-cookie', 'location'):
                        out.headers.add(key, value)
                return out

    async def start(self, embed=True, overrides=None):
        if not self.runners:
            for port, handler in ((28201, self.gateway), (28202, self.proxy)):
                app = web.Application(client_max_size=30 * 1024 * 1024)
                app.router.add_route('*', '/{path:.*}', handler)
                runner = web.AppRunner(app)
                await runner.setup()
                await web.TCPSite(runner, '127.0.0.1', port).start()
                self.runners.append(runner)
        data = self.directory / ('embed' if embed else 'upstream')
        data.mkdir(exist_ok=True)
        self.network_log = data / 'network.jsonl'
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
        env.update(
            {
                'PYTHONPATH': str(BACKEND),
                'USE_SLIM_DOCKER': 'true',
                'DATA_DIR': str(data),
                'STATIC_DIR': str(data / 'static'),
                'WEBUI_SECRET_KEY': 'stage1-isolated-smoke-secret-only',
                'S2A_EMBED_MODE': '1' if embed else '0',
                'S2A_GATEWAY_URL': 'http://127.0.0.1:28201',
                'S2A_TRUSTED_PROXY_CIDRS': '127.0.0.1/32',
                'S2A_SMOKE_NETWORK_LOG': str(self.network_log),
                'OLLAMA_BASE_URL': 'http://127.0.0.1:28201',
                'OFFLINE_MODE': 'true',
                'ENABLE_VERSION_UPDATE_CHECK': 'false',
                'ENABLE_OLLAMA_API': 'false',
                'BYPASS_EMBEDDING_AND_RETRIEVAL': 'true',
                'ENABLE_BASE_MODELS_CACHE': 'false',
                'ENABLE_PERSISTENT_CONFIG': 'false',
                'ENABLE_CHANNELS': 'false',
                'ENABLE_AUTOMATIONS': 'false',
                'RAG_EMBEDDING_MODEL': '',
                'RAG_RERANKING_MODEL': '',
                'HF_HUB_OFFLINE': '1',
                'S2A_HIDE_BRANDING': '1',
            }
        )
        env.update(overrides or {})
        self.log = open(data / 'server.log', 'a')
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name('server.py'))],
            cwd=BACKEND,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        async with httpx.AsyncClient(trust_env=False) as client:
            for _ in range(200):
                if self.process.poll() is not None:
                    raise RuntimeError((data / 'server.log').read_text()[-7000:])
                try:
                    response = await client.get('http://127.0.0.1:28200/api/config', headers=identity(1))
                    if response.status_code == 200:
                        return response.json()
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)
        raise RuntimeError('Backend startup timed out: ' + str(data))

    async def stop_backend(self):
        if self.process:
            self.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.to_thread(self.process.wait, 15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
            self.process = None
            self.log.close()

    async def close(self):
        for socket in self.sockets:
            await socket.disconnect()
        await self.stop_backend()
        for runner in self.runners:
            await runner.cleanup()
        self.runners.clear()


async def run():
    harness = Harness()
    try:
        config = await harness.start()
        assert config['sub2api'] == {
            'embed': True,
            'hide_branding': True,
            'native_web_search': True,
            'image_generation': True,
        }
        assert config['name'] == ''
        assert not harness.records, 'Startup must not prefetch models'
        async with httpx.AsyncClient(base_url='http://127.0.0.1:28202/_chat', timeout=60, trust_env=False) as client:

            def h(uid, key=True, image=False):
                return {
                    'Cookie': f'smoke_user={uid}',
                    **({'X-Sub2API-Key-Id': str(uid)} if key else {}),
                    **({'X-Sub2API-Image-Key-Id': str(uid)} if image else {}),
                }

            tokens = {}
            for uid in (1, 2, 3):
                response = await client.post(
                    '/api/v1/auths/signin', headers=h(uid), json={'email': '', 'password': ''}
                )
                assert response.status_code == 200, response.text
                assert response.json()['role'] == ('admin' if uid == 3 else 'user'), response.text
                assert response.json()['name'] == display_name(uid), response.text
                assert 'Path=/_chat' in response.headers.get('set-cookie', '')
                tokens[uid] = response.json()['token']

            def auth(uid, **kwargs):
                return {**h(uid, **kwargs), 'Authorization': 'Bearer ' + tokens[uid]}

            # Request-by-request role synchronization (including demotion).
            async with httpx.AsyncClient(trust_env=False) as direct:
                for role in ('admin', 'user'):
                    response = await direct.get(
                        'http://127.0.0.1:28200/api/v1/auths/',
                        headers={**identity(1, role), 'Authorization': 'Bearer ' + tokens[1]},
                    )
                    assert response.status_code == 200 and response.json()['role'] == role, response.text
                # Missing headers / malformed header / forged browser identity all fail closed.
                response = await direct.get('http://127.0.0.1:28200/api/config')
                assert response.status_code == 401
                assert (await direct.get('http://127.0.0.1:28200/health')).status_code == 401
                assert (await direct.get('http://127.0.0.1:28200/static/favicon.png')).status_code == 200
            response = await client.get(
                '/api/v1/auths/',
                headers={**auth(1), 'X-Sub2API-User-Role': 'admin', 'X-Sub2API-Email': 'u3@sub2api.internal'},
            )
            assert response.json()['role'] == 'user'
            for path in ('/api/v1/functions/list', '/api/v1/tools/list', '/api/v1/configs/tool_servers'):
                assert (await client.get(path, headers=auth(3))).status_code == 200, path
                assert (await client.get(path, headers=auth(1))).status_code == 403, path
            # C2: only admin may write tool-server connections; disabled stub does not dial.
            tool_config = {
                'TOOL_SERVER_CONNECTIONS': [
                    {
                        'url': 'http://127.0.0.1:28201',
                        'path': '/tool-schema',
                        'auth_type': 'none',
                        'key': '',
                        'config': {'enable': False},
                        'info': {'id': 'stage1-persisted'},
                    }
                ]
            }
            for uid, status in ((1, 403), (3, 200)):
                response = await client.post('/api/v1/configs/tool_servers', headers=auth(uid), json=tool_config)
                assert response.status_code == status, response.text
            # Contract D exact read-only exceptions do not expose management or writes.
            for uid in (1, 3):
                response = await client.get('/api/v1/functions/', headers=auth(uid))
                assert response.status_code == 200 and isinstance(response.json(), list), response.text
                response = await client.get('/api/v1/groups/', headers=auth(uid))
                assert response.status_code == (200 if uid == 3 else 403), response.text
                for method, path in (('POST', '/api/v1/groups/create'), ('GET', '/api/v1/groups/sample')):
                    response = await client.request(method, path, headers=auth(uid), json={})
                    assert response.status_code == 404, response.text
            response = await client.post('/api/v1/functions/create', headers=auth(1), json={})
            assert response.status_code == 403, response.text
            assert (await client.get('/api/v1/functions/', headers=h(1))).status_code == 401

            # Account switching via either stale Bearer or HttpOnly cookie: only config falls back.
            anonymous = await client.get('/api/config', headers=h(2))
            assert anonymous.status_code == 200 and 'default_models' not in anonymous.json(), anonymous.text
            for stale_uid in (1, 3):
                for headers in (
                    {**h(2), 'Authorization': 'Bearer ' + tokens[stale_uid]},
                    {**h(2), 'Cookie': 'smoke_user=2; token=' + tokens[stale_uid]},
                ):
                    response = await client.get('/api/config', headers=headers)
                    assert response.status_code == 200 and response.json() == anonymous.json(), response.text
                    for path in ('/api/v1/auths/', '/api/v1/chats/'):
                        response = await client.get(path, headers=headers)
                        assert response.status_code == 401, (path, response.text)
                    # Trusted signin ignores the stale account token and issues the new user's session.
                    response = await client.post(
                        '/api/v1/auths/signin', headers=headers, json={'email': '', 'password': ''}
                    )
                    assert (
                        response.status_code == 200 and response.json()['email'] == 'u2@sub2api.internal'
                    ), response.text
                    assert 'Path=/_chat' in response.headers.get('set-cookie', '')
                    response = await client.get(
                        '/api/config', headers={**h(2), 'Authorization': 'Bearer ' + response.json()['token']}
                    )
                    assert response.status_code == 200 and 'default_models' in response.json(), response.text
            # In particular a stale admin token must not be demoted by the new user's role header.
            response = await client.get('/api/v1/auths/', headers=auth(3))
            assert response.json()['role'] == 'admin', response.text
            # Concurrent different-key views, same-user key changes cannot share cache.
            views = await asyncio.gather(*(client.get('/api/models', headers=auth(uid)) for uid in (1, 2)))
            for uid, response in zip((1, 2), views):
                assert response.status_code == 200, response.text
                assert {m['id'] for m in response.json()['data']} == {'common', f'only-{uid}'}, response.text
            before = len([r for r in harness.records if r['path'] == '/v1/models'])
            await client.get('/api/models', headers=auth(1))
            assert len([r for r in harness.records if r['path'] == '/v1/models']) == before

            # Supplement 3: real route must preserve gateway status and flat diagnostics.
            model_error_cases = [
                (
                    403,
                    {'code': 'INSUFFICIENT_BALANCE', 'message': 'Insufficient account balance'},
                    'INSUFFICIENT_BALANCE',
                    '账户余额不足',
                    'Insufficient account balance',
                ),
                (
                    401,
                    {
                        'error': {
                            'code': 'invalid_api_key',
                            'type': 'invalid_request_error',
                            'message': 'Invalid API key',
                        }
                    },
                    'invalid_api_key',
                    '所选 Key 不可用',
                    'Invalid API key',
                ),
                (
                    403,
                    {'code': 'API_KEY_EXPIRED', 'message': 'API key 已过期'},
                    'API_KEY_EXPIRED',
                    '所选 Key 不可用',
                    'API key 已过期',
                ),
                (
                    429,
                    {'error': {'type': 'rate_limit_error', 'message': 'Slow down'}},
                    'rate_limit_error',
                    '请求过于频繁',
                    'Slow down',
                ),
                (
                    503,
                    {'code': 'INTERNAL_ERROR', 'message': '错误😀' * 200},
                    'INTERNAL_ERROR',
                    '网关模型列表不可用',
                    ('错误😀' * 200)[:300],
                ),
                (502, '<html>Bad gateway</html>', 'GATEWAY_ERROR', '网关模型列表不可用', '<html>Bad gateway</html>'),
                (
                    302,
                    {'message': 'Redirect not followed'},
                    'GATEWAY_ERROR',
                    '网关模型列表不可用',
                    'Redirect not followed',
                ),
            ]
            for status, body, code, detail, message in model_error_cases:
                harness.model_errors['Bearer smoke-chat-1'] = (status, body)
                before = len(harness.records)
                for path in ('/api/models?refresh=true', '/api/models', '/api/v1/models'):
                    response = await client.get(path, headers=auth(1))
                    assert response.status_code == status, (path, response.status_code, response.text)
                    assert response.json() == {
                        'detail': detail,
                        's2a_gateway_error': {'status': status, 'code': code, 'message': message},
                    }, response.text
                assert len(harness.records) == before + 3, 'Failure must not be cached'
                response = await client.get('/api/models', headers=auth(2))
                assert response.status_code == 200, response.text
                assert len(harness.records) == before + 3, 'Refresh must not evict another Key'
                del harness.model_errors['Bearer smoke-chat-1']
                response = await client.get('/api/models', headers=auth(1))
                assert response.status_code == 200, response.text
                assert {m['id'] for m in response.json()['data']} == {'common', 'only-1'}
                assert len(harness.records) == before + 4, 'Recovery must retry immediately'
                response = await client.get('/api/models', headers=auth(1))
                assert response.status_code == 200 and len(harness.records) == before + 4

            async def chat(uid, stream=False):
                body = {
                    'model': f'only-{uid}',
                    'messages': [{'role': 'user', 'content': f'user-{uid}'}],
                    'stream': stream,
                    'features': {'web_search': True},
                }
                response = await client.post('/api/chat/completions', headers=auth(uid), json=body)
                assert response.status_code == 200, response.text
                return response

            await asyncio.gather(*(chat(uid) for uid in (1, 2, 1, 2)))
            await chat(1, stream=True)

            # The real socket/session path spawns detached chat and initial-title tasks.
            async def socket_connect(uid, token_uid=None, anonymous=False):
                socket = socketio.AsyncClient(reconnection=False)
                harness.sockets.append(socket)
                await socket.connect(
                    'http://127.0.0.1:28202',
                    socketio_path='/_chat/ws/socket.io',
                    transports=['websocket'],
                    auth={} if anonymous else {'token': tokens[token_uid or uid]},
                    headers={'Cookie': f'smoke_user={uid}'},
                    wait_timeout=5,
                )
                return socket

            try:
                await socket_connect(1, anonymous=True)
                raise AssertionError('Tokenless socket accepted')
            except socketio.exceptions.ConnectionError:
                pass
            try:
                await socket_connect(2, 1)
                raise AssertionError('Stale socket token accepted')
            except socketio.exceptions.ConnectionError:
                pass
            sockets = {uid: await socket_connect(uid) for uid in (1, 2)}

            async def background_chat(uid, image=False):
                mid, aid = str(uuid.uuid4()), str(uuid.uuid4())
                content = 'NATIVE-IMAGE-C1' if image else f'user-{uid} background title test'
                response = await client.post(
                    '/api/chat/completions',
                    headers=auth(uid, image=image),
                    json={
                        'model': f'only-{uid}',
                        'stream': True,
                        'messages': [{'role': 'user', 'content': content}],
                        'params': {'function_calling': 'native'},
                        'features': {'web_search': True, 'image_generation': image},
                        'session_id': sockets[uid].get_sid(),
                        'chat_id': None,
                        'id': aid,
                        'parent_id': None,
                        'user_message': {
                            'id': mid,
                            'parentId': None,
                            'childrenIds': [aid],
                            'role': 'user',
                            'content': content,
                            'models': [f'only-{uid}'],
                        },
                        'message_ids': [{'model_id': f'only-{uid}', 'message_id': aid, 'modelIdx': 0}],
                        'background_tasks': {
                            'title_generation': True,
                            'tags_generation': True,
                            'follow_up_generation': True,
                        },
                    },
                )
                assert response.status_code == 200, response.text
                chat_id = response.json()['chat_id']
                for _ in range(100):
                    response = await client.get('/api/v1/chats/' + chat_id, headers=auth(uid))
                    chat_data = response.json()
                    message = chat_data.get('chat', {}).get('history', {}).get('messages', {}).get(aid, {})
                    if message.get('done') and chat_data.get('title') not in (None, '', 'New Chat'):
                        break
                    await asyncio.sleep(0.1)
                else:
                    raise AssertionError(chat_data)
                other = await client.get('/api/v1/chats/' + chat_id, headers=auth(3 - uid))
                missing = await client.get('/api/v1/chats/' + str(uuid.uuid4()), headers=auth(3 - uid))
                assert other.status_code == missing.status_code and other.status_code in (401, 403, 404), other.text
                assert not message.get('followUps')
                return chat_id

            chat_ids = await asyncio.gather(*(background_chat(uid) for uid in (1, 2)))
            await background_chat(1, image=True)
            native_images = [
                r
                for r in harness.records
                if r['path'] == '/v1/images/generations' and (r['body'] or {}).get('prompt') == 'NATIVE-IMAGE-C1'
            ]
            assert len(native_images) == 1 and native_images[0]['key'] == 'Bearer smoke-image-1', native_images
            from open_webui.test.embed.smoke.isolation import check_isolation

            isolation_checks = await check_isolation(client, auth, tokens, harness, socket_connect, chat_ids[0])
            native_requests = [
                r for r in harness.records if (r['body'] or {}).get('stream') and (r['body'] or {}).get('tools')
            ]
            names = {
                t.get('function', t).get('name')
                for r in native_requests
                for t in r['body']['tools']
                if t['type'] == 'function'
            }
            assert {'get_current_timestamp', 'ask_user', 'search_chats', 'generate_image'} <= names, names
            assert not names.intersection(
                {
                    'list_knowledge_bases',
                    'query_knowledge_bases',
                    'search_web',
                    'fetch_url',
                    'execute_code',
                    'timer',
                    'delegate_task',
                    'create_automation',
                    'create_skill',
                }
            ), names
            # user-join cannot replace a handshake identity with another account's JWT.
            await sockets[1].emit('user-join', {'auth': {'token': tokens[2]}})
            for _ in range(50):
                if not sockets[1].connected:
                    break
                await asyncio.sleep(0.05)
            assert not sockets[1].connected
            await sockets[2].emit('heartbeat', {})
            await sockets[2].disconnect()

            for uid in (1, 2):
                response = await client.post(
                    '/api/v1/tasks/title/completions',
                    headers=auth(uid),
                    json={'model': f'only-{uid}', 'messages': [{'role': 'user', 'content': f'user-{uid}'}]},
                )
                assert response.status_code == 200, response.text
                response = await client.post(
                    '/api/v1/images/generations',
                    headers=auth(uid, image=uid == 2),
                    json={'prompt': f'user-{uid}', 'n': 1},
                )
                assert response.status_code == 200, response.text
            response = await client.post(
                '/api/v1/images/generations', headers=auth(1), json={'prompt': 'too many', 'n': 5}
            )
            assert response.status_code == 400, response.text
            for path in ('/api/models',):
                response = await client.get(path, headers=auth(1, key=False))
                assert response.status_code == 400 and response.json()['detail'] == '请选择可用的 Key', response.text
            response = await client.post(
                '/api/chat/completions',
                headers=auth(1),
                json={
                    'model': 'common',
                    'model_item': {'direct': True, 'url': 'http://127.0.0.1:28203'},
                    'messages': [],
                },
            )
            assert response.status_code == 403, response.text
            # Shared assistants are visible only when the selected Key has their base model.
            for preset, base, grants in (
                ('assistant-one', 'only-1', [{'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}]),
                ('assistant-private', 'common', []),
            ):
                response = await client.post(
                    '/api/v1/models/create',
                    headers=auth(3, key=False),
                    json={
                        'id': preset,
                        'base_model_id': base,
                        'name': preset,
                        'params': {},
                        'meta': {},
                        'access_grants': grants,
                    },
                )
                assert response.status_code == 200, response.text
            for uid in (1, 2):
                response = await client.get('/api/models', headers=auth(uid))
                ids = {m['id'] for m in response.json()['data']}
                assert ('assistant-one' in ids) == (uid == 1), ids
                assert 'assistant-private' not in ids, ids
            response = await client.post(
                '/api/chat/completions',
                headers=auth(1),
                json={
                    'model': 'assistant-one',
                    'messages': [{'role': 'user', 'content': 'assistant test'}],
                    'stream': False,
                },
            )
            assert response.status_code == 200, response.text
            # Both raw uploads and original PDF/DOCX loaders.
            for filename, content, mime, marker in (
                ('stage1.pdf', pdf(), 'application/pdf', 'PDF-STAGE1-MARKER'),
                (
                    'stage1.docx',
                    docx(),
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'DOCX-STAGE1-MARKER',
                ),
            ):
                response = await client.post(
                    '/api/v1/files/?process_in_background=false',
                    headers=auth(1),
                    files={'file': (filename, content, mime)},
                )
                assert response.status_code == 200, response.text
                file = response.json()
                response = await client.get(f'/api/v1/files/{file["id"]}', headers=auth(1))
                assert marker in response.text, response.text
                other = await client.get(f'/api/v1/files/{file["id"]}/content', headers=auth(2))
                assert other.status_code in (403, 404), other.text
                rejected = await client.post(
                    '/api/v1/retrieval/process/file',
                    headers=auth(1),
                    json={'file_id': file['id'], 'collection_name': 'forbidden-vector'},
                )
                assert rejected.status_code == 403, rejected.text
                if filename.endswith('.pdf'):
                    response = await client.post(
                        '/api/chat/completions',
                        headers=auth(1),
                        json={
                            'model': 'only-1',
                            'messages': [{'role': 'user', 'content': 'Summarize PDF'}],
                            'stream': False,
                            'files': [{'type': 'file', 'id': file['id'], 'name': filename, 'context': 'full'}],
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert marker in json.dumps(harness.records[-1]['body']), harness.records[-1]
                updated = await client.post(
                    f'/api/v1/files/{file["id"]}/data/content/update',
                    headers=auth(1),
                    json={'content': 'Updated full text'},
                )
                assert updated.status_code == 200, updated.text
                deleted = await client.delete(f'/api/v1/files/{file["id"]}', headers=auth(1))
                assert deleted.status_code == 200, deleted.text

            response = await client.post(
                '/api/v1/files/?process=false',
                headers=auth(1),
                files={'file': ('bad.exe', b'no', 'application/octet-stream')},
            )
            assert response.status_code == 400, response.text
            response = await client.post(
                '/api/v1/files/?process=false', headers=auth(1), files={'file': ('ok.png', PNG, 'image/png')}
            )
            assert response.status_code == 200, response.text
            # All hard policies exercised against the real app for normal/admin users.
            from open_webui.embed.blocklist import RULES, route_status
            import re

            for rule in RULES:
                if rule.policy not in ('removed', 'forbidden', 'admin'):
                    continue
                path = re.sub(r'\{[^}]+\}', 'sample', rule.prefix)
                method = rule.methods[0] if rule.methods else 'POST'
                for uid in (1, 3):
                    expected = route_status(path, method, 'admin' if uid == 3 else 'user')
                    if expected is None:
                        continue
                    response = await client.request(method, path, headers=auth(uid), json={})
                    assert response.status_code == expected, (path, uid, expected, response.status_code, response.text)
            # Returned gateway image URLs and redirect/external URLs.
            for url, expected in (
                ('http://127.0.0.1:28201/image.png', 200),
                ('http://127.0.0.1:28203/external.png', 400),
                ('http://127.0.0.1:28201/redirect.png', 400),
            ):
                harness.response_image_url = url
                response = await client.post(
                    '/api/v1/images/generations', headers=auth(1), json={'prompt': 'url test'}
                )
                assert response.status_code == expected, response.text
            harness.response_image_url = None
            response = await client.post(
                '/api/v1/images/edit',
                headers=auth(2, image=True),
                json={'prompt': 'edit', 'image': 'data:image/png;base64,' + base64.b64encode(PNG).decode(), 'n': 1},
            )
            assert response.status_code == 200, response.text
        for record in harness.records:
            assert record['cookie'] is None
            assert record['key'] in (
                'Bearer smoke-chat-1',
                'Bearer smoke-chat-2',
                'Bearer smoke-image-2',
                'Bearer smoke-image-1',
                'Bearer smoke-chat-3',
            ), record
            body = record['body'] or {}
            if body.get('model') in ('only-1', 'only-2'):
                uid = body['model'][-1]
                assert record['key'] == 'Bearer smoke-chat-' + uid, record
                assert record['xff'] == '203.0.113.' + uid, record
                assert record['path'] == ('/v1/responses' if uid == '2' else '/v1/chat/completions'), record
        searches = [
            r
            for r in harness.records
            if any(t.get('type') == 'web_search' for t in (r['body'] or {}).get('tools', []))
        ]
        assert len(searches) >= 4
        network = [json.loads(line) for line in harness.network_log.read_text().splitlines()]
        assert all(r['allowed'] and r['port'] == 28201 for r in network), network
        for socket in harness.sockets:
            await socket.disconnect()
        await harness.stop_backend()
        await harness.start(overrides={'USER_PERMISSIONS_CHAT_FILE_UPLOAD': 'false'})
        async with httpx.AsyncClient(base_url='http://127.0.0.1:28202/_chat', trust_env=False) as client:
            response = await client.post(
                '/api/v1/files/?process=false',
                headers=auth(1),
                files={'file': ('forbidden.txt', b'no permission', 'text/plain')},
            )
            assert response.status_code == 403, response.text
            response = await client.get('/api/v1/images/models', headers=auth(1, key=False))
            assert response.status_code == 200 and len(response.json()) == 4, response.text
            response = await client.get('/api/v1/configs/tool_servers', headers=auth(3, key=False))
            assert response.status_code == 200, response.text
            assert response.json()['TOOL_SERVER_CONNECTIONS'][0]['info']['id'] == 'stage1-persisted', response.text
        await harness.stop_backend()
        upstream = await harness.start(embed=False)
        assert 'sub2api' not in upstream
        assert upstream['name'] == 'Open WebUI', upstream.get('name')
        result = {
            'status': 'PASS',
            'gateway_requests': len(harness.records),
            'native_search_requests': len(searches),
            'native_generate_image_with_image_key': 'PASS',
            'admin_isolation_checks': isolation_checks,
            'network_destinations': sorted({f"{r['host']}:{r['port']}" for r in network}),
            'upstream_mode_startup': 'PASS',
            'admin_tool_config_persistence': 'PASS',
            'anonymous_static_health_probe': 'PASS',
            'percent_encoded_name_http_and_websocket': 'PASS',
            'config_account_switch_bearer_and_cookie': 'PASS',
            'readonly_function_and_admin_group_lists': 'PASS',
            'tokenless_socket_rejected': 'PASS',
            'model_error_status_body_cache_recovery': 'PASS',
            'model_error_cases': len(model_error_cases),
            'artifacts': str(harness.directory),
        }
        (harness.directory / 'gateway.json').write_text(json.dumps(harness.records, ensure_ascii=False, indent=2))
        (harness.directory / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    except Exception:
        print('Smoke artifacts:', harness.directory, file=sys.stderr)
        raise
    finally:
        await harness.close()


if __name__ == '__main__':
    asyncio.run(run())
