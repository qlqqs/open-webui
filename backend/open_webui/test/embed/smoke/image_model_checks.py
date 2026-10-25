"""Exercise real generation/edit/tool callers without paid requests or file writes."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from open_webui.embed import gateway, images, models
from open_webui.routers import images as routes
from open_webui.tools import builtin
from open_webui.test.embed.smoke.run import PNG


async def run():
    token = gateway.SUB2API_KEY.set('route-model-test-key')
    try:
        for editing in (False, True):
            preferred = 'configured-edit' if editing else 'configured-generation'
            call = routes.image_edits if editing else routes.image_generations
            for available, expected in (
                (['configured-generation', 'configured-edit', 'gpt-image-2'], preferred),
                (['gpt-image-2.5-flare', 'gpt-image-2'], 'gpt-image-2'),
                (['gpt-image-2.5-sunburst', 'gpt-image-2.5-flare', 'flux'], 'gpt-image-2.5-flare'),
                (['seedream-4', 'dall-e-3'], 'dall-e-3'),
                (['gpt-6-sol'], None),
                (models.GatewayModelError(403, 'INSUFFICIENT_BALANCE', 'No balance'), None),
            ):
                request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS={})))
                config = images.configure(SimpleNamespace(
                    IMAGE_GENERATION_MODEL='configured-generation', IMAGE_EDIT_MODEL='configured-edit',
                    IMAGE_SIZE='', IMAGE_EDIT_SIZE='',
                ))
                form = (
                    routes.EditImageForm(
                        prompt='edit selection', image='data:image/png;base64,' + base64.b64encode(PNG).decode(),
                        model='unavailable-user-override',
                    )
                    if editing else routes.CreateImageForm(prompt='generation selection')
                )
                fetch = (
                    AsyncMock(side_effect=available) if isinstance(available, Exception)
                    else AsyncMock(return_value={'data': [{'id': name} for name in available]})
                )
                response = MagicMock(status=200)
                response.json = AsyncMock(return_value={'data': [{'b64_json': base64.b64encode(PNG).decode()}]})
                session = MagicMock()
                session.post.return_value.__aenter__.return_value = response
                with (
                    patch.object(models, 'fetch_models', fetch),
                    patch.object(routes, 'get_image_config', AsyncMock(return_value=config)),
                    patch.object(routes, 'get_image_model', AsyncMock(return_value='configured-generation')),
                    patch.object(routes, 'get_session', AsyncMock(return_value=session)) as get_session,
                    patch.object(routes, 'get_image_data', AsyncMock(return_value=(PNG, 'image/png'))) as load,
                    patch.object(routes, 'upload_image', AsyncMock(return_value=(None, {'id': 'selected'}))) as upload,
                ):
                    if expected:
                        assert await call(request, form, user=None) == [{'id': 'selected'}]
                        assert upload.await_args.args[3]['model'] == expected
                        if expected.startswith('gpt-image'):
                            assert 'response_format' not in upload.await_args.args[3]
                        session.post.assert_called_once()
                    else:
                        try:
                            await call(request, form, user=None)
                            raise AssertionError('unavailable image model accepted')
                        except HTTPException as exc:
                            if isinstance(available, Exception):
                                assert exc is available  # No HTTPException/error-message rewrapping.
                            else:
                                assert exc.status_code == 400
                                assert exc.detail == '当前生图 Key 所在分组没有可用的生图模型'
                        # Built-in tools use the same guard, even without chat/model-list prefetch.
                        if editing:
                            result = await builtin.edit_image('tool edit', [form.image], __request__=request)
                        else:
                            result = await builtin.generate_image('tool generation', __request__=request)
                        assert ('账户余额不足' if isinstance(available, Exception) else '没有可用的生图模型') in json.loads(result)['error']
                        get_session.assert_not_awaited()
                        session.post.assert_not_called()
                        load.assert_not_awaited()
                        upload.assert_not_awaited()
    finally:
        gateway.SUB2API_KEY.reset(token)
