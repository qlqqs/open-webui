# 对话工作台：sub2api 嵌入契约

适用：`qlqqs/open-webui` 的 `sub2api-custom` 分支，基线 v0.12.3；2026-10-24。
本文把任务目录 `10-24-chat-openwebui/contract.md` A–G 固化为部署文档；冲突以任务契约为准。
后端行为以 `backend/open_webui/embed/`、阶段 1 报告的**末次补充**为准（旧版生图白名单及管理员隔离问题已修复）。
前端构建、桥接与 Artifact 协议另见 `docs/sub2api-embed-frontend.md`（阶段 2 维护），本文 §5–6 与其 §5–7 对齐；实现位于 `src/lib/embed/`、`static/embed/`。

## 1. 拓扑与路径

```text
浏览器 → 站点反代 → sub2api
  /chat                      控制台父页面
  /api/v1/chat/*              sub2api 会话与状态接口
  /_chat/__sub2api/*          sub2api 自有接口，不转发给 Open WebUI
  /_chat/*                   剥掉 /_chat 后 → chat-webui:8080
  /_chat/ws/socket.io/        同上，支持 WebSocket 升级及 HTTP polling
                                  ↓ 当前用户所选 Key
                             sub2api:8080/v1/*
```

- 前端编译 `OWUI_BASE_PATH=/_chat`，产物在 `/app/build`，不生成嵌套的 `build/_chat`。
- 后端按根路径服务；必须通过 `start.sh` 启动，嵌入模式强制 `--no-proxy-headers`，**禁止 `--root-path`**，否则可能破坏 engine.io 路由与 TCP 来源校验。
- `WEBUI_URL=https://<站点域名>/_chat`；不用独立的 `/api/chat` 前缀，也不把 WebUI 端口暴露给浏览器。
- sub2api 的 `CHAT_WEBUI_URL=http://chat-webui:8080`；空值关闭入口，反代及会话签发返回 503；上游不可达时反代返回 503。
- `GET /api/v1/chat/status` 返回 `{code:0,data:{enabled:boolean}}`，仅表示是否配置 `CHAT_WEBUI_URL`，不是上游健康探针。

## 2. 会话、Cookie 与请求头

父页先以本站 Bearer JWT 调 `POST /api/v1/chat/session`，成功才加载 `/_chat/?lang=<locale>`。
响应 `{code:0,data:{expires_at}}` 并设置：

```http
Set-Cookie: s2a_chat=<当前 access token>; Path=/_chat; HttpOnly; SameSite=Strict
```

HTTPS 加 `Secure`（判定同 sub2api 现有 Cookie）。token 刷新后父页重新签发；退出/换账号调用 `DELETE /api/v1/chat/session`，以同 Path、`Max-Age=0` 清除，无需登录态仍有效。
`Authorization` 和 `token` Cookie 留给 Open WebUI 自身；其 Cookie Path 固定 `/_chat`。sub2api JWT 不经 postMessage 传给 iframe。

iframe 的 `/_chat/` fetch 可携带 `X-Sub2API-Key-Id` 和可选 `X-Sub2API-Image-Key-Id`，**只传 ID，不传明文**。
图片、下载、WebSocket 不需要这两个头。

sub2api 先读取候选 ID、校验归属及可用性，然后删除客户端全部 `X-Sub2API-*`、`X-Forwarded-*`、`X-Real-IP`、`Forwarded`，再重建可信头：

| 头 | 值 |
|---|---|
| `X-Sub2API-User-Id` | 当前用户 ID |
| `X-Sub2API-Email` | `u<ID>@sub2api.internal` |
| `X-Sub2API-Name` | 用户名，空则邮箱 `@` 前部分 |
| `X-Sub2API-User-Role` | `admin` 或 `user`，每请求同步 |
| `X-Sub2API-Key` | 属于本人、有效、未过期、额度未用完的对话 Key 明文，否则不注入 |
| `X-Sub2API-Key-Platform` | 分组 platform 原值，只在注入对话 Key 时附加 |
| `X-Sub2API-Image-Key` | 同上校验，且分组支持生图的可选 Key |
| `X-Forwarded-For` / `X-Real-IP` | 经 sub2api 按 studio_proxy 规则解析的真实 IP，单个值 |

- 静态免 Cookie：`/_chat/_app/*`、`static/*`、`assets/*`、`favicon*`、`manifest.json`、`embed/*`（均在 `/_chat` 下）。HTML 页面导航也免 Cookie：GET、Accept 含 `text/html`，且不在 `/_chat/api/`、`/_chat/ws/`、`/_chat/oauth/` 下。免 Cookie 请求不注入身份。
- 其他请求校验 `s2a_chat` 的签名、过期、封禁、token 版本。无效返回 HTTP 401：`{"error":{"code":"CHAT_SESSION_INVALID","message":"登录已失效"}}`，不转发。
- fork 只信任原始 TCP peer 落在 `S2A_TRUSTED_PROXY_CIDRS` 中的头。不可信 peer：剥头且非静态 403；可信但无有效身份的非静态请求 401。不得设 `0.0.0.0/0` 或依赖 uvicorn 改写后的 XFF。
- WebSocket 升级不注入计费 Key；fork 对 WebSocket **及 engine.io polling** 都不捕获计费 Key。旧连接无法自动感知后来删除的 sub2api Cookie，父页撤销时必须断开并销毁 iframe。
- 用户首次可信头登录自动开通，不自动把首用户变管理员；旧 WebUI JWT 与新头的合成邮箱不匹配时拒绝。
- 管理员没有读取/修改他人聊天、文件、笔记、日历的角色旁路；显式共享仍遵循原版 ACL。

反代保留查询串；根相对（单 `/`）`Location` 补 `/_chat`（避免重复前缀）；`Set-Cookie: Path=/` 改为 `Path=/_chat` 兜底。
上传 `/_chat/api/v1/files/` 请求体最多 **26 MiB**（25 MiB 文件 + 1 MiB multipart 余量），其他请求 **5 MiB**，超限 413。后端仍单独校验文件默认最多 **25 MiB**，不得把反代请求上限当作文件上限。已知及未知 Content-Length 均执行相同请求体限制。

## 3. `__sub2api` 接口

均在 `/_chat/__sub2api/` 下，使用 `s2a_chat` 鉴权，返回**原始 JSON**，不套 `{code,data}`。
写操作必须 `Content-Type: application/json`，否则 415。
错误统一 `{"error":{"code":"<机器码>","message":"<中文>"}}` 与对应 HTTP 状态。

### Keys / Groups

`GET keys`：

```json
{"keys":[{"id":12,"name":"默认","status":"active","usable":true,"unusable_reason":"","group":{"id":3,"name":"Claude","platform":"anthropic"},"supports_chat":true,"supports_images":false,"quota":0,"quota_used":0,"expires_at":null}]}
```

`unusable_reason` 为 `disabled / expired / quota_exhausted / group_unavailable` 或空，前端映射中文。
额度以美元计，`quota=0` 表示不限；过期时间为 RFC3339 或 null。
生图支持：分组开启 `allow_image_generation`，且平台为 `openai / grok / composite`。
可含 `masked` 脱敏片段，任何响应均不含完整 Key。

- `POST keys`：`{"name":"对话","group_id":3}`，只允许本人可用分组；返回 `{"key":<上述单项>}`，不返回明文。
- `GET groups`：`{"groups":[{"id":3,"name":"Claude","platform":"anthropic","description":"","supports_images":false}]}`，与控制台创建 Key 的可选分组一致。
- `GET model-prices?key_id=12`：`{"models":[{"id":"claude-sonnet-4-5","price_text":"输入 ¥3.00 / 百万 tokens · 输出 ¥15.00 / 百万 tokens"}]}`。按所选 Key 分组及当前用户的模型广场口径生成（币种/汇率一致，不展示倍率）；无价格项省略；他人的 Key 返回 404。
- `GET model-reasoning?key_id=12&model=a&model=b`（最多 300 个 `model`）：`{"models":{"claude-opus-5-5":{"levels":["low","medium","high","xhigh","max"],"default":"medium","multipliers":{"max":1.5}}}}`。档位与网关 Codex 模型清单同源，按该 Key 分组的「最高思考档」裁掉超限档位；不足两档的模型省略；`multipliers` 只列渠道定价里 ≠1 的档位倍率。他人的 Key 返回 404。

Key ID 保存在 WebUI 原版用户设置 `ui.sub2api={"key_id":12,"image_key_id":34}`，通过 `/api/v1/users/user/settings` 更新，按用户隔离。
模型列表仍由 fork 后端拿该 Key 调固定网关 `/v1/models`；价格接口不替代模型授权。

## 4. 固定网关与功能面

- `S2A_GATEWAY_URL` 必须是无路径、尾斜杠、凭据、query、fragment 的 HTTP(S) origin；后端自行追加 `/v1`。
- 每请求通过 ContextVar 读取对话/生图 Key，不持久化明文、不回退到环境或数据库中的 Key。空对话 Key 的模型请求返回 400 `{"detail":"请选择可用的 Key"}`。
- OpenAI 平台走 Responses（`convert_to_responses_payload` 把顶层 `reasoning_effort` 转成 `reasoning.effort`，已有 `reasoning.effort` 时以它为准）；其他平台走 Chat Completions；后台标题、工具循环等继承当次上下文，携带真实 IP，不自动跟随重定向、不转发 Cookie。
- 对话列表按 `S2A_HIDDEN_CHAT_MODELS` 隐藏内部模型和纯生图模型；完整模型缓存不变，隐藏不禁止直接按 ID 调用。
- 生图/编辑共用 per-Key SHA-256、60 秒模型缓存：先使用该 Key 可用的配置模型，否则依次选 `gpt-image-2`、其他 `gpt-image*`、其他生图模型（同级按名字忽略大小写排序）。无生图模型返回 400「当前生图 Key 所在分组没有可用的生图模型」；模型列表失败保留 `s2a_gateway_error`，两者均不发出计费的生图/编辑请求。内置生图工具走同一路径。
- 生图优先生图 Key，否则回退对话 Key；`n` 默认上限 4。生成/编辑结果同时含 `b64_json` 和 `url` 时优先取 base64（网关回填会保留原 URL），不下载外部链接；只有 URL 时仍只允许同网关 origin，否则拒绝，且可能发生在上游已计费之后。
- 联网搜索由网关原生 `web_search` 完成，不启用 WebUI 自建搜索和网页抓取。
- 开启全文附件，绕过 embedding/向量库；slim 加 pypdf、docx2txt，PDF 不 OCR。工具类别默认含 `image_generation`，保留原生工具模式生图。
- 工具服务器 `/api/v1/configs/tool_servers` 及 verify 仅 admin 可写，且配置持久化；其他 configs 写入口禁止。只允许可信管理员管理预设助手/提示词、Functions/Tools/MCP。
- 关闭语音、RAG/记忆、代码解释器、频道、自动化、子代理、分享、评分、终端、连接配置、自身 API Key/OAuth 等；由后端路由封锁，不只是隐藏 UI。
- `/api/config` 在嵌入模式新增 `sub2api={embed:true,hide_branding:false,native_web_search:true,image_generation:true}`，实际开关随配置；非嵌入模式无此字段。

## 5. 父页 postMessage

双方校验 `event.origin === location.origin`，同时校验 `event.source`：iframe 要求 `window.parent`；父页要求该 `iframe.contentWindow`。发送时使用明确同源 targetOrigin。

```ts
// 父 → iframe（不含 JWT / Key）
{ type: 'sub2api:chat-session', revision: number, theme: 'light' | 'dark', locale: 'zh-CN' | 'en-US' }
{ type: 'sub2api:chat-revoke' }
// iframe → 父
{ type: 'chat:ready' }
{ type: 'chat:balance-changed' }
{ type: 'chat:navigate', path: '/purchase' | '/keys' }
{ type: 'chat:session-expired' }
```

ready 后父页回 session；每轮回复结束通知余额刷新。navigate 仅接受两个白名单路径。
收到 sub2api 的 `CHAT_SESSION_INVALID` 才报告 session-expired，不把普通 WebUI 401 混为本站失效；父页重新签 Cookie、回 session 后可重试一次。当前前端等待更大 revision 最多 8 秒，流式请求体不重试；重试仍失败时对上游 UI 返回 403，避免其 401 自动登出造成循环，WebUI 自己的 401 仍原样处理。
每次签 Cookie revision 加 1，Cookie 已更新，较大 revision 本身无需重新登录；主题/语言变化必须即时应用。
撤销/换账号清空 `owui:` 本地存储并显示空白、断开 socket。父页也清同源 `owui:` 键，用 `s2a_chat_owner` 标记所属用户；iframe 只写 `owui:` 命名空间，不使用 `s2a_`，当前 fork 前端没有使用 IndexedDB，不清理其他应用（如 Nova）的数据库；以后引入时由 iframe 只清自己的数据库。

## 6. CSP 与 Artifact 沙箱

sub2api 删除上游 CSP / X-Frame-Options，再设置 `X-Frame-Options: SAMEORIGIN`。
默认 CSP（不可给主页面添加 unsafe-inline/eval 脚本豁免）：

```text
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; media-src 'self' blob: data:; worker-src 'self' blob:; frame-src 'self' blob: data:; frame-ancestors 'self'; base-uri 'self'; form-action 'self'
```

图片上传转换（`src/lib/embed/image-upload.ts`）不得用 `fetch(data:)`：未压缩图片复用原 `File`；压缩后的 base64 图片在本地解码为 `File`，MIME 取编码结果；截图用 `canvas.toBlob()`。`FileReader` 失败/中止及转换失败须捕获并显示上传失败提示，不通过开放 `connect-src data:` 绕过。图片压缩仍按用户/服务端尺寸设置，临时聊天仍使用内联图片，不持久化上传。

构建后必须运行 `scripts/embed-postbuild.mjs`：把 index 的内联脚本外置到 `_app/immutable/inline/`，剩余内联脚本/事件属性会使构建失败；不要跳过此步。删除全部 sourcemap。

**只对精确路径** `/_chat/embed/artifact-frame.html` 使用：

```text
default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data:; style-src 'self' 'unsafe-inline' blob: data:; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'none'; frame-src 'none'; worker-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'
```

该页面由 fork `static/embed/artifact-frame.html` 构建到 `build/embed/artifact-frame.html`；**不是** `/_chat/__sub2api/artifact-frame`，不由 sub2api 生成 HTML。
Artifacts、HTML 文件/工具 UI/引用预览均应走它，不用继承主文档 CSP 的 srcdoc。

### Artifact frame 协议（当前实现）

```ts
// 沙箱 → 包含它的 WebUI 页面
{ protocol: 'sub2api-artifact', type: 'ready' }
// WebUI → 沙箱（每个页面只接受一次，内容更新重建 iframe）
{ protocol: 'sub2api-artifact', type: 'render', html: string, scripts: boolean, autoHeight: boolean }
// 沙箱 → WebUI（autoHeight=true）
{ type: 'iframe:height', height: number }
```

`iframe sandbox` 必须含 loader 所需的 `allow-scripts`，**不含 `allow-same-origin` 或顶层导航权限**。
`src/lib/embed/artifact.ts` 会剥掉这些危险标志；`scripts=false` 会再加 `script-src 'none'` 限制内容脚本。
沙箱为不透明源：父 → 沙箱的 targetOrigin 只能用 `'*'`，沙箱校验 `event.source === window.parent`；WebUI 检查 `event.source === iframe.contentWindow`，不能把其 origin 当成站点同源。
页面拒绝在非沙箱/顶层窗口执行 render。高度消息必须验证来源及数值后使用，不信任 HTML 产生的业务指令。
此策略隔离本站 Cookie/存储并禁止 fetch/XHR/WS、嵌套 frame、worker、表单；它不是通用任意脚本虚拟机，不能声称消除全部导航/浏览器资源滥用风险。不要扩大沙箱权限。

## 7. 镜像与环境变量

镜像：`ghcr.io/qlqqs/open-webui:custom-latest`，或回滚使用 `custom-<7位SHA>`。只构建 linux/amd64。
`docker/sub2api-embed.Dockerfile` 三阶段：Node 22 前端、Python 3.12 slim 依赖 venv、Python slim 运行时。
运行 UID/GID `1000:1000`，单 worker，SQLite 数据目录 `/app/backend/data`；绑定宿主目录时须预先授予 UID 1000 写权限。
镜像不带 Node、CUDA、Ollama、embedding/whisper 模型或预下载 tiktoken 编码，不执行 pyodide:fetch。

| 变量 | 镜像默认 / 部署要求 | 来源 |
|---|---|---|
| `S2A_EMBED_MODE` | `1` | contract G |
| `S2A_GATEWAY_URL` | `http://sub2api:8080` | contract G；源码本身无默认 |
| `S2A_TRUSTED_PROXY_CIDRS` | 空，拒绝所有非静态来源；部署必填真实对话网段，宜收紧到 sub2api `/32` | contract G / 阶段 1 |
| `S2A_HIDE_BRANDING` | `0`，公开镜像保留品牌 | contract G / PRD 许可证约束 |
| `S2A_NATIVE_WEB_SEARCH` | `true` | contract G |
| `S2A_BUILTIN_TOOL_CATEGORIES` | `time,user_input,files,chats,notes,tasks,calendar,image_generation` | 更新后的 contract G |
| `S2A_SLIM_DOC_LOADERS` / `S2A_IMAGE_MAX_N` | `true` / `4` | contract G |
| `S2A_HIDDEN_CHAT_MODELS` | `^codex-auto-review\|^gpt-reserve\|gpt-image\|dall-?e\|imagen\|^grok-.*image\|seedream\|flux` | 不区分大小写的正则，以 `\|` 表示或；覆盖整个默认规则，空串关闭过滤；仅隐藏对话列表 |
| `WEBUI_SECRET_KEY` | 镜像不设，部署注入稳定随机秘密 | 阶段 1 |
| `WEBUI_URL` / `CORS_ALLOW_ORIGIN` | 部署设实际 `https://域名/_chat` / `https://域名` | 阶段 1；不要沿用上游宽泛 CORS |
| `DEFAULT_LOCALE` / `UVICORN_WORKERS` | `zh-CN` / `1` | 阶段 1、design §8 |
| `USE_SLIM_DOCKER` / `USE_OLLAMA_DOCKER` / `USE_CUDA_DOCKER` | `true` / `false` / `false` | 上游 slim / design §8 |
| `DATA_DIR` / `FRONTEND_BUILD_DIR` / `HOME` | `/app/backend/data` / `/app/build` / `/home/app` | 非 root 容器路径 |
| `PORT` / `HOST` / `ENV` / `DOCKER` | `8080` / `0.0.0.0` / `prod` / `true` | 上游容器约定；不等于发布宿主端口 |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | 镜像不设；可选白名单代理，NO_PROXY 必须包含网关服务名 | design §4 |

`embed/settings.py::configure_environment()` 在 Python 导入配置前强制安全开关，Dockerfile 显式镜像该清单便于审计。**不能用 compose 或管理员 UI 覆盖强制项**：

```text
强制 true:
OFFLINE_MODE WEBUI_AUTH ENABLE_PASSWORD_AUTH ENABLE_OPENAI_API
BYPASS_EMBEDDING_AND_RETRIEVAL ENABLE_PLUGINS ENABLE_IMAGE_GENERATION
ENABLE_IMAGE_EDIT ENABLE_TITLE_GENERATION

强制 false:
ENABLE_SIGNUP ENABLE_LOGIN_FORM ENABLE_INITIAL_ADMIN_SIGNUP
ENABLE_PASSWORD_CHANGE_FORM ENABLE_MFA ENABLE_PERSISTENT_CONFIG ENABLE_API_KEYS
ENABLE_OAUTH ENABLE_LDAP ENABLE_SCIM ENABLE_VERSION_UPDATE_CHECK ENABLE_OLLAMA_API
ENABLE_DIRECT_CONNECTIONS ENABLE_DIRECT_INTEGRATIONS ENABLE_WEB_SEARCH
ENABLE_COMMUNITY_SHARING ENABLE_USER_WEBHOOKS ENABLE_MEMORIES ENABLE_CODE_EXECUTION
ENABLE_CODE_INTERPRETER ENABLE_CHANNELS ENABLE_AUTOMATIONS ENABLE_SUBAGENTS
ENABLE_ADMIN_CHAT_ACCESS ENABLE_ADMIN_EXPORT ENABLE_ADMIN_ANALYTICS
ENABLE_EVALUATION_ARENA_MODELS ENABLE_MESSAGE_RATING
ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS ENABLE_TAGS_GENERATION
ENABLE_FOLLOW_UP_GENERATION ENABLE_RETRIEVAL_QUERY_GENERATION
ENABLE_IMAGE_PROMPT_GENERATION ENABLE_AUTOCOMPLETE_GENERATION
ENABLE_GOOGLE_DRIVE_INTEGRATION ENABLE_ONEDRIVE_INTEGRATION ENABLE_APPS
ENABLE_BASE_MODELS_CACHE ENABLE_FORWARD_USER_INFO_HEADERS
ENABLE_OPENAI_API_PASSTHROUGH ENABLE_OTEL

以下 USER_PERMISSIONS_ 后缀强制 false:
FEATURES_MEMORIES FEATURES_CODE_INTERPRETER FEATURES_CHANNELS
FEATURES_DIRECT_TOOL_SERVERS FEATURES_API_KEYS FEATURES_AUTOMATIONS FEATURES_WEBHOOKS
CHAT_SHARE CHAT_STT CHAT_TTS CHAT_CALL
WORKSPACE_TOOLS WORKSPACE_TOOLS_IMPORT WORKSPACE_MODELS WORKSPACE_MODELS_IMPORT
WORKSPACE_PROMPTS WORKSPACE_PROMPTS_IMPORT WORKSPACE_KNOWLEDGE WORKSPACE_SKILLS
```

`ENABLE_PASSWORD_AUTH=true` 是可信头登录所必需，不意味着重新开放独立密码入口。
可信 Email/Name/Role 头固定为上述 `X-Sub2API-*`，`DEFAULT_USER_ROLE=user`。
其他强制值：`TERMINAL_SERVER_CONNECTIONS=[]`、`CONTENT_EXTRACTION_ENGINE=''`、`PDF_EXTRACT_IMAGES=false`、`AIOHTTP_CLIENT_ALLOW_REDIRECTS=false`、`OPENAI_API_CONFIGS={}`；生图/编辑 engine 为 `openai`。
`OPENAI_API_BASE_URL(S)` 重新派生为网关 `/v1`；`OLLAMA_BASE_URL` 也设置为网关 origin 以避免原版启动端口探测。`OPENAI_API_KEY(S)` 在代码中强制清空，镜像不写任何 Key。
清除 `LICENSE_KEY`、`CUSTOM_NAME`、可信组头及环境预创建管理员账号。

可覆盖的默认：`IMAGE_GENERATION_MODEL=IMAGE_EDIT_MODEL=gpt-image-2`、`CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS=20`、`RAG_FILE_MAX_SIZE=25`，以及：

```text
RAG_ALLOWED_FILE_EXTENSIONS=pdf,docx,txt,md,csv,html,htm,json,xml,yaml,yml,py,js,ts,tsx,jsx,css,go,rs,c,cpp,h,java,sh,sql,log
```

镜像额外防御默认：`SCARF_NO_ANALYTICS=true`、`DO_NOT_TRACK=true`、`ANONYMIZED_TELEMETRY=false`（上游镜像约定），`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`HF_HUB_DISABLE_TELEMETRY=1`（离线防御）；这些不能替代网络隔离。
`PYTHONUNBUFFERED=1`、`PYTHONDONTWRITEBYTECODE=1` 用于日志/文件写入控制；`BUILD_HASH` 只记录源码版本，不放秘密。

## 8. 部署 compose 示例与出站

以下是**新部署模板**，不是执行或修改任何现有本机项目的命令。先由 sub2api 项目管理专用 `internal: true` 网络，将 sub2api 挂接并给予 `sub2api` 别名；再启动独立 chat 项目。按本机实际网络选择不冲突的 CIDR。

sub2api compose 的片段（合并进现有服务，保留其原有网络）：

```yaml
services:
  sub2api:
    environment:
      CHAT_WEBUI_URL: http://chat-webui:8080
    networks:
      default: {}
      chat:
        ipv4_address: 172.30.240.2
        aliases: [sub2api]
networks:
  chat:
    name: chat-private
    internal: true
    ipam:
      config:
        - subnet: 172.30.240.0/24
```

独立的 chat `compose.yml`：

```yaml
name: chat-workbench
services:
  webui:
    image: ghcr.io/qlqqs/open-webui:custom-latest
    restart: unless-stopped
    user: "1000:1000"
    networks:
      chat:
        aliases: [chat-webui]
    # 无 ports、host 网络、Docker socket，也不挂 outbound 网络
    volumes:
      - data:/app/backend/data
    environment:
      WEBUI_SECRET_KEY: ${WEBUI_SECRET_KEY:?set a persistent random secret}
      WEBUI_URL: https://${SITE_HOST:?set the public host}/_chat
      CORS_ALLOW_ORIGIN: https://${SITE_HOST}
      S2A_GATEWAY_URL: http://sub2api:8080
      S2A_TRUSTED_PROXY_CIDRS: 172.30.240.2/32
      S2A_HIDE_BRANDING: ${S2A_HIDE_BRANDING:-0}
      DEFAULT_LOCALE: zh-CN
      UVICORN_WORKERS: "1"
      NO_PROXY: sub2api,localhost,127.0.0.1
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
networks:
  chat:
    name: chat-private
    external: true
volumes:
  data:
```

生成 `.env` 中的稳定 `WEBUI_SECRET_KEY`（例如 `openssl rand -hex 32`，文件权限 600），不得入库、打印到报告、写入构建参数或 Dockerfile。
此示例默认完全无出站；网关的网络访问由 sub2api 负责。

需要可信插件/MCP 出网时，另部署管理员维护的白名单代理：
- 代理双网卡：chat internal + 专用 outbound；WebUI **仍只挂 internal**，不映射端口。
- WebUI 运行时设 `HTTP_PROXY=http://chat-egress:3128`、`HTTPS_PROXY=http://chat-egress:3128`，并设同义的小写代理变量（若插件库需要）；`NO_PROXY`/`no_proxy` 包含实际网关名、localhost、127.0.0.1。
- 默认白名单为空=拒绝全部；限制域名和端口、拒绝 IP 字面量、私网/回环/链路本地解析结果，并在连接时防 DNS rebinding。若代理链转到另一代理，也必须在最终出口执行相同限制。
- 不把任意转发代理当白名单代理；不把宿主构建用代理直接作为生产出站配置。
- 本机 `sub2api-local-chat/egress/egress_proxy.py` 只是测试参考，不是此仓库打包的生产代理。生产配置需独立审计，特别是上游代理模式的 DNS/私网保护。
- 不遵守环境代理的插件会直连失败；不要因此给 WebUI 增加公网网络。
- Functions/Tools 是同进程可信 Python，可读用户 Key，也可能触及进程数据；internal 网络不是任意恶意插件的执行沙箱。

健康检查直接请求容器 `/static/favicon.png`，不带 `/_chat`、不使用 `/health`（后者仍需身份）。镜像探针绕过环境代理访问 loopback。
备份 SQLite 与上传目录应停写或使用一致性备份；升级前备份独立 data 卷。回滚优先关闭 `CHAT_WEBUI_URL`，必要时回到旧 SHA 镜像与匹配数据备份；不要盲目降级已迁移数据库。

## 9. 构建、发布与许可证

```bash
# 完整多阶段构建；构建代理仅通过 Docker 预定义参数传入
# 变量值可能敏感，不要 set -x，也不要写进镜像 ENV。
docker build -f docker/sub2api-embed.Dockerfile -t owui-embed:local \
  --build-arg HTTP_PROXY="${HTTP_PROXY:-${http_proxy:-}}" \
  --build-arg HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}" \
  --build-arg BUILD_HASH="$(git rev-parse HEAD)" .
```

前端等价步骤：`ONNXRUNTIME_NODE_INSTALL_CUDA=skip CYPRESS_INSTALL_BINARY=0 npm ci` → `OWUI_BASE_PATH=/_chat npm run build:embed` → 删除 `build/**/*.map`。
不要运行普通 `npm run build`，它会调用 pyodide:fetch。
`.dockerignore` 排除 node_modules/build/venv、数据库、环境及 `.webui_secret_key`；基础镜像拉取由 Docker daemon 执行，构建参数无法修复 daemon 自身代理设置。

CI `.github/workflows/sub2api-embed-image.yml`：自定义分支 push 或手动触发（仍限制仓库/分支），pytest + codemod 幂等检查 + embed Vitest 后构建，使用 `GITHUB_TOKEN` 推送两个 GHCR tag。只有发布 job 有 packages:write；不需要 Docker Hub、Helm 或 PyPI secrets。首次发布后需仓库管理员确认 GHCR package 的可见性及仓库权限；本阶段不推送或操作远端。

**许可证以本版本根目录 `LICENSE`、`LICENSE_HISTORY`、`LICENSE_NOTICE` 原文为准，以下仅复述项目的许可证约束，不是额外授权：**
- 当前为 Open WebUI License（BSD-3 风格条款加第 4 条品牌要求），**不能标成纯 BSD-3-Clause 或 MIT**。
- 只有任意连续 30 天内直接使用应用的自然人不超过 50 人，或另获预先书面许可/明确允许修改品牌的企业授权，才可修改/隐藏品牌。
- 条款同样覆盖分发；公开源码和镜像默认 `S2A_HIDE_BRANDING=0`。仅符合条件的部署可在自己的 `.env` 设 `1`，超过门槛必须恢复 `0` 或先取得授权。
- 隐藏开关不等于获得授权，不能把小规模自用例外理解为无限制再分发许可；分发边界有疑问时向权利人确认。
- 必须保留版权、免责声明、LICENSE/HISTORY/NOTICE；镜像在 `/app/` 保留三份文件，设置页版权/许可证链接仍保留。不使用终端等企业授权功能。

## 10. 跟进上游

详见 `scripts/rebase-upstream.md`。每 1–2 个月或影响开放功能的高危修复时评估上游 tag，重放集中补丁、重跑 codemod、全量测试与 sub2api 本机 e2e。安全更新也不能跳过信任头、管理员隔离、固定网关、无外网启动、主文档 CSP、Artifact 和账号切换验收。
