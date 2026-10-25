// sub2api embed: postMessage bridge between the console page (/chat) and this iframe (contract E).
//
//   parent → iframe  { type: 'sub2api:chat-session', revision, theme: 'light'|'dark', locale }
//                    { type: 'sub2api:chat-revoke' }
//   iframe → parent  { type: 'chat:ready' } | { type: 'chat:balance-changed' }
//                    { type: 'chat:navigate', path: '/purchase' | '/keys' }
//                    { type: 'chat:session-expired' }   (sub2api 401 CHAT_SESSION_INVALID, see fetch.ts)
//
// Incoming messages are accepted only when `event.origin === location.origin` and
// `event.source === window.parent` (and we really are framed). Outgoing messages are posted with
// the exact origin as targetOrigin.
import { writable, type Writable } from 'svelte/store';

export type ChatTheme = 'light' | 'dark';
export type ChatLocale = 'zh-CN' | 'en-US';

export type SessionMessage = {
	type: 'sub2api:chat-session';
	revision: number;
	theme: ChatTheme;
	locale: ChatLocale;
};
export type RevokeMessage = { type: 'sub2api:chat-revoke' };
export type ParentMessage = SessionMessage | RevokeMessage;

export type ChildMessage =
	| { type: 'chat:ready' }
	| { type: 'chat:balance-changed' }
	| { type: 'chat:navigate'; path: NavigatePath }
	| { type: 'chat:session-expired' };

export const NAVIGATE_PATHS = ['/purchase', '/keys'] as const;
export type NavigatePath = (typeof NAVIGATE_PATHS)[number];

type BridgeWindow = Pick<Window, 'addEventListener' | 'removeEventListener'> & {
	location: { origin: string };
	parent: { postMessage: (message: unknown, targetOrigin: string) => void } | Window;
	self?: unknown;
};

export const isFramed = (win: BridgeWindow): boolean => win.parent !== (win as unknown);

/** Origin + source check for messages from the console page. */
export function isTrustedParentEvent(
	event: Pick<MessageEvent, 'origin' | 'source'>,
	win: BridgeWindow
): boolean {
	return isFramed(win) && event.origin === win.location.origin && event.source === win.parent;
}

/** Validate the shape of a parent message; null when unknown / malformed. */
export function parseParentMessage(data: unknown): ParentMessage | null {
	if (!data || typeof data !== 'object') return null;
	const d = data as Record<string, unknown>;
	if (d.type === 'sub2api:chat-revoke') return { type: 'sub2api:chat-revoke' };
	if (d.type === 'sub2api:chat-session') {
		const theme = d.theme === 'dark' ? 'dark' : d.theme === 'light' ? 'light' : null;
		const locale = d.locale === 'en-US' ? 'en-US' : d.locale === 'zh-CN' ? 'zh-CN' : null;
		const revision = typeof d.revision === 'number' && Number.isFinite(d.revision) ? d.revision : 0;
		if (!theme || !locale) return null;
		return { type: 'sub2api:chat-session', revision, theme, locale };
	}
	return null;
}

export const isNavigatePath = (path: unknown): path is NavigatePath =>
	typeof path === 'string' && (NAVIGATE_PATHS as readonly string[]).includes(path);

export type BridgeHandlers = {
	onSession: (message: SessionMessage) => void;
	onRevoke: () => void;
};

export type Bridge = {
	stop: () => void;
	post: (message: ChildMessage) => boolean;
	balanceChanged: () => void;
	navigate: (path: string) => boolean;
	revision: () => number;
	/** resolves true on the next chat-session with a newer revision, false on timeout */
	waitForSession: (afterRevision: number, timeoutMs: number) => Promise<boolean>;
};

/** Start listening; posts `chat:ready` immediately. */
export function createBridge(
	win: BridgeWindow,
	handlers: BridgeHandlers,
	{ balanceDebounceMs = 800 }: { balanceDebounceMs?: number } = {}
): Bridge {
	let lastRevision = -1;
	let balanceTimer: ReturnType<typeof setTimeout> | null = null;
	const waiters = new Set<{ after: number; resolve: (ok: boolean) => void }>();

	const post = (message: ChildMessage): boolean => {
		if (!isFramed(win)) return false;
		try {
			(win.parent as Window).postMessage(message, win.location.origin);
			return true;
		} catch {
			return false;
		}
	};

	const onMessage = (event: MessageEvent) => {
		if (!isTrustedParentEvent(event, win)) return;
		const message = parseParentMessage(event.data);
		if (!message) return;
		if (message.type === 'sub2api:chat-revoke') {
			handlers.onRevoke();
			return;
		}
		lastRevision = Math.max(lastRevision, message.revision);
		handlers.onSession(message);
		for (const w of [...waiters]) {
			if (message.revision > w.after) {
				waiters.delete(w);
				w.resolve(true);
			}
		}
	};

	win.addEventListener('message', onMessage as EventListener);
	post({ type: 'chat:ready' });

	return {
		stop: () => {
			win.removeEventListener('message', onMessage as EventListener);
			if (balanceTimer) clearTimeout(balanceTimer);
			for (const w of waiters) w.resolve(false);
			waiters.clear();
		},
		post,
		balanceChanged: () => {
			if (balanceTimer) clearTimeout(balanceTimer);
			balanceTimer = setTimeout(() => {
				balanceTimer = null;
				post({ type: 'chat:balance-changed' });
			}, balanceDebounceMs);
		},
		navigate: (path: string) => (isNavigatePath(path) ? post({ type: 'chat:navigate', path }) : false),
		revision: () => lastRevision,
		waitForSession: (afterRevision: number, timeoutMs: number) =>
			new Promise<boolean>((resolve) => {
				const w = {
					after: afterRevision,
					resolve: (ok: boolean) => {
						clearTimeout(timer);
						resolve(ok);
					}
				};
				const timer = setTimeout(() => {
					waiters.delete(w);
					resolve(false);
				}, timeoutMs);
				waiters.add(w);
			})
	};
}

// ---------------------------------------------------------------------------------------------
// app-wide singleton (started from src/routes/+layout.svelte once embed mode is known)

let active: Bridge | null = null;

/** true after `sub2api:chat-revoke`: the layout renders an empty page */
export const chatRevoked: Writable<boolean> = writable(false);

export function startBridge(win: BridgeWindow, handlers: BridgeHandlers): Bridge {
	active?.stop();
	active = createBridge(win, handlers);
	return active;
}

export const stopBridge = () => {
	active?.stop();
	active = null;
};

/** One reply round finished (success or error): ask the console to refresh the balance. */
export const notifyBalanceChanged = () => active?.balanceChanged();

/** Navigate the console (whitelisted paths only). */
export const navigateConsole = (path: string): boolean => active?.navigate(path) ?? false;

let pendingRenewal: Promise<boolean> | null = null;

/**
 * The sub2api session cookie expired: ask the console to re-issue it and wait for the next
 * chat-session (newer revision). Concurrent callers share one round trip.
 */
export function renewSession(timeoutMs = 8000): Promise<boolean> {
	if (!active) return Promise.resolve(false);
	if (pendingRenewal) return pendingRenewal;
	const bridge = active;
	const wait = bridge.waitForSession(bridge.revision(), timeoutMs);
	bridge.post({ type: 'chat:session-expired' });
	pendingRenewal = wait.finally(() => {
		pendingRenewal = null;
	});
	return pendingRenewal;
}
