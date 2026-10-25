# sub2api-embed: CI build; never reuse host build/ or node_modules/.
# HTTP_PROXY / HTTPS_PROXY are Docker predefined build args, not image ENV.
FROM node:22-bookworm-slim AS frontend
WORKDIR /app
ENV ONNXRUNTIME_NODE_INSTALL_CUDA=skip CYPRESS_INSTALL_BINARY=0
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG BUILD_HASH
ENV APP_BUILD_HASH=${BUILD_HASH} APP_BUILD_CHANNEL=unknown OWUI_BASE_PATH=/_chat \
    NODE_OPTIONS=--max-old-space-size=8192
# Do NOT run npm run build: it invokes pyodide:fetch (disabled in embed mode).
RUN npm run crypto:verify \
 && npm exec -- vite build \
 && node scripts/embed-postbuild.mjs \
 && find build -type f -name '*.map' -delete

FROM python:3.12-slim-bookworm AS python-deps
WORKDIR /deps
COPY backend/requirements-slim.txt ./
# Document loader pins match backend/requirements.txt; no model prefetch commands.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements-slim.txt pypdf==6.7.5 docx2txt==0.9

FROM python:3.12-slim-bookworm AS runtime
ARG BUILD_HASH
LABEL org.opencontainers.image.title="Open WebUI — sub2api embed" \
      org.opencontainers.image.source="https://github.com/qlqqs/open-webui" \
      org.opencontainers.image.licenses="LicenseRef-Open-WebUI" \
      org.opencontainers.image.revision="${BUILD_HASH}"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    ENV=prod DOCKER=true PORT=8080 HOST=0.0.0.0 \
    HOME=/home/app DATA_DIR=/app/backend/data FRONTEND_BUILD_DIR=/app/build \
    USE_SLIM_DOCKER=true USE_OLLAMA_DOCKER=false USE_CUDA_DOCKER=false \
    UVICORN_WORKERS=1 DEFAULT_LOCALE=zh-CN WEBUI_BUILD_HASH=${BUILD_HASH} \
    SCARF_NO_ANALYTICS=true DO_NOT_TRACK=true ANONYMIZED_TELEMETRY=false \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1

# contract.md G. Empty trusted CIDRs fail closed; deployment MUST set them.
ENV S2A_EMBED_MODE=1 \
    S2A_GATEWAY_URL=http://sub2api:8080 \
    S2A_TRUSTED_PROXY_CIDRS="" \
    S2A_HIDE_BRANDING=0 \
    S2A_NATIVE_WEB_SEARCH=true \
    S2A_BUILTIN_TOOL_CATEGORIES=time,user_input,files,chats,notes,tasks,calendar,image_generation \
    S2A_SLIM_DOC_LOADERS=true \
    S2A_IMAGE_MAX_N=4

# sub2api-embed: explicit audit mirror of embed/settings.py::configure_environment.
# Python enforces these again, including URLs derived from S2A_GATEWAY_URL.
# ENABLE_PASSWORD_AUTH must stay true for trusted-header authentication.
ENV AIOHTTP_CLIENT_ALLOW_REDIRECTS="false" \
    BYPASS_EMBEDDING_AND_RETRIEVAL="true" \
    CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS="20" \
    CONTENT_EXTRACTION_ENGINE="" \
    DEFAULT_USER_ROLE="user" \
    ENABLE_ADMIN_ANALYTICS="false" \
    ENABLE_ADMIN_CHAT_ACCESS="false" \
    ENABLE_ADMIN_EXPORT="false" \
    ENABLE_API_KEYS="false" \
    ENABLE_APPS="false" \
    ENABLE_AUTOCOMPLETE_GENERATION="false" \
    ENABLE_AUTOMATIONS="false" \
    ENABLE_BASE_MODELS_CACHE="false" \
    ENABLE_CHANNELS="false" \
    ENABLE_CODE_EXECUTION="false" \
    ENABLE_CODE_INTERPRETER="false" \
    ENABLE_COMMUNITY_SHARING="false" \
    ENABLE_DIRECT_CONNECTIONS="false" \
    ENABLE_DIRECT_INTEGRATIONS="false" \
    ENABLE_EVALUATION_ARENA_MODELS="false" \
    ENABLE_FOLLOW_UP_GENERATION="false" \
    ENABLE_FORWARD_USER_INFO_HEADERS="false" \
    ENABLE_GOOGLE_DRIVE_INTEGRATION="false" \
    ENABLE_IMAGE_EDIT="true" \
    ENABLE_IMAGE_GENERATION="true" \
    ENABLE_IMAGE_PROMPT_GENERATION="false" \
    ENABLE_INITIAL_ADMIN_SIGNUP="false" \
    ENABLE_LDAP="false" \
    ENABLE_LOGIN_FORM="false" \
    ENABLE_MEMORIES="false" \
    ENABLE_MESSAGE_RATING="false" \
    ENABLE_MFA="false" \
    ENABLE_OAUTH="false" \
    ENABLE_OLLAMA_API="false" \
    ENABLE_ONEDRIVE_INTEGRATION="false" \
    ENABLE_OPENAI_API="true" \
    ENABLE_OPENAI_API_PASSTHROUGH="false" \
    ENABLE_OTEL="false" \
    ENABLE_PASSWORD_AUTH="true" \
    ENABLE_PASSWORD_CHANGE_FORM="false" \
    ENABLE_PERSISTENT_CONFIG="false" \
    ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS="false" \
    ENABLE_PLUGINS="true" \
    ENABLE_RETRIEVAL_QUERY_GENERATION="false" \
    ENABLE_SCIM="false" \
    ENABLE_SIGNUP="false" \
    ENABLE_SUBAGENTS="false" \
    ENABLE_TAGS_GENERATION="false" \
    ENABLE_TITLE_GENERATION="true" \
    ENABLE_USER_WEBHOOKS="false" \
    ENABLE_VERSION_UPDATE_CHECK="false" \
    ENABLE_WEB_SEARCH="false" \
    IMAGE_EDIT_ENGINE="openai" \
    IMAGE_EDIT_MODEL="gpt-image-1" \
    IMAGE_GENERATION_ENGINE="openai" \
    IMAGE_GENERATION_MODEL="gpt-image-1" \
    OFFLINE_MODE="true" \
    OLLAMA_BASE_URL="http://sub2api:8080" \
    OPENAI_API_BASE_URL="http://sub2api:8080/v1" \
    OPENAI_API_BASE_URLS="http://sub2api:8080/v1" \
    OPENAI_API_CONFIGS="{}" \
    PDF_EXTRACT_IMAGES="false" \
    RAG_ALLOWED_FILE_EXTENSIONS="pdf,docx,txt,md,csv,html,htm,json,xml,yaml,yml,py,js,ts,tsx,jsx,css,go,rs,c,cpp,h,java,sh,sql,log" \
    RAG_FILE_MAX_SIZE="25" \
    TERMINAL_SERVER_CONNECTIONS="[]" \
    USER_PERMISSIONS_CHAT_CALL="false" \
    USER_PERMISSIONS_CHAT_SHARE="false" \
    USER_PERMISSIONS_CHAT_STT="false" \
    USER_PERMISSIONS_CHAT_TTS="false" \
    USER_PERMISSIONS_FEATURES_API_KEYS="false" \
    USER_PERMISSIONS_FEATURES_AUTOMATIONS="false" \
    USER_PERMISSIONS_FEATURES_CHANNELS="false" \
    USER_PERMISSIONS_FEATURES_CODE_INTERPRETER="false" \
    USER_PERMISSIONS_FEATURES_DIRECT_TOOL_SERVERS="false" \
    USER_PERMISSIONS_FEATURES_MEMORIES="false" \
    USER_PERMISSIONS_FEATURES_WEBHOOKS="false" \
    USER_PERMISSIONS_WORKSPACE_KNOWLEDGE="false" \
    USER_PERMISSIONS_WORKSPACE_MODELS="false" \
    USER_PERMISSIONS_WORKSPACE_MODELS_IMPORT="false" \
    USER_PERMISSIONS_WORKSPACE_PROMPTS="false" \
    USER_PERMISSIONS_WORKSPACE_PROMPTS_IMPORT="false" \
    USER_PERMISSIONS_WORKSPACE_SKILLS="false" \
    USER_PERMISSIONS_WORKSPACE_TOOLS="false" \
    USER_PERMISSIONS_WORKSPACE_TOOLS_IMPORT="false" \
    WEBUI_AUTH="true" \
    WEBUI_AUTH_TRUSTED_EMAIL_HEADER="X-Sub2API-Email" \
    WEBUI_AUTH_TRUSTED_NAME_HEADER="X-Sub2API-Name" \
    WEBUI_AUTH_TRUSTED_ROLE_HEADER="X-Sub2API-User-Role"

RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/app app \
 && mkdir -p /app/backend/data \
 && chown -R 1000:1000 /app
COPY --from=python-deps /opt/venv /opt/venv
COPY --chown=1000:1000 backend /app/backend
COPY --from=frontend --chown=1000:1000 /app/build /app/build
COPY --chown=1000:1000 package.json CHANGELOG.md LICENSE LICENSE_HISTORY LICENSE_NOTICE /app/
WORKDIR /app/backend
USER 1000:1000
EXPOSE 8080
# /health is authenticated. Bypass any runtime proxy for this loopback static probe.
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import os, urllib.request; r=urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/static/favicon.png', timeout=4); assert r.status == 200"
# start.sh forces --no-proxy-headers and rejects --root-path in embed mode.
CMD ["bash", "start.sh"]
