"""TCP-peer trust boundary. Must run outside all upstream HTTP/socket middleware."""

import ipaddress
import re
from urllib.parse import quote, unquote
from starlette.responses import JSONResponse
from .settings import settings
from .gateway import SUB2API_KEY, SUB2API_IMAGE_KEY, SUB2API_KEY_PLATFORM, SUB2API_CLIENT_IP
from .blocklist import route_status


def is_static(scope):
    if scope['type'] != 'http' or scope.get('method') not in ('GET', 'HEAD'):
        return False
    path = scope.get('path', '/')
    if path.startswith(('/_app/', '/static/', '/assets/', '/favicon', '/embed/')) or path == '/manifest.json':
        return True
    headers = dict(scope.get('headers', ()))
    return (
        scope.get('method') == 'GET'
        and b'text/html' in headers.get(b'accept', b'')
        and not any(
            path == p or path.startswith(p + '/')
            for p in (
                '/api',
                '/ws',
                '/oauth',
                '/openai',
                '/ollama',
                '/cache',
                '/health',
                '/ready',
                '/docs',
                '/redoc',
                '/openapi.json',
            )
        )
    )


def normalize_display_name(value):
    """Validate B.4, then keep the trusted-name header ASCII on both transports.

    Upstream signin unquotes its trusted NAME header once. Decode strictly here
    before canonical re-encoding; putting decoded UTF-8 bytes into scope headers
    would break websocket handshakes. A literal '%2F' remains '%2F', not '/'.
    """
    encoded = value.decode('ascii')
    if re.search(r'%(?![0-9A-Fa-f]{2})', encoded):
        raise ValueError('Malformed percent escape')
    name = unquote(encoded, encoding='utf-8', errors='strict')
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError('Control character in display name')
    return quote(name, safe='').encode('ascii')


def validate_identity(headers):
    if any(
        len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value)
        for name, value in headers.items()
        if name.startswith('x-sub2api-')
    ):
        return False
    uid = headers.get('x-sub2api-user-id', '')
    if not re.fullmatch(r'[1-9][0-9]{0,19}', uid):
        return False
    if headers.get('x-sub2api-email') != f'u{uid}@sub2api.internal':
        return False
    if headers.get('x-sub2api-user-role') not in ('user', 'admin'):
        return False
    for name in ('x-sub2api-key', 'x-sub2api-image-key'):
        value = headers.get(name, '')
        if value and (len(value) > 4096 or not re.fullmatch(r'[\x21-\x7e]+', value)):
            return False
    platform = headers.get('x-sub2api-key-platform', '')
    if platform and not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', platform):
        return False
    try:
        ip = ipaddress.ip_address(headers.get('x-forwarded-for', ''))
        if headers.get('x-real-ip') and ipaddress.ip_address(headers['x-real-ip']) != ip:
            return False
    except ValueError:
        return False
    return True


async def deny(scope, receive, send, status, detail):
    if scope['type'] == 'websocket':
        await send({'type': 'websocket.close', 'code': 1008})
    else:
        await JSONResponse({'detail': detail}, status_code=status)(scope, receive, send)


class Sub2APIAuthMiddleware:
    def __init__(self, app, config=settings):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if not self.config.enabled or scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        scope = dict(scope)
        raw_headers = list(scope.get('headers', ()))
        scope['headers'] = raw_headers
        try:
            peer = ipaddress.ip_address((scope.get('client') or ('', 0))[0])
            trusted = any(peer in network for network in self.config.trusted_proxy_cidrs)
        except ValueError:
            trusted = False
        if not trusted:
            scope['headers'] = [(k, v) for k, v in raw_headers if not k.lower().startswith(b'x-sub2api-')]
            if not is_static(scope):
                return await deny(scope, receive, send, 403, '不可信的反向代理')
            return await self.app(scope, receive, send)
        # Static navigation is anonymous, even if supplied with unnecessary headers.
        if is_static(scope):
            scope['headers'] = [(k, v) for k, v in raw_headers if not k.lower().startswith(b'x-sub2api-')]
            return await self.app(scope, receive, send)
        names = [
            k.lower() for k, v in raw_headers if k.lower().startswith(b'x-sub2api-') or k.lower() == b'x-forwarded-for'
        ]
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k, v in raw_headers}
        if len(set(names)) != len(names) or not validate_identity(headers):
            return await deny(scope, receive, send, 401, '缺少或无效的 sub2api 身份头')
        # B.4 uses percent-encoded UTF-8. Never put decoded Unicode into handshake headers.
        normalized = []
        for name, value in raw_headers:
            if name.lower() == b'x-sub2api-name':
                try:
                    value = normalize_display_name(value)
                except ValueError:
                    return await deny(scope, receive, send, 401, '无效的用户显示名')
            normalized.append((name, value))
        raw_headers = normalized
        scope['client'] = (headers['x-forwarded-for'], (scope.get('client') or ('', 0))[1])
        scope.setdefault('state', {})['sub2api_identity'] = headers['x-sub2api-email']
        status = route_status(scope['path'], scope.get('method', 'GET'), headers['x-sub2api-user-role'])
        if status:
            return await deny(
                scope, receive, send, status, 'Not Found' if status == 404 else '此功能在嵌入模式下不可用'
            )
        # WebSocket (including engine.io HTTP polling) must never retain billing keys.
        if scope['type'] != 'http' or scope['path'].startswith('/ws/'):
            scope['headers'] = [
                (k, v)
                for k, v in raw_headers
                if k.lower() not in (b'x-sub2api-key', b'x-sub2api-image-key', b'x-sub2api-key-platform')
            ]
            return await self.app(scope, receive, send)
        pairs = (
            (SUB2API_KEY, headers.get('x-sub2api-key', '')),
            (SUB2API_IMAGE_KEY, headers.get('x-sub2api-image-key', '')),
            (SUB2API_KEY_PLATFORM, headers.get('x-sub2api-key-platform', '')),
            (SUB2API_CLIENT_IP, headers['x-forwarded-for']),
        )
        tokens = [(var, var.set(value)) for var, value in pairs]
        # Avoid accidental disclosure by upstream logging, plugins receive context only.
        scope['headers'] = [
            (k, v)
            for k, v in raw_headers
            if k.lower() not in (b'x-sub2api-key', b'x-sub2api-image-key', b'x-sub2api-key-platform')
        ]
        try:
            await self.app(scope, receive, send)
        finally:
            for var, token in reversed(tokens):
                var.reset(token)


async def sync_user(user, headers):
    from fastapi import HTTPException
    from open_webui.models.users import Users

    if not headers.get('x-sub2api-email') or user.email != headers.get('x-sub2api-email'):
        raise HTTPException(401, 'User mismatch. Please sign in again.')
    role = headers.get('x-sub2api-user-role')
    if role not in ('admin', 'user'):
        raise HTTPException(401, 'Invalid role')
    if role != user.role:
        await Users.update_user_role_by_id(user.id, role)
        user = user.model_copy(update={'role': role})
    return user


async def sync_config_user(user, headers):
    """Config bootstraps a fresh signin after account switching, not a 401 loop.

    This exception is intentionally local to /api/config. Do not downgrade or
    otherwise modify the stale token's account using the new identity's role.
    The ASGI boundary still rejects missing/invalid trusted identity headers.
    """
    if user.email != headers.get('x-sub2api-email'):
        return None
    return await sync_user(user, headers)


def socket_identity_matches(user, environ):
    if not settings.enabled:
        return True
    scope = (environ or {}).get('asgi.scope') or {}
    headers = {k.decode().lower(): v.decode('latin1') for k, v in scope.get('headers', ())}
    return bool(
        user
        and headers.get('x-sub2api-email') == user.email
        and headers.get('x-sub2api-user-role') in ('user', 'admin')
    )
