import re
import pytest
from open_webui.embed.blocklist import RULES, route_status


@pytest.mark.parametrize('rule', RULES, ids=lambda r: r.prefix + ':' + r.policy)
@pytest.mark.parametrize('role', ['user', 'admin'])
def test_every_policy(rule, role):
    path = re.sub(r'\{[^}]+\}', 'sample', rule.prefix)
    method = rule.methods[0] if rule.methods else 'POST'
    # Validate each row independently and account for intentionally ordered exceptions.
    assert rule.matches(path, method)
    first = next(r for r in RULES if r.matches(path, method))
    expected = (
        404
        if first.policy == 'removed'
        else 403 if first.policy == 'forbidden' or first.policy == 'admin' and role == 'user' else None
    )
    assert route_status(path, method, role) == expected
    assert not rule.matches(path + '-not-a-child', method)


@pytest.mark.parametrize(
    'path',
    [
        '/api/v1/memories',
        '/api/v1/knowledge',
        '/api/v1/retrieval/query/doc',
        '/api/v1/retrieval/query/collection',
        '/api/v1/retrieval/process/text',
        '/api/v1/retrieval/process/web',
        '/api/v1/retrieval/process/youtube',
        '/api/v1/tools/load/url',
        '/api/v1/functions/load/url',
        '/api/v1/images/verify',
        '/api/v1/chats/abc/share',
        '/api/v1/chats/abc/clone/shared',
    ],
)
def test_disabled_surfaces_for_both_roles(path):
    for role in ('user', 'admin'):
        assert route_status(path, 'POST', role) == 404


@pytest.mark.parametrize(
    'path,method',
    [
        ('/api/v1/users/user/settings/update', 'POST'),
        ('/api/v1/chats/new', 'POST'),
        ('/api/v1/notes', 'GET'),
        ('/api/v1/calendars', 'GET'),
        ('/api/v1/tools', 'GET'),
        ('/api/v1/prompts', 'GET'),
        ('/api/v1/retrieval/process/file', 'POST'),
        ('/api/models', 'GET'),
        ('/api/v1/auths/signin', 'POST'),
    ],
)
def test_retained_user_surfaces(path, method):
    assert route_status(path, method, 'user') is None


@pytest.mark.parametrize('trailing', ['', '/'])
@pytest.mark.parametrize('role', ['user', 'admin'])
def test_contract_readonly_lists(trailing, role):
    assert route_status('/api/v1/functions' + trailing, 'GET', role) is None
    assert route_status('/api/v1/groups' + trailing, 'GET', role) == (None if role == 'admin' else 403)


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'])
@pytest.mark.parametrize('role', ['user', 'admin'])
def test_list_exception_does_not_allow_writes(method, role):
    assert route_status('/api/v1/groups/', method, role) == 404
    assert route_status('/api/v1/functions/', method, role) == (None if role == 'admin' else 403)


@pytest.mark.parametrize('suffix', ['/list', '/export', '/create', '/id/one', '//', '-extra'])
@pytest.mark.parametrize('role', ['user', 'admin'])
def test_list_exception_is_not_a_prefix(suffix, role):
    # '-extra' is outside both namespaces and must not match either exception.
    from open_webui.embed.blocklist import Rule

    assert not Rule('/api/v1/functions', 'allow', ('GET',), True).matches('/api/v1/functions' + suffix, 'GET')
    assert not Rule('/api/v1/groups', 'admin', ('GET',), True).matches('/api/v1/groups' + suffix, 'GET')
    if suffix != '-extra':
        assert route_status('/api/v1/groups' + suffix, 'GET', role) == 404
        assert route_status('/api/v1/functions' + suffix, 'GET', role) == (None if role == 'admin' else 403)
