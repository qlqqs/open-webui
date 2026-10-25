import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/paths', () => ({ base: '/_chat' }));

import { config } from '$lib/stores';
import { createEmbedFetch, isSub2apiSessionError } from '../fetch';
import { setKeySelection } from '../keys';

const ORIGIN = 'https://site.example';
const json = (status: number, body: unknown) =>
	new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const sessionInvalid = () => json(401, { error: { code: 'CHAT_SESSION_INVALID', message: '登录已失效' } });

beforeEach(() => {
	config.set({ sub2api: { embed: true } } as any);
	setKeySelection({ key_id: 7 });
});

describe('sub2api session errors', () => {
	it('tells sub2api 401 from Open WebUI 401', async () => {
		expect(await isSub2apiSessionError(sessionInvalid())).toBe(true);
		expect(await isSub2apiSessionError(json(401, { detail: 'Not authenticated' }))).toBe(false);
		expect(await isSub2apiSessionError(json(403, { error: { code: 'CHAT_SESSION_INVALID' } }))).toBe(false);
	});

	it('renews the session and retries once', async () => {
		const inner = vi.fn().mockResolvedValueOnce(sessionInvalid()).mockResolvedValueOnce(json(200, { ok: 1 }));
		const renew = vi.fn().mockResolvedValue(true);
		const f = createEmbedFetch(inner as any, () => ORIGIN, renew);
		const res = await f('/_chat/api/v1/chats/', { method: 'POST', body: '{}' });
		expect(res.status).toBe(200);
		expect(renew).toHaveBeenCalledTimes(1);
		expect(inner).toHaveBeenCalledTimes(2);
		expect((inner.mock.calls[1][1].headers as Headers).get('x-sub2api-key-id')).toBe('7');
	});

	it('hands a still-invalid session on as 403 so upstream does not sign out', async () => {
		const inner = vi.fn().mockImplementation(async () => sessionInvalid());
		const f = createEmbedFetch(inner as any, () => ORIGIN, vi.fn().mockResolvedValue(false));
		const res = await f('/_chat/api/v1/auths/');
		expect(res.status).toBe(403);
		expect((await res.json()).error.code).toBe('CHAT_SESSION_INVALID');
		expect(inner).toHaveBeenCalledTimes(1);
	});

	it('passes Open WebUI 401 through untouched', async () => {
		const inner = vi.fn().mockResolvedValue(json(401, { detail: 'Not authenticated' }));
		const renew = vi.fn();
		const f = createEmbedFetch(inner as any, () => ORIGIN, renew);
		expect((await f('/_chat/api/v1/auths/')).status).toBe(401);
		expect(renew).not.toHaveBeenCalled();
	});

	it('does nothing outside embed mode or the base path', async () => {
		const inner = vi.fn().mockImplementation(async () => sessionInvalid());
		const renew = vi.fn();
		const f = createEmbedFetch(inner as any, () => ORIGIN, renew);
		expect((await f('/api/v1/auth/me')).status).toBe(401);
		config.set({} as any);
		expect((await f('/_chat/api/v1/auths/')).status).toBe(401);
		expect(renew).not.toHaveBeenCalled();
	});
});
