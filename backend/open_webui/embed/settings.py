"""Fail-closed settings; deliberately independent of Open WebUI's config/DB."""

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def boolean(value):
    return str(value).lower() in ('1', 'true', 'yes', 'on')


def origin(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ('http', 'https')
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or '?' in value
            or '#' in value
            or '\\' in value
            or '%' in parsed.netloc
            or parsed.netloc.endswith(':')
            or any(c.isspace() or ord(c) < 32 for c in value)
        ):
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
        return value
    except ValueError:
        raise ValueError(
            'S2A_GATEWAY_URL must be an http(s) origin without path, credentials, query or fragment'
        ) from None


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    gateway_url: str = ''
    trusted_proxy_cidrs: tuple = ()
    hide_branding: bool = False
    native_web_search: bool = True
    builtin_tool_categories: frozenset = frozenset(
        ('time', 'user_input', 'files', 'chats', 'notes', 'tasks', 'calendar', 'image_generation')
    )
    slim_doc_loaders: bool = True
    image_max_n: int = 4

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        if not boolean(env.get('S2A_EMBED_MODE', '0')):
            return cls()  # Do not even validate unused embed settings in upstream mode.
        gateway = origin(env.get('S2A_GATEWAY_URL', ''))
        cidrs = tuple(
            ipaddress.ip_network(c.strip(), strict=True)
            for c in env.get('S2A_TRUSTED_PROXY_CIDRS', '').split(',')
            if c.strip()
        )
        maximum = int(env.get('S2A_IMAGE_MAX_N', '4'))
        if maximum < 1:
            raise ValueError('S2A_IMAGE_MAX_N must be positive')
        return cls(
            True,
            gateway,
            cidrs,
            boolean(env.get('S2A_HIDE_BRANDING', '0')),
            boolean(env.get('S2A_NATIVE_WEB_SEARCH', 'true')),
            frozenset(
                c.strip()
                for c in env.get(
                    'S2A_BUILTIN_TOOL_CATEGORIES', 'time,user_input,files,chats,notes,tasks,calendar,image_generation'
                ).split(',')
                if c.strip()
            ),
            boolean(env.get('S2A_SLIM_DOC_LOADERS', 'true')),
            maximum,
        )


settings = Settings.from_env()


def configure_environment():
    """Security invariants, applied before upstream env/config imports (embed only).

    Deployment still needs an internal-only network and an allowlisted plugin proxy.
    No key is ever placed in process environment or persistent configuration.
    """
    if not settings.enabled:
        return
    disabled = '''ENABLE_SIGNUP ENABLE_LOGIN_FORM ENABLE_INITIAL_ADMIN_SIGNUP
        ENABLE_PASSWORD_CHANGE_FORM ENABLE_MFA ENABLE_PERSISTENT_CONFIG ENABLE_API_KEYS ENABLE_OAUTH ENABLE_LDAP ENABLE_SCIM
        ENABLE_VERSION_UPDATE_CHECK ENABLE_OLLAMA_API ENABLE_DIRECT_CONNECTIONS ENABLE_DIRECT_INTEGRATIONS
        ENABLE_WEB_SEARCH ENABLE_COMMUNITY_SHARING ENABLE_USER_WEBHOOKS ENABLE_MEMORIES ENABLE_CODE_EXECUTION
        ENABLE_CODE_INTERPRETER ENABLE_CHANNELS ENABLE_AUTOMATIONS ENABLE_SUBAGENTS ENABLE_ADMIN_CHAT_ACCESS
        ENABLE_ADMIN_EXPORT ENABLE_ADMIN_ANALYTICS ENABLE_EVALUATION_ARENA_MODELS ENABLE_MESSAGE_RATING
        ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS ENABLE_TAGS_GENERATION ENABLE_FOLLOW_UP_GENERATION
        ENABLE_RETRIEVAL_QUERY_GENERATION ENABLE_IMAGE_PROMPT_GENERATION ENABLE_AUTOCOMPLETE_GENERATION
        ENABLE_GOOGLE_DRIVE_INTEGRATION ENABLE_ONEDRIVE_INTEGRATION ENABLE_APPS ENABLE_BASE_MODELS_CACHE
        ENABLE_FORWARD_USER_INFO_HEADERS ENABLE_OPENAI_API_PASSTHROUGH ENABLE_OTEL'''.split()
    for name in disabled:
        os.environ[name] = 'false'
    for name in (
        'OFFLINE_MODE',
        'WEBUI_AUTH',
        'ENABLE_PASSWORD_AUTH',
        'ENABLE_OPENAI_API',
        'BYPASS_EMBEDDING_AND_RETRIEVAL',
        'ENABLE_PLUGINS',
        'ENABLE_IMAGE_GENERATION',
        'ENABLE_IMAGE_EDIT',
        'ENABLE_TITLE_GENERATION',
    ):
        os.environ[name] = 'true'
    for suffix in (
        'FEATURES_MEMORIES',
        'FEATURES_CODE_INTERPRETER',
        'FEATURES_CHANNELS',
        'FEATURES_DIRECT_TOOL_SERVERS',
        'FEATURES_API_KEYS',
        'FEATURES_AUTOMATIONS',
        'FEATURES_WEBHOOKS',
        'CHAT_SHARE',
        'CHAT_STT',
        'CHAT_TTS',
        'CHAT_CALL',
        'WORKSPACE_TOOLS',
        'WORKSPACE_TOOLS_IMPORT',
        'WORKSPACE_MODELS',
        'WORKSPACE_MODELS_IMPORT',
        'WORKSPACE_PROMPTS',
        'WORKSPACE_PROMPTS_IMPORT',
        'WORKSPACE_KNOWLEDGE',
        'WORKSPACE_SKILLS',
    ):
        os.environ['USER_PERMISSIONS_' + suffix] = 'false'
    os.environ.update(
        {
            'WEBUI_AUTH_TRUSTED_EMAIL_HEADER': 'X-Sub2API-Email',
            'WEBUI_AUTH_TRUSTED_NAME_HEADER': 'X-Sub2API-Name',
            'WEBUI_AUTH_TRUSTED_ROLE_HEADER': 'X-Sub2API-User-Role',
            'DEFAULT_USER_ROLE': 'user',
            'TERMINAL_SERVER_CONNECTIONS': '[]',
            'OLLAMA_BASE_URL': settings.gateway_url,  # suppress upstream's startup port probes
            'CONTENT_EXTRACTION_ENGINE': '',
            'PDF_EXTRACT_IMAGES': 'false',
            'OPENAI_API_BASE_URL': settings.gateway_url + '/v1',
            'OPENAI_API_BASE_URLS': settings.gateway_url + '/v1',
            'OPENAI_API_KEY': '',
            'OPENAI_API_KEYS': '',
            'OPENAI_API_CONFIGS': '{}',
            'IMAGE_GENERATION_ENGINE': 'openai',
            'IMAGE_EDIT_ENGINE': 'openai',
            'AIOHTTP_CLIENT_ALLOW_REDIRECTS': 'false',
        }
    )
    for name in (
        'LICENSE_KEY',
        'CUSTOM_NAME',
        'WEBUI_AUTH_TRUSTED_GROUPS_HEADER',
        'WEBUI_ADMIN_EMAIL',
        'WEBUI_ADMIN_PASSWORD',
    ):
        os.environ.pop(name, None)
    os.environ.setdefault('IMAGE_GENERATION_MODEL', 'gpt-image-1')
    os.environ.setdefault('IMAGE_EDIT_MODEL', 'gpt-image-1')
    os.environ.setdefault('CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS', '20')
    os.environ.setdefault('RAG_FILE_MAX_SIZE', '25')
    os.environ.setdefault(
        'RAG_ALLOWED_FILE_EXTENSIONS',
        'pdf,docx,txt,md,csv,html,htm,json,xml,yaml,yml,py,js,ts,tsx,jsx,css,go,rs,c,cpp,h,java,sh,sql,log',
    )
