// sub2api embed: app-level wiring. Upstream layouts call these from a few `sub2api-embed` hooks;
// everything is a no-op outside embed mode.
import { get } from 'svelte/store';
import { toast } from 'svelte-sonner';
import { base } from '$app/paths';
import i18next from 'i18next';
import { models, settings, showSettings, socket, user } from '$lib/stores';
import { changeLanguage } from '$lib/i18n';
import { cacheBrandingFlag, isEmbedMode, parseEmbedConfig, type EmbedConfig } from './mode';
import { chatRevoked, startBridge, type SessionMessage } from './bridge';
import { applyEmbedTheme, normalizeInitialTheme } from './theme';
import { clearEmbedStorage, localStorage, sessionStorage } from './storage';
import {
	normalizeSelection,
	refreshKeys,
	refreshModelPrices,
	resolveKeys,
	setKeySelection
} from './keys';
import { startNeutralAvatars, stopNeutralAvatars } from './avatar';
import { translate } from './i18n';
import { mapGatewayError } from './errors';

import { initializeWorkbench } from './workbench-defaults';

const USER_KEY = 's2a:uid';
/** survive an account switch inside the same browser (everything else is per user) */
const KEEP_ON_SWITCH = ['token', 'theme', 'locale', 's2a:hide-branding', USER_KEY];

let started = false;

function onSession(message: SessionMessage) {
	applyEmbedTheme(message.theme);
	if (i18next.language !== message.locale) changeLanguage(message.locale);
}

function onRevoke() {
	clearEmbedStorage();
	chatRevoked.set(true);
	try {
		get(socket)?.disconnect();
	} catch {
		// ignore
	}
	stopNeutralAvatars();
}

/** R3.2: local drafts / view state of a previous account must not leak to the next one. */
export function partitionStorageForUser(userId: string | undefined | null): boolean {
	if (!userId) return false;
	const previous = localStorage.getItem(USER_KEY);
	let cleared = false;
	if (previous && previous !== userId) {
		clearEmbedStorage(KEEP_ON_SWITCH);
		cleared = true;
	}
	localStorage.setItem(USER_KEY, userId);
	return cleared;
}

/**
 * Root layout, right after `/api/config` is loaded. Returns the embed config (null outside embed
 * mode) so the caller can adjust the brand name.
 */
export function initEmbedApp(backendConfig: unknown): EmbedConfig | null {
	const e = parseEmbedConfig(backendConfig);
	cacheBrandingFlag(e);
	if (!e || started || typeof window === 'undefined') return e;
	started = true;

	normalizeInitialTheme();
	settings.subscribe((s) => {
		const ui = (s ?? {}) as Record<string, unknown>;
		setKeySelection(ui.sub2api);
		// previews never run same-origin inside the console (design §5.1)
		if (ui.iframeSandboxAllowSameOrigin || ui.terminalPreviewAllowSameOrigin) {
			settings.update((v) => ({
				...v,
				iframeSandboxAllowSameOrigin: false,
				terminalPreviewAllowSameOrigin: false
			}));
		}
	});
	// The embed backend refuses socket handshakes without a token (no anonymous sockets) and
	// socket.io does not retry after a server-side refusal: (re)connect once signed in.
	let retries = 0;
	const reconnectSocket = () => {
		const s = get(socket);
		if (!s || s.active || !get(user) || !localStorage.getItem('token') || retries >= 5) return;
		retries += 1;
		s.connect();
	};
	user.subscribe((u) => {
		partitionStorageForUser(u?.id);
		retries = 0;
		if (u) reconnectSocket();
	});
	let watched: unknown = null;
	socket.subscribe((s) => {
		if (!s || s === watched) return;
		watched = s;
		s.on('connect', () => (retries = 0));
		s.on('connect_error', () => setTimeout(reconnectSocket, 500 * (retries + 1)));
	});
	if (e.hide_branding) {
		startNeutralAvatars(base, (id) => (get(models) ?? []).find((m) => m?.id === id));
	}
	startBridge(window, { onSession, onRevoke });
	return e;
}

/** Name shown in titles: upstream name, or a neutral word when branding is hidden. */
export function embedBrandName(backendConfig: unknown, upstreamName: string): string {
	const e = parseEmbedConfig(backendConfig);
	return e?.hide_branding ? translate(i18next.language, 'brand.name') : upstreamName;
}

const GUIDED_KEY = 's2a:key-guide-shown';

/**
 * (app) layout, after the user settings and models are loaded: fetch the key list, load prices and
 * guide the user to 「模型与密钥」 when no usable chat key is selected (PRD R5.5).
 */
export async function embedAfterUserSettings(): Promise<void> {
	if (!isEmbedMode()) return;
	const keys = await refreshKeys();
	if (keys) {
		try {
			await initializeWorkbench(keys);
		} catch {
			toast.error(translate(i18next.language, 'defaults.saveFailed'));
		}
	}
	const raw = (get(settings) as Record<string, unknown> | undefined)?.sub2api;
	const resolved = resolveKeys(keys ?? [], raw);
	refreshModelPrices(resolved.chatKey?.id ?? normalizeSelection(raw).key_id);
	if (keys === null || !resolved.needsSetup) return;
	const lang = i18next.language;
	toast.info(translate(lang, 'guide.body'), {
		id: 's2a-key-guide',
		duration: 15000,
		action: {
			label: translate(lang, 'guide.action'),
			onClick: () => showSettings.set('sub2api')
		}
	});
	if (!sessionStorage.getItem(GUIDED_KEY)) {
		sessionStorage.setItem(GUIDED_KEY, '1');
		showSettings.set('sub2api');
	}
}

/** Text for toasts: the Chinese hint for known gateway errors, otherwise upstream's text. */
export function embedErrorToast(error: unknown, fallback: string): string {
	if (!isEmbedMode()) return fallback;
	const mapped = mapGatewayError(error) ?? mapGatewayError(fallback);
	if (!mapped) return fallback;
	return mapped.original || translate(i18next.language, mapped.messageKey);
}
