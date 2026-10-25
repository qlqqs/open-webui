"""Ordered route-prefix policy. First match wins; {name} matches one segment.

Allow exceptions are deliberately narrow. A blocked feature cannot be restored by
an upstream admin/config endpoint. Tool-server administration is the sole config
exception (required by PRD); its network access is constrained by deployment.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    prefix: str
    policy: str  # allow / admin / forbidden / removed
    methods: tuple = ()
    exact: bool = False

    def matches(self, path, method):
        pattern = re.sub(r'\\\{[^}]+\\\}', '[^/]+', re.escape(self.prefix.rstrip('/')))
        return (not self.methods or method in self.methods) and bool(
            re.fullmatch(pattern + ('/?' if self.exact else '(?:/.*)?/?'), path)
        )


RULES = (
    Rule('/api/v1/files/all', 'forbidden'),
    Rule('/api/v1/configs/tool_servers', 'admin'),
    Rule('/api/v1/tools/load/url', 'removed'),
    Rule('/api/v1/functions/load/url', 'removed'),
    Rule('/api/v1/images/verify', 'removed'),
    Rule('/api/v1/retrieval/process/file', 'allow', ('POST',), True),
    Rule('/api/v1/retrieval/process/url', 'removed'),
    Rule('/api/v1/retrieval/process/web', 'removed'),
    Rule('/api/v1/retrieval/process/youtube', 'removed'),
    Rule('/api/v1/retrieval/config', 'forbidden'),
    Rule('/api/v1/retrieval/embedding', 'forbidden'),
    Rule('/api/v1/retrieval', 'removed'),
    # Contract D: only the admin's read-only group list is exposed.
    Rule('/api/v1/groups', 'admin', ('GET',), True),
    *(
        Rule('/api/v1/' + p, 'removed')
        for p in (
            'memories',
            'knowledge',
            'audio',
            'pipelines',
            'terminals',
            'channels',
            'automations',
            'evaluations',
            'analytics',
            'scim',
            'apps',
            'skills',
            'groups',
        )
    ),
    Rule('/api/v1/configs', 'forbidden'),
    Rule('/api/v1/images/config', 'forbidden'),
    Rule('/api/v1/tasks/config', 'forbidden'),
    *(
        Rule('/api/v1/tasks/' + p, 'removed')
        for p in ('follow_up', 'tags', 'queries', 'image_prompt', 'auto', 'emoji', 'moa')
    ),
    *(
        Rule('/api/v1/auths/' + p, 'forbidden')
        for p in (
            'signup',
            'add',
            'update/password',
            'update/profile',
            'api_key',
            'admin',
            'ldap',
            'mfa',
            'oauth',
            'signout',
        )
    ),
    Rule('/oauth', 'removed'),
    Rule('/api/v1/users/user/settings', 'allow'),
    Rule('/api/v1/users/user/variables', 'allow'),
    Rule('/api/v1/users/user/info', 'allow'),
    Rule('/api/v1/users/permissions', 'allow', ('GET',), True),
    Rule('/api/v1/users/{id}/profile/image', 'allow', ('GET',), True),
    Rule('/api/v1/users', 'forbidden'),
    Rule('/api/v1/chats/{id}/clone/shared', 'removed'),
    Rule('/api/v1/chats/{id}/share', 'removed'),
    *(Rule('/api/v1/chats/' + p, 'removed') for p in ('share', 'shared', 'stats', 'all/db', 'list/user')),
    Rule('/api/v1/chats/config', 'forbidden'),
    Rule('/api/v1/utils', 'removed'),
    Rule('/api/embeddings', 'removed'),
    Rule('/api/v1/embeddings', 'removed'),
    Rule('/api/models/base', 'forbidden'),
    Rule('/api/models/unload', 'forbidden'),
    Rule('/api/events', 'forbidden'),
    # Global task IDs are not user-authorized; use the owner-checked chat task endpoints.
    Rule('/api/tasks', 'forbidden', exact=True),
    Rule('/api/tasks/stop', 'forbidden'),
    Rule('/api/usage', 'forbidden'),
    Rule('/api/version/updates', 'removed'),
    Rule('/api/changelog', 'removed'),
    Rule('/ollama', 'removed'),
    Rule('/openai/config', 'forbidden'),
    Rule('/openai/verify', 'forbidden'),
    Rule('/openai/models', 'allow', ('GET',), True),
    Rule('/openai/chat/completions', 'allow', ('POST',), True),
    Rule('/openai/responses', 'allow', ('POST',), True),
    Rule('/openai', 'removed'),
    Rule('/api/v1/models', 'allow', ('GET',), True),
    Rule('/api/v1/models/model/profile/image', 'allow', ('GET',), True),
    Rule('/api/v1/models', 'admin'),
    Rule('/api/v1/prompts', 'allow', ('GET',), True),
    Rule('/api/v1/prompts/tags', 'allow', ('GET',), True),
    Rule('/api/v1/prompts', 'admin'),
    Rule('/api/v1/tools', 'allow', ('GET',), True),
    Rule('/api/v1/tools/id/{id}/specs', 'allow', ('GET',), True),
    Rule('/api/v1/tools', 'admin'),
    # Contract D: chat UI reads installed filter/action metadata, not management routes.
    Rule('/api/v1/functions', 'allow', ('GET',), True),
    Rule('/api/v1/functions', 'admin'),
    Rule('/docs', 'removed'),
    Rule('/redoc', 'removed'),
    Rule('/openapi.json', 'removed'),
)


def route_status(path, method, role):
    for rule in RULES:
        if rule.matches(path, method):
            if rule.policy == 'removed':
                return 404
            if rule.policy == 'forbidden' or rule.policy == 'admin' and role != 'admin':
                return 403
            return None
    return None
