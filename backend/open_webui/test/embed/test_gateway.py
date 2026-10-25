import asyncio
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from open_webui.embed import gateway, images, models, embeddings
from open_webui.embed.settings import Settings
from open_webui.embed.gateway import SUB2API_KEY, SUB2API_KEY_PLATFORM, SUB2API_CLIENT_IP

SETTINGS = Settings.from_env({'S2A_EMBED_MODE': '1', 'S2A_GATEWAY_URL': 'http://127.0.0.1:28201'})


class Response:
    status = 200
    headers = {'Content-Type': 'image/png'}

    def __init__(self, body=None):
        self.body = body or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return self.body

    async def read(self):
        return b'png'

    def raise_for_status(self):
        pass


class Session:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert kwargs['allow_redirects'] is False
        key = kwargs['headers']['Authorization'].split()[-1]
        # Gateway fields must not inject direct connections or pipe metadata.
        return Response(
            {'data': [{'id': key + '-model', 'urlIdx': 99, 'direct': True, 'pipe': {}, 'url': 'http://bad'}]}
        )

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert kwargs['allow_redirects'] is False
        return Response({'data': [{'embedding': [1, 2]}]})


@pytest.fixture
def fake_gateway(monkeypatch):
    monkeypatch.setattr(gateway, 'settings', SETTINGS)
    monkeypatch.setattr(images, 'settings', SETTINGS)
    monkeypatch.setattr(models.aiohttp, 'ClientSession', Session)
    Session.calls = []


@pytest.mark.asyncio
async def test_per_key_hash_ttl_and_metadata_union(fake_gateway, monkeypatch):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={}, MODELS={}, BASE_MODELS=[])))
    now = [10.0]
    monkeypatch.setattr(models.time, 'monotonic', lambda: now[0])

    async def get(key):
        token = SUB2API_KEY.set(key)
        try:
            return await models.gateway_models(request)
        finally:
            SUB2API_KEY.reset(token)

    first, second = await asyncio.gather(get('user-a'), get('user-b'))
    assert first['data'][0]['id'] == 'user-a-model' and second['data'][0]['id'] == 'user-b-model'
    assert set(request.app.state.OPENAI_MODELS) == {'user-a-model', 'user-b-model'}
    assert request.app.state.BASE_MODELS == []
    assert not any(m.get('direct') or 'pipe' in m for m in request.app.state.OPENAI_MODELS.values())
    assert all(m['urlIdx'] == 0 for m in request.app.state.OPENAI_MODELS.values())
    first['data'][0]['name'] = 'mutable caller view'
    assert (await get('user-a'))['data'][0]['name'] == 'user-a-model'
    assert len(Session.calls) == 2
    assert set(request.app.state.SUB2API_MODEL_CACHE) == {
        hashlib.sha256(k.encode()).hexdigest() for k in ('user-a', 'user-b')
    }
    now[0] = 71
    await get('user-a')
    assert len(Session.calls) == 3
    with pytest.raises(HTTPException) as error:
        await models.gateway_models(request)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_embedding_uses_runtime_context_not_stored_key(fake_gateway):
    for key in ('user-a', 'user-b'):
        token = SUB2API_KEY.set(key)
        ip = SUB2API_CLIENT_IP.set('203.0.113.7')
        try:
            assert await embeddings.async_embeddings('embed-model', ['hello']) == [[1, 2]]
        finally:
            SUB2API_KEY.reset(token)
            SUB2API_CLIENT_IP.reset(ip)
        url, options = Session.calls[-1]
        assert url == SETTINGS.gateway_url + '/v1/embeddings'
        assert options['headers']['Authorization'] == 'Bearer ' + key
        assert options['headers']['X-Forwarded-For'] == '203.0.113.7'


@pytest.mark.asyncio
async def test_images_external_redirects_and_engine_config(fake_gateway, monkeypatch):
    config = images.configure(SimpleNamespace(IMAGE_GENERATION_ENGINE='comfyui', IMAGE_EDIT_ENGINE='gemini'))
    assert config.IMAGE_GENERATION_ENGINE == config.IMAGE_EDIT_ENGINE == 'openai'
    assert config.IMAGES_OPENAI_API_BASE_URL == SETTINGS.gateway_url + '/v1'
    for url in (
        'https://external.invalid/image.png',
        'http://127.0.0.1:28202/image.png',
        'http://127.0.0.1:28201@bad/image.png',
    ):
        with pytest.raises(HTTPException):
            await images.gateway_image(url)
        with pytest.raises(HTTPException):
            await images.edit_source(url, None)
    assert not Session.calls
    token = SUB2API_KEY.set('image-key')
    try:
        for n in (0, -1, 5):
            with pytest.raises(HTTPException):
                images.validate_request(SimpleNamespace(n=n))
        images.validate_request(SimpleNamespace(n=4))
        assert (await images.gateway_image(SETTINGS.gateway_url + '/image.png'))[0] == b'png'
        monkeypatch.setattr(Response, 'status', 302)
        with pytest.raises(HTTPException):
            await images.gateway_image(SETTINGS.gateway_url + '/redirect.png')
    finally:
        SUB2API_KEY.reset(token)
