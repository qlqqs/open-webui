// sub2api embed: map gateway / proxy errors to Chinese hints (PRD R6.2).
//
// Sources of the patterns (sub2api backend): middleware/api_key_auth.go (INVALID_API_KEY,
// API_KEY_DISABLED, API_KEY_EXPIRED "API key 已过期", INSUFFICIENT_BALANCE "Insufficient account
// balance", "API key 额度已用完" / insufficient_quota, USAGE_LIMIT_EXCEEDED),
// handler/concurrency_error_response.go (rate_limit_error, gateway_queue_full,
// gateway_concurrency_limit), content moderation (content_policy_violation, "内容审计…"),
// "No available accounts", and the fork backend's 400 「请选择可用的 Key」.
import { writable, type Writable } from 'svelte/store';
import type { EmbedStringKey } from './i18n';

export type GatewayErrorKind =
	| 'session'
	| 'balance'
	| 'keyQuota'
	| 'key'
	| 'imageKey'
	| 'moderation'
	| 'usageLimit'
	| 'rateLimit'
	| 'unavailable'
	| 'model'
	| 'models';

export type GatewayErrorAction = 'purchase' | 'keys' | 'settings';

export type MappedGatewayError = {
	kind: GatewayErrorKind;
	messageKey: EmbedStringKey;
	action: GatewayErrorAction | null;
	/** message from the gateway when it is already Chinese and more specific (moderation) */
	original: string;
};

const RULES: [GatewayErrorKind, RegExp, GatewayErrorAction | null][] = [
	['session', /CHAT_SESSION_INVALID|登录已失效/, null],
	[
		'balance',
		/INSUFFICIENT_BALANCE|insufficient[ _]?(account[ _])?balance|insufficient[ _]credits|余额不足/i,
		'purchase'
	],
	['keyQuota', /API_KEY_QUOTA_EXHAUSTED|insufficient_quota|额度已用完|quota[ _]exhausted/i, 'keys'],
	[
		'imageKey',
		/(image|生图).{0,40}(key|密钥)|请选择可用的生图\s*Key|does not support image generation/i,
		'settings'
	],
	[
		'key',
		/INVALID_API_KEY|Invalid API key|API_KEY_DISABLED|API key is disabled|API_KEY_EXPIRED|API key 已过期|API key is required|请选择可用的\s*Key|API_KEY_REQUIRED/i,
		'settings'
	],
	['moderation', /content_policy_violation|content moderation|moderation_blocked|内容审计|审核/i, null],
	['usageLimit', /USAGE_LIMIT_EXCEEDED|(daily|weekly|monthly) (usage )?limit/i, null],
	[
		'rateLimit',
		/rate[ _]?limit|too many (pending )?requests|concurrency limit|gateway_queue_full|gateway_concurrency_limit|\b429\b/i,
		null
	],
	[
		'unavailable',
		/No available accounts?|Service temporarily unavailable|upstream_error|overloaded|\b50[23]\b/i,
		null
	],
	[
		'model',
		/model[^\n]{0,60}(not (found|supported|available|allowed)|does not exist)|Model not found|unsupported model/i,
		'settings'
	]
];

const MESSAGE_KEYS: Record<GatewayErrorKind, EmbedStringKey> = {
	session: 'error.session',
	balance: 'error.balance',
	keyQuota: 'error.keyQuota',
	key: 'error.key',
	imageKey: 'error.imageKey',
	moderation: 'error.moderation',
	usageLimit: 'error.usageLimit',
	rateLimit: 'error.rateLimit',
	unavailable: 'error.unavailable',
	model: 'error.model',
	models: 'error.models'
};

const hasCJK = (s: string) => /[一-鿿]/.test(s);

/** Flatten error payloads (string / {detail} / {error:{message,code}} / {message}) into text. */
export function errorText(value: unknown): string {
	if (value === null || value === undefined) return '';
	if (typeof value === 'string') return value;
	if (typeof value !== 'object') return String(value);
	const v = value as Record<string, unknown>;
	const parts: string[] = [];
	for (const key of ['code', 'type', 'message', 'detail', 'content', 's2a_gateway_error']) {
		const item = v[key];
		if (typeof item === 'string') parts.push(item);
		else if (item && typeof item === 'object') parts.push(errorText(item));
	}
	if (v.error !== undefined) parts.push(errorText(v.error));
	if (parts.length) return parts.join(' ');
	try {
		return JSON.stringify(value);
	} catch {
		return String(value);
	}
}

/** Recognise a gateway error; null when the text matches none of the known cases. */
export function mapGatewayError(value: unknown): MappedGatewayError | null {
	const text = errorText(value);
	if (!text) return null;
	for (const [kind, re, action] of RULES) {
		if (re.test(text)) {
			// moderation: the gateway's own (admin-configured, Chinese) block message is more useful
			const original =
				kind === 'moderation' && hasCJK(text)
					? (text.match(/[\u4e00-\u9fff][^"'{}\[\]\n]*/)?.[0].trim() ?? '')
					: '';
			return { kind, messageKey: MESSAGE_KEYS[kind], action, original };
		}
	}
	return null;
}

/** Console paths for actions (contract E navigate whitelist). */
export const ACTION_PATHS: Record<Exclude<GatewayErrorAction, 'settings'>, '/purchase' | '/keys'> =
	{
		purchase: '/purchase',
		keys: '/keys'
	};

/**
 * `/api/models` failed (contract D: gateway status + {"detail", "s2a_gateway_error":{status,code,message}}).
 * Unknown errors still produce a generic hint so the dropdown is never silently empty.
 */
export function mapModelsError(value: unknown): MappedGatewayError {
	const mapped = mapGatewayError(value);
	if (mapped) return mapped;
	const detail = (value as { detail?: unknown } | null)?.detail;
	const original = typeof detail === 'string' && hasCJK(detail) ? detail.trim() : '';
	return { kind: 'models', messageKey: 'error.models', action: null, original };
}

export type ModelsErrorState = { mapped: MappedGatewayError; raw: string } | null;

/** Last `/api/models` failure in embed mode (null after a successful load). */
export const embedModelsError: Writable<ModelsErrorState> = writable(null);

export function setEmbedModelsError(error: unknown): void {
	embedModelsError.set(
		error === null || error === undefined
			? null
			: { mapped: mapModelsError(error), raw: errorText(error) }
	);
}
