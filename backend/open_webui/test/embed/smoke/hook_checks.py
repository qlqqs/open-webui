"""Check real upstream hook functions in an isolated slim process/database."""

import asyncio
from dataclasses import replace
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from open_webui.test.embed.smoke.server import audit

sys.addaudithook(audit)

from fastapi import HTTPException
from starlette.requests import Request
import importlib

main = importlib.import_module('open_webui.main')
from open_webui.embed import gateway
from open_webui.embed import settings as settings_module
from open_webui.embed import embeddings
from open_webui.models.config import Config
from open_webui.routers.openai import get_openai_connection
from open_webui.retrieval import utils as retrieval_utils
from open_webui.retrieval.vector.factory import get_vector_db_client
from open_webui.socket import main as sockets
from open_webui.utils.headers import get_headers_and_cookies
from open_webui.utils import session_pool
from open_webui.utils.tools import get_builtin_tools
from open_webui.test.embed.smoke.run import identity


async def run():
    request = Request(
        {'type': 'http', 'method': 'POST', 'path': '/', 'headers': [(b'cookie', b'private=secret')], 'app': main.app}
    )
    token = gateway.SUB2API_KEY.set('runtime-user-key')
    platform = gateway.SUB2API_KEY_PLATFORM.set('openai')
    ip = gateway.SUB2API_CLIENT_IP.set('203.0.113.19')
    try:
        connection = await get_openai_connection(999)
        assert connection == ('http://127.0.0.1:28201/v1', 'runtime-user-key', {'api_type': 'responses'})
        headers, cookies = await get_headers_and_cookies(
            request,
            connection[0],
            'stored-secret',
            {
                'azure': True,
                'auth_type': 'system_oauth',
                'forward_cookies': True,
                'headers': {'Authorization': 'Bearer evil', 'X-Forwarded-For': 'evil'},
            },
        )
        assert (
            headers
            == {
                'Authorization': 'Bearer runtime-user-key',
                'Content-Type': 'application/json',
                'X-Forwarded-For': '203.0.113.19',
            }
            and cookies == {}
        )
        try:
            await get_headers_and_cookies(request, 'http://127.0.0.1:28203/v1')
            raise AssertionError('external origin accepted')
        except HTTPException as exc:
            assert exc.status_code == 400
        # Every embedding engine's old direct helper resolves a call-time context.
        with patch.object(embeddings, 'async_embeddings', AsyncMock(return_value=[[1]])) as helper:
            for name in (
                'agenerate_openai_batch_embeddings',
                'agenerate_azure_openai_batch_embeddings',
                'agenerate_ollama_batch_embeddings',
            ):
                assert await getattr(retrieval_utils, name)('m', ['text'], 'http://127.0.0.1:28203', 'stored') == [[1]]
            assert helper.await_count == 3
        with patch.object(embeddings, 'sync_embeddings', return_value=[[1]]) as helper:
            for name in (
                'generate_openai_batch_embeddings',
                'generate_azure_openai_batch_embeddings',
                'generate_ollama_batch_embeddings',
            ):
                assert getattr(retrieval_utils, name)('m', ['text'], 'http://127.0.0.1:28203', 'stored') == [[1]]
            assert helper.call_count == 3
    finally:
        gateway.SUB2API_KEY.reset(token)
        gateway.SUB2API_KEY_PLATFORM.reset(platform)
        gateway.SUB2API_CLIENT_IP.reset(ip)
    # Contract D: tokenless socket namespace connections stay rejected before user lookup.
    with (
        patch.object(sockets, 'get_verified_user_by_token', AsyncMock()) as lookup,
        patch.object(sockets.sio, 'save_session', AsyncMock()) as save,
    ):
        for auth in (None, {}, {'token': ''}, {'other': 'no token'}):
            assert await sockets.connect('anonymous-sid', {}, auth) is False
        lookup.assert_not_awaited()
        save.assert_not_awaited()
    # Periodic authentication and heartbeat share this exact callback.
    user = SimpleNamespace(email='u1@sub2api.internal')
    session = {'user': {'id': 'one'}, 'token': 'saved-jwt'}
    environ = lambda uid: {
        'asgi.scope': {'headers': [(k.lower().encode(), v.encode()) for k, v in identity(uid).items()]}
    }
    with (
        patch.object(sockets, 'get_verified_user_by_token', AsyncMock(return_value=user)),
        patch.object(sockets.sio, 'get_session', AsyncMock(return_value=session)),
        patch.object(sockets.sio, 'get_environ', return_value=environ(1)) as get_env,
        patch.object(sockets.sio, 'disconnect', AsyncMock()) as disconnect,
    ):
        assert await sockets.get_socket_session_user('test-sid') == {'id': 'one'}
        get_env.return_value = environ(2)
        sockets.LOCAL_AUTHENTICATED_SIDS.add('test-sid')
        assert await sockets.get_socket_session_user('test-sid') is None
        assert 'test-sid' not in sockets.LOCAL_AUTHENTICATED_SIDS
        disconnect.assert_awaited_once_with('test-sid')
        get_env.return_value = {}
        assert await sockets.get_socket_session_user('test-sid') is None
    # A note-chat or admin voice override cannot bypass the deployment whitelist.
    with patch.object(
        settings_module, 'settings', replace(settings_module.settings, builtin_tool_categories=frozenset({'time'}))
    ):
        tools = await get_builtin_tools(
            request,
            {'__user__': {'id': 'one', 'role': 'admin'}, '__metadata__': {}},
            features={'voice': True, 'web_search': True, 'image_generation': True},
            is_note_chat=True,
        )
        assert set(tools) == {'get_current_timestamp', 'calculate_timestamp'}, tools.keys()
    try:
        get_vector_db_client()
        raise AssertionError('vector storage initialized')
    except HTTPException as exc:
        assert exc.status_code == 403
    pool = await session_pool.get_session()
    import aiohttp

    assert isinstance(pool.cookie_jar, aiohttp.DummyCookieJar)
    await session_pool.close_session()
    # Tool servers are the only persisted config exception; model credentials never persist.
    assert Config.persistent_enabled_for('tool_server.connections')
    assert not Config.persistent_enabled_for('openai.api_keys')
    await Config.upsert({'tool_server.connections': [{'url': 'http://127.0.0.1:28201', 'config': {'enable': False}}]})
    assert (await Config.get('tool_server.connections'))[0]['url'] == 'http://127.0.0.1:28201'
    from open_webui.test.embed.smoke.isolation_checks import run as isolation_checks

    await isolation_checks()
    # Non-embedded OpenAI responses must retain upstream's URL-first behavior.
    from open_webui.routers import images as image_routes
    from open_webui.embed import images as embed_images
    from open_webui.test.embed.smoke.run import PNG
    import base64

    config = embed_images.configure(
        SimpleNamespace(
            IMAGE_GENERATION_MODEL='dall-e-3', IMAGE_EDIT_MODEL='dall-e-2', IMAGE_SIZE='', IMAGE_EDIT_SIZE='',
        )
    )
    response = MagicMock()
    response.json = AsyncMock(
        return_value={
            'data': [{'url': 'https://cdn.example.com/a.png', 'b64_json': base64.b64encode(PNG).decode()}],
        }
    )
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    with (
        patch.object(image_routes, 'embed_settings', replace(image_routes.embed_settings, enabled=False)),
        patch.object(image_routes, 'get_image_config', AsyncMock(return_value=config)),
        patch.object(image_routes, 'get_image_model', AsyncMock(return_value='dall-e-3')),
        patch.object(image_routes, 'get_session', AsyncMock(return_value=session)),
        patch.object(image_routes, 'get_image_data', AsyncMock(return_value=(PNG, 'image/png'))) as load,
        patch.object(image_routes, 'upload_image', AsyncMock(return_value=(None, {'id': 'test'}))),
        patch.object(embed_images, 'raise_for_status', AsyncMock()) as embed_status,
    ):
        for call, form in (
            (image_routes.image_generations, image_routes.CreateImageForm(prompt='upstream generation')),
            (
                image_routes.image_edits,
                image_routes.EditImageForm(
                    prompt='upstream edit', image='data:image/png;base64,' + base64.b64encode(PNG).decode(),
                ),
            ),
        ):
            assert await call(request, form, user=SimpleNamespace(id='one', role='user')) == [{'id': 'test'}]
            load.assert_awaited_once_with('https://cdn.example.com/a.png', None)
            load.reset_mock()
        assert response.raise_for_status.call_count == 2
        embed_status.assert_not_awaited()
    from open_webui.test.embed.smoke.image_model_checks import run as image_model_checks

    await image_model_checks()
    print('HOOK_CHECKS_PASS')


asyncio.run(run())
