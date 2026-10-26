// sub2api embed: strings for embed-only UI (zh-CN / en-US). Kept out of the upstream locale files so
// rebasing never conflicts with upstream translation updates.
import { derived, type Readable } from 'svelte/store';
import i18n from '$lib/i18n';

const zhCN = {
	'settings.tab': '模型与密钥',
	'settings.button': '设置',
	'settings.workspace': '工作空间',
	'settings.plugins': '插件与工具',
	'keys.title': '模型与密钥',
	'keys.intro': '对话使用你在本站的 API Key 计费，费用从账户余额扣除。Key 明文不会出现在浏览器中。',
	'keys.chat': '对话 Key',
	'keys.chatHint': '所有对话、标题生成和联网搜索都用这个 Key 计费。',
	'keys.image': '生图 Key（可选）',
	'keys.imageHint': '只列出支持生图的分组。不选时，若对话 Key 支持生图就用对话 Key。',
	'keys.imageNone': '不单独设置',
	'keys.placeholder': '请选择 Key',
	'keys.loading': '正在加载 Key…',
	'keys.loadFailed': '加载 Key 失败：{{error}}',
	'keys.empty': '你还没有可用于对话的 Key。',
	'keys.create': '一键创建',
	'keys.createIn': '在分组「{{group}}」下创建',
	'keys.creating': '正在创建…',
	'keys.created': '已创建 Key「{{name}}」并设为对话 Key',
	'keys.createFailed': '创建 Key 失败：{{error}}',
	'keys.defaultName': '对话',
	'keys.manage': '管理 API 密钥',
	'keys.saved': '已保存',
	'keys.saveFailed': '保存失败：{{error}}',
	'keys.group': '分组：{{group}}',
	'keys.noGroup': '未绑定分组',
	'keys.quota': '额度 ${{used}} / ${{quota}}',
	'keys.expires': '{{date}} 到期',
	'keys.imageReady': '生图：使用「{{name}}」',
	'keys.imageUnavailable': '当前没有可用于生图的 Key，输入框不显示生图开关。',
	'keys.reason.disabled': '已禁用',
	'keys.reason.expired': '已过期',
	'keys.reason.quota_exhausted': '额度已用完',
	'keys.reason.group_unavailable': '分组不可用',
	'keys.reason.no_chat': '分组不支持对话',
	'keys.reason.unknown': '不可用',
	'keys.selectedUnusable': '当前选择的 Key 不可用（{{reason}}），请重新选择。',
	'guide.title': '先选择一个 Key',
	'guide.body': '对话需要使用你的 API Key 计费。请在「模型与密钥」里选择或一键创建一个 Key。',
	'guide.action': '去选择',
	'defaults.unavailable': '默认模型不可用，请选择其他模型',
	'defaults.saveFailed': '默认配置暂不可用，请在「模型与密钥」中配置 Key',
	'image.needKey': '生图需要支持生图的 Key',
	'composer.webSearch': '联网搜索',
	'composer.webSearchHint': '打开后，模型会在需要时自己联网搜索',
	'composer.imageGeneration': '图片生成',
	'composer.imageGenerationHint': '打开后，模型会在需要时自己生成图片，按生图 Key 计费',
	'price.label': '单价',
	'error.session': '登录状态已失效，请刷新页面后重试。',
	'error.balance': '账户余额不足，请充值后再试。',
	'error.keyQuota': '当前 Key 的额度已用完。请在「模型与密钥」中更换 Key，或到 API 密钥页调整额度。',
	'error.key': '当前 Key 不可用（未选择、已禁用、已过期或已删除），请在「模型与密钥」中重新选择。',
	'error.rateLimit': '请求太频繁或并发已达上限，请稍后再试。',
	'error.usageLimit': '已达到用量上限，请稍后再试或更换 Key。',
	'error.moderation': '内容未通过安全审核，请调整输入后再试。',
	'error.unavailable': '模型服务暂时不可用，请稍后再试或更换模型。',
	'error.model': '所选 Key 不能使用这个模型，请更换模型或 Key。',
	'error.imageKey': '生图需要支持生图的 Key，请在「模型与密钥」中设置生图 Key。',
	'error.purchase': '去充值',
	'error.keys': '管理 API 密钥',
	'error.settings': '去设置',
	'error.models': '模型列表加载失败，请稍后重试或检查所选 Key。',
	'error.detail': '原始信息',
	'footer.copyright': '本页面基于 Open WebUI（© Open WebUI 及其贡献者）修改。',
	'footer.license': '许可证',
	'revoked': '会话已结束，请重新打开对话页面。',
	'brand.name': '对话',
	'upload.heic': '暂不支持 HEIC 图片，请先转换为 JPG 或 PNG 再上传。',
	'admin.tools': '工具',
	'admin.toolServers': '工具服务器',
	'reasoning.title': '思考强度',
	'reasoning.slider': '拖动调节思考强度',
	'reasoning.showLevels': '查看全部档位',
	'reasoning.showSlider': '返回滑块',
	'reasoning.default': '默认',
	'reasoning.multiplier': '计费 ×{{n}}',
	'reasoning.level.minimal': '最少',
	'reasoning.level.low': '低',
	'reasoning.level.medium': '中',
	'reasoning.level.high': '高',
	'reasoning.level.xhigh': '超高',
	'reasoning.level.max': '最高'
} as const;

export type EmbedStringKey = keyof typeof zhCN;

const enUS: Record<EmbedStringKey, string> = {
	'settings.tab': 'Models & Keys',
	'settings.button': 'Settings',
	'settings.workspace': 'Workspace',
	'settings.plugins': 'Plugins & Tools',
	'keys.title': 'Models & Keys',
	'keys.intro':
		'Chats are billed to one of your API keys on this site and deducted from your balance. Key secrets never reach the browser.',
	'keys.chat': 'Chat key',
	'keys.chatHint': 'All chats, title generation and web search are billed to this key.',
	'keys.image': 'Image key (optional)',
	'keys.imageHint':
		'Only groups that support image generation are listed. If unset, the chat key is used when it supports images.',
	'keys.imageNone': 'Not set',
	'keys.placeholder': 'Select a key',
	'keys.loading': 'Loading keys…',
	'keys.loadFailed': 'Failed to load keys: {{error}}',
	'keys.empty': 'You have no key that can be used for chat yet.',
	'keys.create': 'Create one',
	'keys.createIn': 'Create in group “{{group}}”',
	'keys.creating': 'Creating…',
	'keys.created': 'Created key “{{name}}” and selected it for chat',
	'keys.createFailed': 'Failed to create key: {{error}}',
	'keys.defaultName': 'Chat',
	'keys.manage': 'Manage API keys',
	'keys.saved': 'Saved',
	'keys.saveFailed': 'Failed to save: {{error}}',
	'keys.group': 'Group: {{group}}',
	'keys.noGroup': 'No group',
	'keys.quota': 'Quota ${{used}} / ${{quota}}',
	'keys.expires': 'Expires {{date}}',
	'keys.imageReady': 'Images: using “{{name}}”',
	'keys.imageUnavailable': 'No key can generate images, so the image toggle is hidden.',
	'keys.reason.disabled': 'Disabled',
	'keys.reason.expired': 'Expired',
	'keys.reason.quota_exhausted': 'Quota used up',
	'keys.reason.group_unavailable': 'Group unavailable',
	'keys.reason.no_chat': 'Group does not support chat',
	'keys.reason.unknown': 'Unavailable',
	'keys.selectedUnusable': 'The selected key cannot be used ({{reason}}). Please choose another.',
	'guide.title': 'Choose a key first',
	'guide.body':
		'Chats are billed to your API key. Select one or create one in “Models & Keys”.',
	'guide.action': 'Choose',
	'defaults.unavailable': 'The default model is unavailable. Please choose another model.',
	'defaults.saveFailed': 'Default settings are unavailable. Please configure a key in Models & Keys.',
	'image.needKey': 'Image generation needs a key that supports images',
	'composer.webSearch': 'Web search',
	'composer.webSearchHint': 'When on, the model searches the web whenever it needs to',
	'composer.imageGeneration': 'Image',
	'composer.imageGenerationHint':
		'When on, the model generates images whenever it needs to (billed to the image key)',
	'price.label': 'Price',
	'error.session': 'Your session has expired. Please reload the page.',
	'error.balance': 'Insufficient balance. Please top up and try again.',
	'error.keyQuota':
		'This key has used up its quota. Pick another key in “Models & Keys” or raise its quota on the API keys page.',
	'error.key':
		'The key is not usable (not selected, disabled, expired or deleted). Please choose one in “Models & Keys”.',
	'error.rateLimit': 'Too many requests or concurrency limit reached. Please try again later.',
	'error.usageLimit': 'Usage limit reached. Try again later or use another key.',
	'error.moderation': 'The content was blocked by moderation. Please rephrase and try again.',
	'error.unavailable':
		'The model service is temporarily unavailable. Try again later or pick another model.',
	'error.model': 'The selected key cannot use this model. Pick another model or key.',
	'error.imageKey': 'Image generation needs an image-capable key. Set one in “Models & Keys”.',
	'error.purchase': 'Top up',
	'error.keys': 'Manage API keys',
	'error.settings': 'Open settings',
	'error.models': 'Could not load the model list. Try again later or check the selected key.',
	'error.detail': 'Details',
	'footer.copyright': 'This page is a modified version of Open WebUI (© Open WebUI contributors).',
	'footer.license': 'License',
	'revoked': 'The session has ended. Please reopen the chat page.',
	'brand.name': 'Chat',
	'upload.heic': 'HEIC images are not supported here. Please convert to JPG or PNG first.',
	'admin.tools': 'Tools',
	'admin.toolServers': 'Tool servers',
	'reasoning.title': 'Thinking',
	'reasoning.slider': 'Drag to adjust thinking effort',
	'reasoning.showLevels': 'Show all levels',
	'reasoning.showSlider': 'Back to slider',
	'reasoning.default': 'Default',
	'reasoning.multiplier': 'Billed ×{{n}}',
	'reasoning.level.minimal': 'Minimal',
	'reasoning.level.low': 'Low',
	'reasoning.level.medium': 'Medium',
	'reasoning.level.high': 'High',
	'reasoning.level.xhigh': 'Extra High',
	'reasoning.level.max': 'Max'
};

const DICTS: Record<string, Record<EmbedStringKey, string>> = { 'zh-CN': zhCN, 'en-US': enUS };

export function embedLocale(language: string | undefined | null): 'zh-CN' | 'en-US' {
	return (language ?? '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US';
}

export function translate(
	language: string | undefined | null,
	key: EmbedStringKey,
	vars: Record<string, string | number> = {}
): string {
	const template = DICTS[embedLocale(language)][key] ?? zhCN[key] ?? key;
	return template.replace(/\{\{(\w+)\}\}/g, (_, name) => String(vars[name] ?? ''));
}

type I18nStore = Readable<{ language?: string }>;

/** `$et('keys.title')` — reactive to language changes. */
type Translator = (key: EmbedStringKey, vars?: Record<string, string | number>) => string;

export const et: Readable<Translator> = derived(
	i18n as unknown as I18nStore,
	($i18n): Translator =>
		(key, vars) =>
			translate($i18n?.language, key, vars)
);
