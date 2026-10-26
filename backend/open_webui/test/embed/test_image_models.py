"""Chat visibility and image selection share complete, per-Key gateway metadata."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from open_webui.embed import gateway, images, models
from open_webui.embed.settings import DEFAULT_HIDDEN_CHAT_MODELS, Settings

ENV = {'S2A_EMBED_MODE': '1', 'S2A_GATEWAY_URL': 'http://127.0.0.1:28201'}
DEPLOYMENT_MODELS = [
    'codex-auto-review', 'gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra',
    'gpt-6-astra', 'gpt-6-luna', 'gpt-6-sol', 'gpt-6.1-sol',
    'gpt-image-2', 'gpt-image-2.5-flare', 'gpt-image-2.5-sunburst', 'gpt-reserve',
]


def items(names):
    return [{'id': name} for name in names]


def test_default_chat_filter(monkeypatch):
    monkeypatch.setattr(models, 'settings', Settings.from_env(ENV))
    source = items(DEPLOYMENT_MODELS)
    assert models.visible_chat_models(source) == items(DEPLOYMENT_MODELS[1:8])
    assert len(source) == 12  # Seven chat models, two internal models, three image models.


@pytest.mark.parametrize('name', [
    'CODEX-AUTO-REVIEW-v2', 'GPT-RESERVE-1', 'GPT-IMAGE-2', 'vendor/dall-e-3', 'DALLE-2',
    'imagen-4', 'GROK-2-IMAGE', 'grok-imagine-image', 'Seedream-4', 'FLUX.1-dev',
])
def test_default_image_and_internal_families(monkeypatch, name):
    monkeypatch.setattr(models, 'settings', Settings.from_env(ENV))
    assert models.visible_chat_models(items([name])) == []


@pytest.mark.parametrize('pattern,expected', [
    ('^gpt-5|^gpt-6', [DEPLOYMENT_MODELS[0], *DEPLOYMENT_MODELS[8:]]),
    ('', DEPLOYMENT_MODELS),
])
def test_chat_filter_override_and_empty(monkeypatch, pattern, expected):
    monkeypatch.setattr(models, 'settings', Settings.from_env({**ENV, 'S2A_HIDDEN_CHAT_MODELS': pattern}))
    assert models.visible_chat_models(items(DEPLOYMENT_MODELS)) == items(expected)


def test_invalid_regex_and_disabled_mode(monkeypatch):
    with pytest.raises(ValueError, match='S2A_HIDDEN_CHAT_MODELS'):
        Settings.from_env({**ENV, 'S2A_HIDDEN_CHAT_MODELS': '['})
    monkeypatch.setattr(models, 'settings', Settings.from_env({'S2A_HIDDEN_CHAT_MODELS': '['}))
    assert models.visible_chat_models(items(DEPLOYMENT_MODELS)) == items(DEPLOYMENT_MODELS)


@pytest.fixture
def stub(monkeypatch):
    settings = Settings.from_env(ENV)
    for module in (gateway, models, images):
        monkeypatch.setattr(module, 'settings', settings)
    state = SimpleNamespace(OPENAI_MODELS={})
    stub = SimpleNamespace(
        request=SimpleNamespace(app=SimpleNamespace(state=state)),
        bodies={}, errors={}, calls=[], now=0.0,
    )
    monkeypatch.setattr(models.time, 'monotonic', lambda: stub.now)

    class Response:
        def __init__(self, key):
            self.status, self.body = stub.errors.get(key, (200, {'data': items(stub.bodies.get(key, []))}))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return self.body

        async def text(self, **kwargs):
            return json.dumps(self.body)

    class Session:
        def __init__(self, **kwargs):
            assert kwargs['timeout'].total == 15

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, url, **kwargs):
            assert url == ENV['S2A_GATEWAY_URL'] + '/v1/models'
            assert kwargs['allow_redirects'] is False
            key = kwargs['headers']['Authorization'].removeprefix('Bearer ')
            stub.calls.append(key)
            return Response(key)

        def post(self, *args, **kwargs):
            pytest.fail('Model selection must never make a billable request')

    monkeypatch.setattr(models.aiohttp, 'ClientSession', Session)
    token = gateway.SUB2API_KEY.set('chat-key')
    try:
        yield stub
    finally:
        gateway.SUB2API_KEY.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize('configured,available,expected', [
    ('gpt-image-1', ['gpt-image-2', 'gpt-image-1'], 'gpt-image-1'),
    ('custom-image', ['custom-image', 'gpt-image-2'], 'custom-image'),
    ('missing', DEPLOYMENT_MODELS, 'gpt-image-2'),
    ('missing', ['gpt-image-2.5-sunburst', 'flux', 'gpt-image-2.5-flare'], 'gpt-image-2.5-flare'),
    ('missing', ['seedream-4', 'flux.1', 'dall-e-3'], 'dall-e-3'),
    ('missing', ['imagen-4'], 'imagen-4'),
    ('missing', ['GROK-2-IMAGE'], 'GROK-2-IMAGE'),
    ('missing', ['GPT-IMAGE-2.5', 'GPT-IMAGE-2'], 'GPT-IMAGE-2'),
    ('', ['gpt-image-2'], 'gpt-image-2'),
])
async def test_model_selection(stub, configured, available, expected):
    stub.bodies['chat-key'] = available
    assert await images.resolve_model(stub.request, configured) == expected
    assert stub.calls == ['chat-key']


@pytest.mark.asyncio
@pytest.mark.parametrize('available', [[], ['gpt-6-sol', 'codex-auto-review', 'gpt-reserve']])
async def test_no_image_models(stub, available):
    stub.bodies['chat-key'] = available
    with pytest.raises(HTTPException) as caught:
        await images.resolve_model(stub.request, 'gpt-image-2')
    assert caught.value.status_code == 400
    assert caught.value.detail == '当前生图 Key 所在分组没有可用的生图模型'
    assert stub.calls == ['chat-key']


@pytest.mark.asyncio
async def test_image_key_cache_isolation_fallback_and_ttl(stub):
    stub.bodies = {'chat-key': ['gpt-6-sol', 'gpt-image-1'], 'image-key': ['gpt-image-2']}
    await models.gateway_models(stub.request)
    # Missing image Key reuses the chat Key's cached full list, even when hidden in chat UI.
    assert models.visible_chat_models((await models.gateway_models(stub.request))['data']) == [
        next(m for m in stub.request.app.state.OPENAI_MODELS.values() if m['id'] == 'gpt-6-sol')
    ]
    assert await images.resolve_model(stub.request, 'missing') == 'gpt-image-1'
    assert stub.calls == ['chat-key']
    image_token = gateway.SUB2API_IMAGE_KEY.set('image-key')
    try:
        assert await images.resolve_model(stub.request, 'gpt-image-1') == 'gpt-image-2'
        stub.now = 59
        assert await images.resolve_model(stub.request, 'missing') == 'gpt-image-2'
        assert stub.calls == ['chat-key', 'image-key']
        # Image-only requests need no chat key, and do not mutate its ContextVar.
        chat_token = gateway.SUB2API_KEY.set('')
        try:
            stub.now = 60
            assert await images.resolve_model(stub.request, 'missing') == 'gpt-image-2'
        finally:
            gateway.SUB2API_KEY.reset(chat_token)
        assert stub.calls == ['chat-key', 'image-key', 'image-key']
        assert gateway.SUB2API_KEY.get() == 'chat-key'
    finally:
        gateway.SUB2API_IMAGE_KEY.reset(image_token)
    assert set(stub.request.app.state.SUB2API_MODEL_CACHE) == {
        hashlib.sha256(key.encode()).hexdigest() for key in ('chat-key', 'image-key')
    }


@pytest.mark.asyncio
async def test_image_list_failure_invalidates_only_image_key_and_recovers(stub):
    stub.bodies = {'chat-key': ['gpt-6-sol'], 'image-key': ['gpt-image-2']}
    await models.gateway_models(stub.request)
    image_token = gateway.SUB2API_IMAGE_KEY.set('image-key')
    try:
        await images.resolve_model(stub.request, 'missing')
        stub.now = 60
        stub.errors['image-key'] = (403, {'code': 'INSUFFICIENT_BALANCE', 'message': 'No balance'})
        for _ in range(2):
            with pytest.raises(models.GatewayModelError) as caught:
                await images.resolve_model(stub.request, 'missing')
            assert caught.value.status_code == 403 and caught.value.detail == '账户余额不足'
            assert caught.value.gateway_error == {
                'status': 403, 'code': 'INSUFFICIENT_BALANCE', 'message': 'No balance',
            }
            assert set(stub.request.app.state.SUB2API_MODEL_CACHE) == {hashlib.sha256(b'chat-key').hexdigest()}
        del stub.errors['image-key']
        assert await images.resolve_model(stub.request, 'missing') == 'gpt-image-2'
    finally:
        gateway.SUB2API_IMAGE_KEY.reset(image_token)
    assert stub.calls == ['chat-key', 'image-key', 'image-key', 'image-key', 'image-key']


def test_docker_defaults_match_settings():
    from pathlib import Path

    dockerfile = Path(__file__).resolve().parents[4] / 'docker/sub2api-embed.Dockerfile'
    source = dockerfile.read_text()
    assert f'S2A_HIDDEN_CHAT_MODELS="{DEFAULT_HIDDEN_CHAT_MODELS}"' in source
    assert 'IMAGE_GENERATION_MODEL="gpt-image-2"' in source
    assert 'IMAGE_EDIT_MODEL="gpt-image-2"' in source


@pytest.mark.asyncio
async def test_signup_image_model_is_exact_and_never_falls_back(stub):
    user = SimpleNamespace(settings=SimpleNamespace(ui={
        'sub2api_defaults': {'image_model': 'gpt-image-2.5-sunburst'}
    }))
    stub.bodies['chat-key'] = ['gpt-image-2', 'gpt-image-2.5-sunburst']
    assert await images.resolve_model(stub.request, 'gpt-image-2', user) == 'gpt-image-2.5-sunburst'
    stub.request.app.state.SUB2API_MODEL_CACHE.clear()
    stub.bodies['chat-key'] = ['gpt-image-2']
    with pytest.raises(HTTPException) as caught:
        await images.resolve_model(stub.request, 'gpt-image-2', user)
    assert caught.value.status_code == 400
    assert caught.value.detail == '默认模型不可用，请选择其他模型'
