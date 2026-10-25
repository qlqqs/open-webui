"""Image-only gateway policy; shared by route and built-in tool callers."""

import base64
import re
import aiohttp
from fastapi import HTTPException
from .settings import IMAGE_MODEL_PATTERN, settings
from .models import gateway_models
from .gateway import current_key, headers, require_gateway_url, SUB2API_IMAGE_KEY, SUB2API_KEY


def configure(config):
    config.IMAGE_GENERATION_ENGINE = config.IMAGE_EDIT_ENGINE = 'openai'
    config.IMAGES_OPENAI_API_BASE_URL = config.IMAGES_EDIT_OPENAI_API_BASE_URL = settings.gateway_url + '/v1'
    config.IMAGES_OPENAI_API_KEY = config.IMAGES_EDIT_OPENAI_API_KEY = SUB2API_IMAGE_KEY.get() or SUB2API_KEY.get()
    config.IMAGES_OPENAI_API_VERSION = config.IMAGES_EDIT_OPENAI_API_VERSION = ''
    config.IMAGES_OPENAI_API_PARAMS = {}
    return config


def validate_request(form):
    current_key(image=True)
    if not 1 <= (form.n if form.n is not None else 1) <= settings.image_max_n:
        raise HTTPException(400, f'生图数量必须在 1–{settings.image_max_n} 之间')


async def resolve_model(request, configured):
    """Use the image Key's full cached list, independent of chat-list visibility."""
    available = {model['id'] for model in (await gateway_models(request, image=True))['data']}
    if configured in available:
        return configured
    candidates = [name for name in available if re.search(IMAGE_MODEL_PATTERN, name, re.IGNORECASE)]
    if not candidates:
        raise HTTPException(400, '当前生图 Key 所在分组没有可用的生图模型')
    # Exact gpt-image-2 first; then gpt-image variants; then other image families.
    return min(candidates, key=lambda name: (
        name.lower() != 'gpt-image-2',
        not name.lower().startswith('gpt-image'),
        name.lower(),
        name,
    ))


async def raise_for_status(response):
    """Preserve the gateway's image error message, with the original HTTP fallback."""
    message = None
    if response.status >= 400:
        # Read before raise_for_status(), which may release the response.
        try:
            body = await response.json(content_type=None)
        except (ValueError, aiohttp.ClientError):
            body = None
        detail = body.get('error') if isinstance(body, dict) else None
        message = detail.get('message') if isinstance(detail, dict) else None
    try:
        response.raise_for_status()
    except aiohttp.ClientResponseError as error:
        if isinstance(message, str) and message.strip():
            error.message = message[:300]
        raise


async def gateway_image(url):
    require_gateway_url(url)
    async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=60)) as session:
        async with session.get(url, headers=headers(image=True), allow_redirects=False) as response:
            if response.status != 200 or not response.headers.get('Content-Type', '').startswith('image/'):
                raise HTTPException(400, '网关未返回图片，或返回了不允许的重定向')
            return await response.read(), response.headers['Content-Type']


async def edit_source(data, user):
    if data.startswith('data:'):
        return data
    if data.startswith(('http:', 'https:')):
        image, content_type = await gateway_image(data)
        return f'data:{content_type};base64,{base64.b64encode(image).decode()}'
    from open_webui.utils.files import get_image_base64_from_url

    image = await get_image_base64_from_url(data, user=user)
    if image is None:
        raise HTTPException(400, '只能使用本站文件、内嵌图片或网关图片')
    return image
