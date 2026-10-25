import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	createBridge,
	isTrustedParentEvent,
	parseParentMessage,
	renewSession,
	startBridge,
	stopBridge
} from '../bridge';

const ORIGIN = 'https://console.example';

function fakeWindow({ framed = true } = {}) {
	const listeners: ((e: MessageEvent) => void)[] = [];
	const parent = { postMessage: vi.fn() };
	const win: any = {
		location: { origin: ORIGIN },
		addEventListener: (_t: string, fn: (e: MessageEvent) => void) => listeners.push(fn),
		removeEventListener: (_t: string, fn: (e: MessageEvent) => void) => {
			const i = listeners.indexOf(fn);
			if (i >= 0) listeners.splice(i, 1);
		}
	};
	win.parent = framed ? parent : win;
	const dispatch = (data: unknown, { origin = ORIGIN, source = win.parent } = {}) =>
		[...listeners].forEach((fn) => fn({ data, origin, source } as MessageEvent));
	return { win, parent, dispatch, listeners };
}

const session = (revision = 1, theme = 'dark', locale = 'zh-CN') => ({
	type: 'sub2api:chat-session',
	revision,
	theme,
	locale
});

afterEach(() => {
	stopBridge();
	vi.useRealTimers();
});

describe('message validation', () => {
	it('accepts only the same origin from window.parent', () => {
		const { win } = fakeWindow();
		expect(isTrustedParentEvent({ origin: ORIGIN, source: win.parent } as MessageEvent, win)).toBe(true);
		expect(
			isTrustedParentEvent({ origin: 'https://evil.example', source: win.parent } as MessageEvent, win)
		).toBe(false);
		expect(isTrustedParentEvent({ origin: ORIGIN, source: {} } as unknown as MessageEvent, win)).toBe(false);
		expect(isTrustedParentEvent({ origin: ORIGIN, source: null } as MessageEvent, win)).toBe(false);
	});

	it('rejects everything when not framed', () => {
		const { win } = fakeWindow({ framed: false });
		expect(isTrustedParentEvent({ origin: ORIGIN, source: win } as MessageEvent, win)).toBe(false);
	});

	it('parses only well-formed parent messages', () => {
		expect(parseParentMessage(session(3))).toEqual(session(3));
		expect(parseParentMessage({ type: 'sub2api:chat-revoke' })).toEqual({ type: 'sub2api:chat-revoke' });
		expect(parseParentMessage({ ...session(), theme: 'purple' })).toBeNull();
		expect(parseParentMessage({ ...session(), locale: 'fr-FR' })).toBeNull();
		expect(parseParentMessage({ type: 'sub2api:nova-studio-session' })).toBeNull();
		expect(parseParentMessage('sub2api:chat-revoke')).toBeNull();
		expect(parseParentMessage(null)).toBeNull();
	});
});

describe('bridge', () => {
	it('posts chat:ready with the exact origin on start', () => {
		const { win, parent } = fakeWindow();
		createBridge(win, { onSession: vi.fn(), onRevoke: vi.fn() });
		expect(parent.postMessage).toHaveBeenCalledWith({ type: 'chat:ready' }, ORIGIN);
	});

	it('delivers session and revoke only from the trusted parent', () => {
		const { win, dispatch } = fakeWindow();
		const onSession = vi.fn();
		const onRevoke = vi.fn();
		const bridge = createBridge(win, { onSession, onRevoke });

		dispatch(session(1), { origin: 'https://evil.example' });
		dispatch({ type: 'sub2api:chat-revoke' }, { source: {} as any });
		expect(onSession).not.toHaveBeenCalled();
		expect(onRevoke).not.toHaveBeenCalled();

		dispatch(session(2, 'light', 'en-US'));
		expect(onSession).toHaveBeenCalledWith(session(2, 'light', 'en-US'));
		expect(bridge.revision()).toBe(2);

		dispatch({ type: 'sub2api:chat-revoke' });
		expect(onRevoke).toHaveBeenCalledTimes(1);
	});

	it('stop() removes the listener', () => {
		const { win, dispatch, listeners } = fakeWindow();
		const onRevoke = vi.fn();
		const bridge = createBridge(win, { onSession: vi.fn(), onRevoke });
		bridge.stop();
		expect(listeners).toHaveLength(0);
		dispatch({ type: 'sub2api:chat-revoke' });
		expect(onRevoke).not.toHaveBeenCalled();
	});

	it('navigates only to whitelisted console paths', () => {
		const { win, parent } = fakeWindow();
		const bridge = createBridge(win, { onSession: vi.fn(), onRevoke: vi.fn() });
		expect(bridge.navigate('/purchase')).toBe(true);
		expect(parent.postMessage).toHaveBeenLastCalledWith({ type: 'chat:navigate', path: '/purchase' }, ORIGIN);
		expect(bridge.navigate('/keys')).toBe(true);
		expect(bridge.navigate('/admin/users')).toBe(false);
		expect(bridge.navigate('https://evil.example/')).toBe(false);
		expect(parent.postMessage).toHaveBeenCalledTimes(3); // ready + 2 navigations
	});

	it('debounces balance-changed', () => {
		vi.useFakeTimers();
		const { win, parent } = fakeWindow();
		const bridge = createBridge(win, { onSession: vi.fn(), onRevoke: vi.fn() }, { balanceDebounceMs: 500 });
		bridge.balanceChanged();
		bridge.balanceChanged();
		vi.advanceTimersByTime(499);
		expect(parent.postMessage).toHaveBeenCalledTimes(1);
		vi.advanceTimersByTime(1);
		expect(parent.postMessage).toHaveBeenLastCalledWith({ type: 'chat:balance-changed' }, ORIGIN);
		expect(parent.postMessage).toHaveBeenCalledTimes(2);
	});

	it('does not post when not framed', () => {
		const { win, parent } = fakeWindow({ framed: false });
		const bridge = createBridge(win, { onSession: vi.fn(), onRevoke: vi.fn() });
		expect(bridge.navigate('/purchase')).toBe(false);
		expect(parent.postMessage).not.toHaveBeenCalled();
	});
});

describe('session renewal', () => {
	it('posts chat:session-expired and resolves on a newer revision', async () => {
		const { win, parent, dispatch } = fakeWindow();
		startBridge(win, { onSession: vi.fn(), onRevoke: vi.fn() });
		dispatch(session(4));
		const a = renewSession(1000);
		const b = renewSession(1000); // shared round trip
		expect(parent.postMessage).toHaveBeenCalledWith({ type: 'chat:session-expired' }, ORIGIN);
		expect(parent.postMessage.mock.calls.filter((c) => c[0].type === 'chat:session-expired')).toHaveLength(1);
		dispatch(session(4)); // same revision does not count
		dispatch(session(5));
		await expect(a).resolves.toBe(true);
		await expect(b).resolves.toBe(true);
	});

	it('times out when the console does not answer', async () => {
		vi.useFakeTimers();
		const { win } = fakeWindow();
		startBridge(win, { onSession: vi.fn(), onRevoke: vi.fn() });
		const p = renewSession(2000);
		vi.advanceTimersByTime(2000);
		await expect(p).resolves.toBe(false);
	});

	it('resolves false without a bridge', async () => {
		stopBridge();
		await expect(renewSession(10)).resolves.toBe(false);
	});
});
