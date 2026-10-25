import pytest
from open_webui.embed.settings import Settings

BASE = {'S2A_EMBED_MODE': '1', 'S2A_GATEWAY_URL': 'http://127.0.0.1:28201', 'S2A_TRUSTED_PROXY_CIDRS': '127.0.0.1/32'}


@pytest.mark.parametrize(
    'url',
    [
        '',
        'ftp://host',
        'http://user:pass@host',
        'http://host/',
        'http://host/v1',
        'http://host?a',
        'http://host?',
        'https://host#',
        'http://host#f',
        'http://host:0',
        'http://host:65536',
        'http://host:abc',
        'http://host\\bad',
        'http://host\n',
        '//host',
        'http://',
    ],
)
def test_invalid_gateway(url):
    with pytest.raises(ValueError):
        Settings.from_env({**BASE, 'S2A_GATEWAY_URL': url})


@pytest.mark.parametrize('url', ['http://sub2api:8080', 'https://gateway', 'http://[::1]:28201'])
def test_valid_gateway(url):
    assert Settings.from_env({**BASE, 'S2A_GATEWAY_URL': url}).gateway_url == url


def test_upstream_defaults_ignore_unused_invalid_settings():
    settings = Settings.from_env({'S2A_GATEWAY_URL': 'bad', 'S2A_IMAGE_MAX_N': 'bad', 'S2A_HIDE_BRANDING': '1'})
    assert not settings.enabled and not settings.hide_branding


def test_fail_closed_proxy_and_limits():
    assert not Settings.from_env({k: v for k, v in BASE.items() if k != 'S2A_TRUSTED_PROXY_CIDRS'}).trusted_proxy_cidrs
    for name, value in [('S2A_TRUSTED_PROXY_CIDRS', 'wrong'), ('S2A_IMAGE_MAX_N', '0')]:
        with pytest.raises(ValueError):
            Settings.from_env({**BASE, name: value})


def test_flags():
    settings = Settings.from_env(
        {
            **BASE,
            'S2A_HIDE_BRANDING': 'true',
            'S2A_NATIVE_WEB_SEARCH': '0',
            'S2A_BUILTIN_TOOL_CATEGORIES': 'time,files',
            'S2A_SLIM_DOC_LOADERS': 'false',
        }
    )
    assert settings.hide_branding and not settings.native_web_search and not settings.slim_doc_loaders
    assert settings.builtin_tool_categories == {'time', 'files'}


def test_default_native_image_category():
    expected = {'time', 'user_input', 'files', 'chats', 'notes', 'tasks', 'calendar', 'image_generation'}
    assert Settings().builtin_tool_categories == expected
    assert Settings.from_env(BASE).builtin_tool_categories == expected
