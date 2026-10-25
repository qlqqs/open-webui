"""Image gateway errors keep useful diagnostics without changing the HTTP fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from open_webui.embed.images import raise_for_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'body,expected',
    [
        ({'error': {'message': 'Image model does not exist'}}, 'Image model does not exist'),
        ({'error': {'message': '错' * 400}}, '错' * 300),
        *[
            (body, 'Not Found')
            for body in (
                None,
                [],
                {},
                {'error': None},
                {'error': 'bad'},
                {'error': {'message': []}},
                {'error': {'message': ''}},
                {'error': {'message': '  '}},
                ValueError('not JSON'),
                aiohttp.ClientPayloadError('incomplete body'),
            )
        ],
    ],
)
async def test_image_error_message_and_fallback(body, expected):
    error = aiohttp.ClientResponseError(None, (), status=404, message='Not Found')
    response = SimpleNamespace(
        status=404,
        json=AsyncMock(side_effect=body) if isinstance(body, Exception) else AsyncMock(return_value=body),
        raise_for_status=Mock(side_effect=error),
    )
    with pytest.raises(aiohttp.ClientResponseError) as caught:
        await raise_for_status(response)
    assert caught.value is error
    assert error.status == 404 and error.message == expected
    response.json.assert_awaited_once_with(content_type=None)
    response.raise_for_status.assert_called_once_with()


@pytest.mark.asyncio
async def test_success_does_not_consume_body():
    response = SimpleNamespace(status=200, json=AsyncMock(), raise_for_status=Mock())
    await raise_for_status(response)
    response.json.assert_not_awaited()
    response.raise_for_status.assert_called_once_with()
