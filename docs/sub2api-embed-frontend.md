# sub2api 嵌入模式：前端（fork `sub2api-custom`）

本文件描述 Open WebUI fork 前端为「对话工作台」（sub2api 控制台 `/chat` 内的同源 iframe `/_chat/`）做的改动。
接口约定以 sub2api 仓库 `.trellis/tasks/10-24-chat-openwebui/contract.md` 为准；后端部分见 `docs/sub2api-embed.md`。

## 1. 改动的组织方式

| 类别 | 位置 | 变基时 |
|---|---|---|
| 机械改动（子路径、存储命名空间） | `scripts/embed-codemod.mjs` 生成，散落在约 290 个上游文件 | 在新的上游代码上重跑脚本，不手工解冲突 |
| 嵌入专用代码 | `src/lib/embed/`、`static/embed/`、`scripts/embed-*.mjs`、本文件 | 不与上游冲突 |
| 上游组件里的挂接 | 28 个文件，每处带 `sub2api-embed` 注释 | 手工核对；`git grep -n sub2api-embed -- src` 列出全部 |

- codemod 幂等：`npm run embed:check`（= `node scripts/embed-codemod.mjs --check`）在树已是最新时退出码 0，否则 1。
  PATCHES 表里某条的锚点在新上游中找不到时输出 `WARN MISSING ...`、退出码 2。
- 挂接代码必须「codemod 干净」：属性 `src={…}` / `href={…}` 的表达式以 `withBase(` 开头，代码里不出现裸的 `'/api…'`、`'/static…'` 字符串，否则重跑 codemod 会再改一遍。
- 非嵌入模式（`/api/config` 没有 `sub2api` 字段）下，除子路径与存储前缀外行为与上游一致。

变基流程：取上游新 tag → 在干净的上游树上 `node scripts/embed-codemod.mjs` → 提交「codemod」→ 重放「手写挂接 + 新增文件」提交 → `npm run embed:check`、`npm run test:embed`、构建、e2e。

## 2. codemod 规则（`scripts/embed-codemod.mjs`）

| 规则 | 内容 |
|---|---|
| R1 | `svelte.config.js`：`paths: { base: process.env.OWUI_BASE_PATH ?? '/_chat', relative: false }` |
| R2 | `src/lib/constants.ts`：`WEBUI_BASE_URL = base`（`$app/paths`），约 360 处 API 调用随之带前缀 |
| R3 | `from '$app/navigation'` → `'$lib/embed/navigation'`（覆写 `goto` 补前缀） |
| R4a/b/c | `.svelte` 属性：`href/src/poster/action="/x"` → `"{BASE}/x"`；`href={e}` / `src={e}` → `withBase(e)` |
| R5 | `location.href = '/x'` → `withBase('/x')` |
| R6 | `$page.url.pathname` → `stripBase(...)`（路由判断） |
| R7 | 代码里 `'/api…'`、`'/static…'`、`'/audio…'`、`'/favicon.png'`、`'/user.png'` 等 → `withBase(...)`（排除终端服务器、worker、pyodide 等） |
| R11 | `` `${window.location.origin}/x` `` → 补 `${BASE}` |
| R12 | `history.replaceState/pushState(…, '/x')` → `withBase('/x')` |
| R13 | 用到 `localStorage` / `sessionStorage` 的模块加 `import { localStorage, sessionStorage } from '$lib/embed/storage'`（以同名导入遮蔽全局，读写自动加 `owui:` 前缀） |
| P（精确补丁） | socket.io `io(undefined, { path: withBase('/ws/socket.io') })`；清 `token` Cookie 用 `path=${BASE}`；`MessageInput` / `MarkdownInlineTokens` / `auths/index.ts` 的路径判断；`safeImageUrl` 根相对 URL 补前缀；pyodide / kokoro worker 从脚本 URL 推导前缀；i18next 检测器 `lookupLocalStorage: 'owui:locale'` |
| R9 | `src/app.html`：静态资源 → `%sveltekit.assets%`；删除死代码 `resizeIframe`；`localStorage.theme` → `localStorage['owui:theme']`；插入嵌入启动脚本（`?theme=light|dark` 预置主题；在 iframe 内且未知品牌开关、或缓存 `owui:s2a:hide-branding=1` 时隐藏启动画面 logo） |

## 3. `src/lib/embed/` 模块

| 文件 | 作用 |
|---|---|
| `paths.ts` / `navigation.ts` | `BASE`、`withBase()`、`stripBase()`；`goto` 包装 |
| `storage.ts` | `owui:` 前缀的 Storage Proxy；`clearEmbedStorage(except)` |
| `mode.ts` | `embedConfig` / `embedMode` / `hideBranding`（来自 `/api/config.sub2api`，contract D）；品牌开关缓存 |
| `features.ts` | 前端隐藏表（与后端 `embed/blocklist.py` 成对）：`HIDDEN_FEATURES`、设置页分区白名单、侧栏项、被屏蔽的路由 |
| `bridge.ts` | 父页桥（contract E），含 `chat:session-expired` 续期 |
| `fetch.ts` | 全局 fetch 包装：Key 头、sub2api 401 处理（见 §6） |
| `keys.ts` | 「模型与密钥」：Key 列表 / 选择逻辑 / 一键创建 / 单价（contract C） |
| `errors.ts` | 网关错误 → 中文提示与动作 |
| `theme.ts` / `theme.css` | 深浅色由桥驱动；QxAPI 配色覆盖（只在 `html.s2a-embed` 下生效） |
| `avatar.ts` | 隐藏品牌时把默认模型头像（后端 302 到 Open WebUI logo）换成中性图标 |
| `links.ts` | 引用 / 搜索结果不访问 Google favicon 与搜索链接 |
| `artifact.ts` / `ArtifactFrame.svelte` | Artifact 沙箱页的父侧（§7） |
| `app.ts` | 上游布局调用的入口：`initEmbedApp`、`embedAfterUserSettings`、`embedBrandName`、`embedErrorToast` |
| `i18n.ts` | 嵌入专用文案（zh-CN / en-US），不改上游语言包 |
| `reasoning.ts` / `ReasoningPicker.svelte` | 输入框「思考强度」胶囊（§8） |
| `composer-features.ts` | 输入框「联网搜索」「图片生成」开关的记忆（§8） |
| `KeysSettings.svelte` / `SidebarSettings.svelte` / `LicenseFooter.svelte` / `GatewayErrorHint.svelte` | 组件 |

## 4. 存储

- 所有键写成 `owui:<key>`（含 `token`、`theme`、`locale`、草稿 `chat-input*`、侧栏状态等）；不带前缀的键（控制台的 `auth_token`、`theme`、`s2a_chat_owner` 等）对 Open WebUI 不可见、不会被改动。
- 嵌入专用键也在命名空间内：`owui:s2a:uid`（本地数据属于哪个 Open WebUI 用户）、`owui:s2a:hide-branding`（启动画面用）、`sessionStorage owui:s2a:key-guide-shown`。不使用 `s2a_` 前缀（控制台保留）。
- 同一浏览器换账号：登录用户 ID 与 `owui:s2a:uid` 不同 → 清掉除 `token / theme / locale / 品牌缓存` 以外的全部 `owui:` 键。父页退出 / 换账号时也会直接清 `owui:*`（contract E）。
- 未使用 IndexedDB（同源上 Nova 用 localforage，所以 revoke 时不做全局 IndexedDB 清理）。

## 5. 父页桥（contract E）

- 启动（拿到 `/api/config` 且为嵌入模式）后注册 `message` 监听并发 `{type:'chat:ready'}`。
- 只接受 `event.origin === location.origin && event.source === window.parent`（且确实被嵌在 iframe 里）的消息；向父页发送时 targetOrigin 为本源。
- `sub2api:chat-session`：`theme` / `locale` 与当前不同即时切换（`applyEmbedTheme`、`changeLanguage`）；记录 `revision`。
- `sub2api:chat-revoke`：清 `owui:` 本地存储、断开 socket、整页显示「会话已结束」。
- 发出：`chat:balance-changed`（每轮回复结束或出错，800 ms 去抖）、`chat:navigate`（只允许 `/purchase`、`/keys`）、`chat:session-expired`（§6）。

## 6. 请求头与 sub2api 的 401（`fetch.ts`）

- 在上游自己的 `window.fetch` 覆写之前安装（根布局脚本顶层 `installEmbedFetch()`），所以上游的 401 处理看到的是本层处理后的结果。
- 同源且路径在 `/_chat/` 下的请求加 `X-Sub2API-Key-Id`（对话 Key）与 `X-Sub2API-Image-Key-Id`（生图 Key，设置了才加）；调用方已带同名头时不覆盖。
- 响应 401 且 JSON 为 `{"error":{"code":"CHAT_SESSION_INVALID"}}`（contract B.3，sub2api 的 Cookie 失效）：发 `chat:session-expired`，等父页回更大 `revision` 的 `chat-session`（8 秒），成功则原样重试一次（请求体为流时不重试）。仍失败时把响应改成 403 交给上层，避免上游 401 处理把 Open WebUI 会话登出后在 `/auth` 循环。Open WebUI 自己的 401 原样透传（走上游 `clearExpiredSession`）。

## 7. Artifact 沙箱页（contract F）

页面：`static/embed/artifact-frame.html`（构建后 `build/embed/artifact-frame.html`，浏览器路径 `/_chat/embed/artifact-frame.html`）。
sub2api 对这个精确路径下发独立 CSP（允许内联脚本、`connect-src 'none'`、无外部图片 / 框架）。

使用方：`ArtifactFrame.svelte`，在嵌入模式下替换 4 处 `srcdoc`（`Artifacts.svelte`、`common/FullHeightIframe.svelte`、`chat/FileNav/FilePreview.svelte`、`Citations/CitationModal.svelte`）。

```
<iframe sandbox="allow-scripts [allow-forms] [allow-downloads] [allow-popups]"   ← 永不含 allow-same-origin / allow-top-navigation
        src="/_chat/embed/artifact-frame.html" referrerpolicy="no-referrer">

沙箱页 → 父   { protocol: 'sub2api-artifact', type: 'ready' }                     targetOrigin '*'
父 → 沙箱页   { protocol: 'sub2api-artifact', type: 'render',                      targetOrigin '*'
               html: string,          // 完整文档或片段（已按 config.ui.iframe_csp 注入 meta CSP）
               scripts: boolean,      // false：原请求的 sandbox 不含 allow-scripts → 页面追加 script-src 'none'
               autoHeight: boolean }  // true：内容页上报高度
内容页 → 父   { type: 'iframe:height', height: number }                            targetOrigin '*'（与上游 FullHeightIframe 的高度消息同名）
```

- 沙箱页先检查自己是不透明源（`window.origin === 'null'`）且被嵌套，否则拒绝渲染（防止被同源无沙箱地嵌入后以宽松 CSP 执行内容）。
- 沙箱页只接受 `event.source === window.parent` 的第一条 `render`；渲染方式为 `document.open()/write()/close()`，并把一小段引导脚本插在内容 `<head>` 最前面（上报高度、拦截链接点击，不让 iframe 被导航走）。
- 每个内容版本一个新 iframe（与 `srcdoc` 变化时重新加载的语义一致）；父侧在收到 `ready` 或 iframe `load` 时发送一次 `render`，只认 `event.source === iframe.contentWindow`。
- 内容页的消息（`input:prompt` 等）仍由上游 `Chat.svelte` 的策略处理（来自自身嵌入 iframe 的提示词需用户确认）。
- 结果（Playwright 实测）：内容脚本与内联事件可运行；读 Cookie / localStorage、访问 `parent.location` 均被拒；`fetch` 与外站图片被 CSP 拦截。

另外：
- 嵌入模式下 `settings.iframeSandboxAllowSameOrigin` / `terminalPreviewAllowSameOrigin` 被强制为 false，界面设置里的开关隐藏。
- `Chat.svelte` 的 socket `execute` 事件（让页面执行任意 JS）在嵌入模式下忽略。

## 8. 「模型与密钥」

- 设置页新分区 `sub2api`（替换 Connections；嵌入模式下设置页只保留：通用、界面、键盘、模型与密钥、数据、已归档对话；管理员另有「扩展功能」即工具服务器）。
- 数据：`GET /_chat/__sub2api/keys|groups`、`POST /_chat/__sub2api/keys`、`GET /_chat/__sub2api/model-prices?key_id=`、`GET /_chat/__sub2api/model-reasoning?key_id=&model=…`（contract C）。不出现明文 Key。
- 对话 Key 下拉列出全部 Key，不可用的置灰并写明原因（已禁用 / 已过期 / 额度已用完 / 分组不可用 / 分组不支持对话）；生图 Key 下拉只列 `supports_images` 的 Key，可选「不单独设置」。
- 选择保存到用户设置 `ui.sub2api = {key_id, image_key_id}`（字段级补丁），随后重新拉取模型列表与单价。
- 没有可用 Key 时显示「一键创建」（分组下拉；默认选中不生图的 anthropic 分组，其次 openai，再其次第一个），创建后自动设为对话 Key。
- 进入时没有可用的对话 Key：每个标签页会话自动打开一次该分区，并给出带「去选择」按钮的提示。
- 模型选择器每行显示 `price_text`（预设助手按其 `base_model_id` 取价）。
- 模型列表加载失败（contract D：`/api/models` 返回网关状态码与 `{"detail","s2a_gateway_error":{status,code,message}}`，如余额不足、Key 无效）：嵌入模式下 `getModels` 不再抛出，而是返回空列表并写入 `embedModelsError`（`errors.ts`）；输入框上方与模型下拉的空状态显示与对话错误相同的提示（余额不足 → 去充值，Key 不可用 → 去设置）。下一次成功加载时提示消失。挂接点：`lib/apis/index.ts` `getModels`、`chat/MessageInput.svelte`、`chat/ModelSelector/Selector.svelte`。
- 思考强度（仿 ChatGPT）：输入框模型名右侧的胶囊，未选时显示「思考强度」，选后显示档位名；点开是档位名加横向滑条（左低右高，拖动 / 点击吸附到档位，方向键、Home / End 可调），点档位名旁的「›」切到档位列表（标注「默认」与计费倍率）。档位来自 `GET /_chat/__sub2api/model-reasoning`（按对话 Key 与当前模型列表批量取，同一 Key + 列表不重复请求），没有可选档位的模型不显示胶囊。选择按模型存在 `owui:s2a:reasoning`，发送时作为 `params.reasoning_effort`（预设助手按 `base_model_id`）；已不在可选档位里的旧选择不发送，由网关用默认档。挂接点：`chat/MessageInput.svelte`（胶囊与拉取）、`chat/Chat.svelte`（请求参数）。
- 「联网搜索」「图片生成」：输入框加号右侧两个独立开关（不再放在扩展菜单里），默认都关。打开表示把对应工具交给模型，由模型自行决定是否搜索 / 生图。选择存在 `owui:s2a:features`，新对话、切换对话、换模型、刷新和 Esc 都不会清掉（上游会清）；当前不可用时请求里按关处理，恢复可用后回到记住的值。挂接点：`chat/MessageInput.svelte`（按钮与同步）、`chat/MessageInput/IntegrationsMenu.svelte`（嵌入模式下菜单不含这两项）。
- 生图可用性（PRD R5.6）：有可用生图 Key，或对话 Key 本身支持生图时「图片生成」可点；否则按钮显示为虚线，悬停提示需要支持生图的 Key，点击打开「模型与密钥」。

## 9. 隐藏与关闭（`features.ts` + 挂接点）

| 项 | 挂接点 |
|---|---|
| 头像菜单 → 「设置」按钮（管理员另有「插件与工具」→ `/admin/functions`） | `layout/Sidebar.svelte`（两处 UserMenu） |
| 侧栏只留笔记、日历、工作空间（工作空间仍按上游权限只给管理员） | `Sidebar.svelte` `pinnedItems` / `isMenuItemVisible` |
| 设置页分区白名单 | `chat/SettingsModal.svelte` |
| 主题、语言选择 | `chat/Settings/General.svelte` |
| `iframeSandboxAllowSameOrigin` 开关 | `common/InterfaceSettings.svelte` |
| Changelog、横幅（不请求 banners 接口） | `routes/(app)/+layout.svelte` |
| 麦克风、语音通话（管理员也隐藏） | `chat/MessageInput.svelte` |
| 朗读、点赞 / 点踩 | `chat/Messages/ResponseMessage.svelte` |
| 分享 | `layout/Navbar/Menu.svelte` |
| 工作空间的知识库、技能 | `routes/(app)/workspace/+layout.svelte` |
| 管理后台只留函数 + 工具 + 工具服务器 | `routes/(app)/admin/+layout.svelte`、`admin/+page.svelte`、`admin/Settings/Integrations.svelte`（隐藏终端、外部知识库、直连开关） |
| 被屏蔽功能的路由回到 `/` | `routes/(app)/+layout.svelte` + `features.ts` `EMBED_BLOCKED_ROUTES` |
| 自动登录页不显示「正在登录 Open WebUI」 | `routes/auth/+page.svelte` |
| 隐藏品牌时首页输入框下方的「名称 ‧ v版本号」整行 | `chat/Suggestions.svelte` |
| Google favicon / 搜索链接 | `Messages/Citations.svelte`（只改 `src`，LICENSE 注释的 `/favicon.png` 回退保留）、`ResponseMessage/WebSearchResults.svelte` |
| OSM 瓦片 | `common/Valves/MapSelector.svelte` |
| 频道、代码解释器、更新提示、新手引导、记忆、语音权限 | 由后端配置关闭（`/api/config` 与用户权限），前端沿用上游判断 |

## 10. 主题与品牌

- `theme.css`：`html.s2a-embed` 下覆盖 `--color-gray-*`（浅色 50–950、深色单独一套）与 `--color-blue-*`，侧栏改为与控制台一致的平铺底色 + 1px 线，主按钮黑白反转改为主色，输入卡片去阴影。
- 深浅色只由父页的 `chat-session.theme` 决定；嵌入模式下去掉上游在深色时写入的内联灰阶。
- `hide_branding=true`（部署 `S2A_HIDE_BRANDING=1`，须满足 LICENSE 例外：30 天内 ≤ 50 名用户）：
  - 页面标题与 `WEBUI_NAME` 显示「对话」；侧栏 logo / 名称隐藏（CSS）；启动画面不显示 logo；默认模型头像与通知 logo 换成 `static/embed/model-avatar.svg`；
  - 版权声明与 LICENSE 链接以小字留在设置页底部（`LicenseFooter.svelte`）。
- 新增文案在 `src/lib/embed/i18n.ts`（zh-CN / en-US），不改上游语言包。

## 11. 错误提示

`errors.ts` 按 sub2api 网关的错误码 / 文案映射：余额不足（「去充值」→ `chat:navigate /purchase`）、Key 额度用完（→ `/keys`）、Key 无效 / 禁用 / 过期 / 未选择（→「模型与密钥」）、生图 Key、内容审核（保留网关自带的中文提示）、用量上限、限流 / 并发、上游不可用、模型不可用、会话失效。
回复下方的错误块（`Messages/Error.svelte`）与错误 toast（`Chat.svelte`）都用这套映射；原始信息折叠在「原始信息」里。

## 12. 构建与测试

```bash
npm ci   # ONNXRUNTIME_NODE_INSTALL_CUDA=skip CYPRESS_INSTALL_BINARY=0
npm run embed:check                         # codemod 已应用且幂等
npm run test:embed                          # vitest：src/lib/embed
NODE_OPTIONS=--max-old-space-size=8192 npm run build:embed   # crypto:verify + vite build + embed-postbuild
```

- `build:embed` 不跑 `pyodide:fetch`（代码解释器在嵌入模式关闭）。
- `embed-postbuild.mjs` 把 `build/index.html` 的内联脚本写到 `build/_app/immutable/inline/<hash>.js`，页面 CSP 可为 `script-src 'self'`；仍有内联脚本或内联事件处理器时退出码非 0。
- 子路径可用 `OWUI_BASE_PATH` 改（构建与 postbuild 都读它）；`OWUI_BASE_PATH=''` 构建出的产物按根路径服务。
