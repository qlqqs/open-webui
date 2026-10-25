# sub2api-embed 补丁集：跟进上游与回滚

本文件是维护操作手册，不是自动执行脚本。所有 Git 写操作、推送和部署需维护者另行确认；不要在其他代理仍修改的工作区变基。本阶段没有执行以下变基/提交/推送操作。

## 1. 补丁划分

保持四类可审阅提交，提交说明使用 `sub2api-embed:` 前缀：

1. **后端 embed**：`backend/open_webui/embed/`、对应测试、少量路由/鉴权/启动挂接；包括管理员个人资源隔离、固定网关与工具服务器持久化。
2. **前端手写**：`src/lib/embed/`、`static/embed/`、桥接/功能控制/品牌/主题/Key 设置挂接，以及 codemod、postbuild 脚本本身与测试。
3. **codemod 生成**：仅机械路径、导航、存储等改写；单独提交，不和业务逻辑混合。变基时按新上游重新生成，不机械复用大量已过时的 diff。
4. **镜像与文档**：`docker/`、`.dockerignore`、Custom Image workflow、契约与本手册。许可证文件不可删除或改写成别的许可证。

有交叉文件时按 hunk 划分。记录旧上游 tag、patch 提交列表和生成规则版本；更新后的默认工具类别必须含 `image_generation`。

## 2. 准备与取 tag

- 确认工作区干净、没有并发代理、测试环境不被占用；若有未提交改动，先协调其作者保存，**不要自动 stash/reset/checkout 覆盖**。
- 记录 `git rev-parse HEAD`、`git status --short`、`git remote -v`、旧基线 tag；备份数据卷和正在使用的镜像 SHA/digest。
- 阅读目标版本 release notes、安全通告与 LICENSE/NOTICE/HISTORY 差异；重新核查当前开放功能及新路由，不能假定 blocklist 自动覆盖新增入口。
- remote URL 必须先核实。若还没有 `upstream`，由维护者添加指向 Open WebUI 官方仓库的 remote；不要覆盖已有 remote。

```bash
git fetch upstream --tags
# 人工选择并核实具体 tag，不使用含义漂移的 main/latest 作为基线
git show <目标tag>:LICENSE
git diff <旧基线tag> <目标tag> -- backend/start.sh backend/requirements-slim.txt \
  package.json package-lock.json svelte.config.js .github/workflows
```

## 3. 重放补丁、重跑 codemod

推荐在新的独立 worktree/临时维护分支重建，旧分支原样保留以便比较；以下占位参数需维护者替换。

```bash
git worktree add -b <维护分支> <新worktree目录> <目标tag>
cd <新worktree目录>
git cherry-pick <后端embed提交...>
git cherry-pick <前端手写提交...>
# 跳过旧“codemod 生成”提交，在新上游上重新运行规则
node scripts/embed-codemod.mjs --dry
node scripts/embed-codemod.mjs
node scripts/embed-codemod.mjs --check
# 审阅生成 diff，再由维护者单独保存生成提交
git cherry-pick <镜像与文档提交...>
```

若前端手写补丁以已生成的树为上下文，按 `docs/sub2api-embed-frontend.md` 先移植 codemod 脚本并在新上游运行，再重放手写挂接；之后仍重跑 codemod/--check，保证最终树幂等。这是同一流程的依赖顺序调整，不重放旧机械 diff。

也可用维护者确认后的 `git rebase --onto <目标tag> <旧基线tag> <维护分支>`，交互式丢弃旧机械生成提交并重生成；**不要盲目重放旧 codemod 结果后直接宣告成功**。
脚本 --check 只验证幂等，不证明新上游所有新增路径都覆盖；需扫描根路径、socket、HTML srcdoc、外部 URL、本地存储和新导航入口。

## 4. 注释与安全挂接核对

```bash
# 后端标准标记（含新增未跟踪文件；不是只依赖 git grep）
rg -n '# sub2api-embed:' backend --glob '*.py' --glob '*.sh'
# 前端既有标记包含空格形式，兼容它；不要为统一注释改动所有业务文件
rg -n 'sub2api[- ]embed' backend src static scripts docker docs .github/workflows \
  --glob '!*.map'
# 单独检查规范连字符标记
rg -n 'sub2api-embed' backend src static scripts docker docs .github/workflows
git diff --check
git diff --stat <目标tag>
git range-diff <旧基线tag>..<旧fork提交> <目标tag>..HEAD
```

在变基前后保存上述清单并 diff；不能仅比较计数。逐条核对消失/迁移的挂接点、新上游替代实现，特别是：
- 原始 TCP peer 与 `--no-proxy-headers`、禁止 root-path、可信头/角色/JWT/socket 邮箱一致性。
- Key 的 HTTP ContextVar、polling/socket 不持有 Key、固定网关 URL 与禁止重定向/携带 Cookie。
- `embed/blocklist.py`、`embed/settings.py` 与前端 features 的一致性；允许 admin 的工具服务器配置不能被误封或不持久化。
- chats/files/notes/calendar 及内置工具、socket/Yjs 的所有者/共享 ACL；不能重新引入上游 admin bypass。
- 原生搜索、Responses/CC、生图 Key 优先、默认工具白名单、全文附件无向量初始化。
- 所有持久存储 `owui:` 前缀、撤销流程、Artifact 不透明源、默认品牌保留、版权 footer。
- Docker 环境显式清单与新 settings 强制项一致，base path、postbuild、许可证打包未遗漏。

## 5. 必跑验证门

在新 worktree 中使用独立 Python 3.12 venv，不复用生产数据；测试只访问本机假网关。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-slim.txt \
  pypdf==6.7.5 docx2txt==0.9 pytest pytest-asyncio
# 去掉宿主代理/真实 Key，防止测试请求意外离开本机
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  -u OPENAI_API_KEY -u OPENAI_API_KEYS \
  FRONTEND_BUILD_DIR="$PWD" .venv/bin/python -m pytest -q backend/open_webui/test/embed
FRONTEND_BUILD_DIR="$PWD" PYTHONPATH=backend .venv/bin/python backend/open_webui/test/embed/smoke/run.py

ONNXRUNTIME_NODE_INSTALL_CUDA=skip CYPRESS_INSTALL_BINARY=0 npm ci --no-audit --no-fund
node scripts/embed-codemod.mjs --check
npm run test:embed
npm run test:frontend -- --run
OWUI_BASE_PATH=/_chat NODE_OPTIONS=--max-old-space-size=8192 npm run build:embed
find build -type f -name '*.map' -delete
```

新版本有上游测试时也运行；原有类型/lint失败应记录基线与新增差异，不得静默跳过。不要使用会自动修改全仓库的 lint/format 作为“只读检查”。

接着用 `docker/sub2api-embed.Dockerfile` 做一次完整构建并在**独立新建 internal 网络**启动验证：随机 WEBUI_SECRET_KEY、不可达假网关、受限 trusted CIDR；确认 UID 1000、静态探针 healthy、`/_app/` 存在、index 无内联脚本、无 sourcemap、无外网失败/下载日志。`/health` 应仍需身份。仅删除自己创建的容器/网络/镜像标签，禁止任何全局 prune。

最后跑 sub2api 本机全链路 e2e（阶段 6 的 chat 驱动，以该阶段实际入口为准，不将一个不存在的 `p9_chat.py` 当成已执行）：
- sub2api 后端/前端测试、单独 chat 驱动及与现有功能的完整回归。
- 两普通用户及管理员交叉读取、登录/换账号/token 刷新/退出/socket 撤销。
- 并发不同 Key、可用模型过滤、真实 IP、费用及余额回刷、标题附加计费。
- 原生搜索引用、两把 Key 生图/编辑、PDF/DOCX 全文/工具模式。
- 主页面 CSP 无脚本豁免、四处 HTML 预览/Artifacts 的交互与恶意 HTML 隔离。
- 空白名单无出网、允许域名可用、非白名单与私网/DNS rebinding/重定向拒绝。
- 深浅主题/语言即时同步、品牌 0/1 两种模式、移动端与刷新子路由。

本机现有 `sub2api-*` 环境须按其维护规则、经授权操作，不在变基手册中自动重启、清库或删除。报告须区分通过、跳过、阻塞，不能把 fork 假网关 smoke 当成 sub2api e2e。

## 6. 发布与回滚

全部门通过后，由维护者审阅补丁及报告、确认提交/推送；CI 发布 `custom-<7位SHA>` 和 `custom-latest`，再另行批准生产部署。禁止为了变基自动强推共享分支。
部署前核查存储、网段、代理白名单、许可证人数条件；保留上一个 SHA/digest 与数据库备份。
异常时先关闭 `CHAT_WEBUI_URL` 以隔离工作台，不影响主站；旧镜像必须配套兼容数据库，迁移后必要时恢复备份，而非只降镜像。
