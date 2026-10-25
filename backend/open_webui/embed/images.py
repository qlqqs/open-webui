"""Image-only gateway policy; shared by route and built-in tool callers."""

import base64
import aiohttp
from fastapi import HTTPException
from .settings import settings
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
