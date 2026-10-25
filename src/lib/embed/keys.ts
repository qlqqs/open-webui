// sub2api embed: 「模型与密钥」 — key list / selection / one-click create / prices (contract C) and the
// per-request key headers (contract A).
//
// The selected key IDs live in the Open WebUI user settings `ui.sub2api = {key_id, image_key_id}`
// (server-side, per user). The browser only ever sees key IDs; sub2api swaps them for the secret
// when it forwards `/_chat/*` to Open WebUI.
import { derived, get, writable, type Readable, type Writable } from 'svelte/store';
import { settings } from '$lib/stores';
import { base } from '$app/paths';

export type Sub2apiKeyReason =
	| ''
	| 'disabled'
	| 'expired'
	| 'quota_exhausted'
	| 'group_unavailable'
	| (string & {});

export type Sub2apiGroup = {
	id: number;
	name: string;
	platform: string;
	description?: string;
	supports_images?: boolean;
};

export type Sub2apiKey = {
	id: number;
	name: string;
	status: string;
	usable: boolean;
	unusable_reason?: Sub2apiKeyReason;
	group: { id: number; name: string; platform: string } | null;
	supports_chat?: boolean;
	supports_images?: boolean;
	quota?: number;
	quota_used?: number;
	expires_at?: string | null;
	masked?: string;
};

export type KeySelection = { key_id?: number | null; image_key_id?: number | null };

export type KeyOption = {
	key: Sub2apiKey;
	/** '' when selectable, otherwise a reason code for the greyed-out entry */
	reason: string;
};

export const KEY_HEADER = 'X-Sub2API-Key-Id';
export const IMAGE_KEY_HEADER = 'X-Sub2API-Image-Key-Id';

// ---------------------------------------------------------------------------------------------
// pure logic (unit-tested)

const toId = (v: unknown): number | null => {
	const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : v;
	return typeof n === 'number' && Number.isInteger(n) && n > 0 ? n : null;
};

/** Normalise `ui.sub2api` from the user settings. */
export function normalizeSelection(raw: unknown): { key_id: number | null; image_key_id: number | null } {
	const r = (raw ?? {}) as KeySelection;
	return { key_id: toId(r.key_id), image_key_id: toId(r.image_key_id) };
}

/** Why a key cannot be used at all ('' = usable). */
export function keyUnusableReason(key: Sub2apiKey): string {
	if (key.usable) return '';
	return key.unusable_reason || 'unknown';
}

/** Why a key cannot be used for chat ('' = selectable). */
export function chatKeyReason(key: Sub2apiKey): string {
	const reason = keyUnusableReason(key);
	if (reason) return reason;
	if (key.supports_chat === false) return 'no_chat';
	return '';
}

const byUsability = (a: KeyOption, b: KeyOption) => Number(!!a.reason) - Number(!!b.reason);

/** Chat key dropdown: every key, unusable ones greyed out with a reason, usable first. */
export function chatKeyOptions(keys: Sub2apiKey[]): KeyOption[] {
	return keys.map((key) => ({ key, reason: chatKeyReason(key) })).sort(byUsability);
}

/** Image key dropdown: only keys whose group supports image generation. */
export function imageKeyOptions(keys: Sub2apiKey[]): KeyOption[] {
	return keys
		.filter((key) => key.supports_images === true)
		.map((key) => ({ key, reason: keyUnusableReason(key) }))
		.sort(byUsability);
}

export type ResolvedKeys = {
	chatKey: Sub2apiKey | null;
	/** reason the selected chat key cannot be used ('' when fine or nothing selected) */
	chatKeyProblem: string;
	/** key that will pay for image generation, null = image generation unavailable */
	imageKey: Sub2apiKey | null;
	imageVia: 'image' | 'chat' | null;
	/** no usable chat key selected → guide the user to 「模型与密钥」 */
	needsSetup: boolean;
};

export function resolveKeys(keys: Sub2apiKey[], raw: unknown): ResolvedKeys {
	const sel = normalizeSelection(raw);
	const chat = sel.key_id !== null ? (keys.find((k) => k.id === sel.key_id) ?? null) : null;
	const chatProblem = chat ? chatKeyReason(chat) : sel.key_id !== null ? 'unknown' : '';
	const chatKey = chat && !chatProblem ? chat : null;

	let imageKey: Sub2apiKey | null = null;
	let imageVia: ResolvedKeys['imageVia'] = null;
	const img = sel.image_key_id !== null ? keys.find((k) => k.id === sel.image_key_id) : undefined;
	if (img && img.supports_images === true && !keyUnusableReason(img)) {
		imageKey = img;
		imageVia = 'image';
	} else if (chatKey?.supports_images === true) {
		// no (usable) image key: sub2api injects none and Open WebUI falls back to the chat key
		imageKey = chatKey;
		imageVia = 'chat';
	}
	return { chatKey, chatKeyProblem: chatProblem, imageKey, imageVia, needsSetup: !chatKey };
}

/** Headers added to every same-origin request under the base path. */
export function keyHeaders(raw: unknown): Record<string, string> {
	const sel = normalizeSelection(raw);
	const headers: Record<string, string> = {};
	if (sel.key_id !== null) headers[KEY_HEADER] = String(sel.key_id);
	if (sel.image_key_id !== null) headers[IMAGE_KEY_HEADER] = String(sel.image_key_id);
	return headers;
}

/** True for URLs the key headers may be attached to: same origin and under the base path. */
export function isBaseUrl(url: string | URL, origin: string, basePath: string): boolean {
	let u: URL;
	try {
		u = new URL(String(url), origin);
	} catch {
		return false;
	}
	if (u.origin !== origin) return false;
	if (!basePath) return true;
	return u.pathname === basePath || u.pathname.startsWith(basePath + '/');
}

export type FetchInput = RequestInfo | URL;

/** Return fetch arguments with the key headers added (existing headers win). */
export function addKeyHeaders(
	input: FetchInput,
	init: RequestInit | undefined,
	headers: Record<string, string>,
	origin: string,
	basePath: string
): [FetchInput, RequestInit | undefined] {
	if (!Object.keys(headers).length) return [input, init];
	const url = typeof input === 'string' || input instanceof URL ? input : input.url;
	if (!isBaseUrl(url, origin, basePath)) return [input, init];
	const merged = new Headers(
		init?.headers ?? (typeof input === 'object' && 'headers' in input ? input.headers : undefined)
	);
	for (const [name, value] of Object.entries(headers)) {
		if (!merged.has(name)) merged.set(name, value);
	}
	return [input, { ...(init ?? {}), headers: merged }];
}

/** Default name for a one-click key (unique against existing names). */
export function newKeyName(keys: Sub2apiKey[], baseName: string): string {
	const names = new Set(keys.map((k) => k.name));
	if (!names.has(baseName)) return baseName;
	for (let i = 2; ; i++) if (!names.has(`${baseName}-${i}`)) return `${baseName}-${i}`;
}

/**
 * Default group for one-click create: a chat-only Anthropic group first, then an OpenAI group, then
 * the first one (the list order itself is kept; the user can still pick another group).
 */
export function defaultCreateGroup(groups: Sub2apiGroup[]): Sub2apiGroup | null {
	const platform = (g: Sub2apiGroup) => String(g.platform ?? '').toLowerCase();
	return (
		groups.find((g) => platform(g) === 'anthropic' && g.supports_images !== true) ??
		groups.find((g) => platform(g) === 'openai') ??
		groups[0] ??
		null
	);
}

// ---------------------------------------------------------------------------------------------
// state

let currentSelection: KeySelection = {};

/** Called whenever `$settings.sub2api` changes. */
export function setKeySelection(raw: unknown): void {
	currentSelection = normalizeSelection(raw);
}

export const getKeySelection = () => ({ ...currentSelection });

export const sub2apiKeys: Writable<Sub2apiKey[] | null> = writable(null);
export const sub2apiKeysError: Writable<string | null> = writable(null);
/** model id → price text for the selected chat key */
export const modelPrices: Writable<Record<string, string>> = writable({});
/** picker rows grow to two lines (name + price) while any price is known; rows stay uniform for the virtual list */
export const hasModelPrices: Readable<boolean> = derived(
	modelPrices,
	($p) => Object.keys($p).length > 0
);

/** resolved selection for the current user (null until the key list is loaded) */
export const resolvedKeys: Readable<ResolvedKeys | null> = derived(
	[sub2apiKeys, settings],
	([$keys, $settings]) =>
		$keys === null ? null : resolveKeys($keys, ($settings as Record<string, unknown>)?.sub2api)
);

// ---------------------------------------------------------------------------------------------
// sub2api endpoints (contract C; cookie auth, raw JSON, errors {"error":{"code","message"}})

export const SUB2API_API = `${base}/__sub2api`;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${SUB2API_API}${path}`, {
		credentials: 'same-origin',
		...init,
		headers: { Accept: 'application/json', ...(init?.headers ?? {}) }
	});
	const body = await res.json().catch(() => null);
	if (!res.ok) {
		const message = body?.error?.message ?? body?.detail ?? `HTTP ${res.status}`;
		throw new Error(message);
	}
	return body as T;
}

export const fetchKeys = () => call<{ keys: Sub2apiKey[] }>('/keys').then((r) => r.keys ?? []);
export const fetchGroups = () =>
	call<{ groups: Sub2apiGroup[] }>('/groups').then((r) => r.groups ?? []);
export const createKey = (name: string, groupId: number) =>
	call<{ key: Sub2apiKey }>('/keys', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ name, group_id: groupId })
	}).then((r) => r.key);
export const fetchModelPrices = (keyId: number) =>
	call<{ models: { id: string; price_text: string }[] }>(
		`/model-prices?key_id=${encodeURIComponent(String(keyId))}`
	).then((r) => Object.fromEntries((r.models ?? []).map((m) => [m.id, m.price_text])));

export async function refreshKeys(): Promise<Sub2apiKey[] | null> {
	try {
		const keys = await fetchKeys();
		sub2apiKeys.set(keys);
		sub2apiKeysError.set(null);
		return keys;
	} catch (e) {
		sub2apiKeysError.set(String((e as Error)?.message ?? e));
		if (get(sub2apiKeys) === null) sub2apiKeys.set([]);
		return null;
	}
}

let pricesFor: number | null = null;
export async function refreshModelPrices(keyId: number | null, force = false): Promise<void> {
	if (!force && keyId === pricesFor) return;
	pricesFor = keyId;
	if (keyId === null) {
		modelPrices.set({});
		return;
	}
	try {
		const prices = await fetchModelPrices(keyId);
		if (pricesFor === keyId) modelPrices.set(prices);
	} catch {
		if (pricesFor === keyId) modelPrices.set({});
	}
}
