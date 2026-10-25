"""Per-request billing context. Never fall back to installation-wide credentials."""

from contextvars import ContextVar
from urllib.parse import urlsplit
from fastapi import HTTPException
from .settings import settings

SUB2API_KEY = ContextVar('sub2api_key', default='')
SUB2API_IMAGE_KEY = ContextVar('sub2api_image_key', default='')
SUB2API_KEY_PLATFORM = ContextVar('sub2api_key_platform', default='')
SUB2API_CLIENT_IP = ContextVar('sub2api_client_ip', default='')


def current_key(image=False):
    key = (SUB2API_IMAGE_KEY.get() if image else '') or SUB2API_KEY.get()
    if not key:
        raise HTTPException(400, '请选择可用的 Key')
    return key


def connection():
    return (
        settings.gateway_url + '/v1',
        current_key(),
        {
            'api_type': 'responses' if SUB2API_KEY_PLATFORM.get() == 'openai' else 'chat_completions',
        },
    )


def require_gateway_url(url):
    try:
        parsed, gateway = urlsplit(url), urlsplit(settings.gateway_url)
        if (
            (parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
            != (gateway.scheme, gateway.hostname, gateway.port or (443 if gateway.scheme == 'https' else 80))
            or parsed.username is not None
            or parsed.password is not None
            or '\\' in url
        ):
            raise ValueError()
    except ValueError:
        raise HTTPException(400, '只允许访问本站网关') from None


def headers(image=False):
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {current_key(image)}',
        'X-Forwarded-For': SUB2API_CLIENT_IP.get(),
    }


def reject_direct(model_item):
    if settings.enabled and model_item.get('direct'):
        raise HTTPException(403, '不允许直连模型')
