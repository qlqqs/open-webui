import { beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryStorage } from './memoryStorage';

// the module proxies resolve globalThis.localStorage lazily (first access)
const local = new MemoryStorage();
const session = new MemoryStorage();

beforeAll(() => {
	vi.stubGlobal('localStorage', local);
	vi.stubGlobal('sessionStorage', session);
});

describe('revoke / account switch cleanup', () => {
	it('clearEmbedStorage removes only owui: keys from both storages', async () => {
		const { clearEmbedStorage, localStorage: ls, sessionStorage: ss } = await import('../storage');
		local.setItem('auth_token', 'console');
		local.setItem('s2a_chat_owner', '1');
		ls.setItem('token', 'owui-jwt');
		ls.setItem('chat-input-x', 'draft');
		ss.setItem('chat-input', 'draft');
		clearEmbedStorage();
		expect(local.getItem('owui:token')).toBeNull();
		expect(local.getItem('owui:chat-input-x')).toBeNull();
		expect(session.getItem('owui:chat-input')).toBeNull();
		expect(local.getItem('auth_token')).toBe('console');
		expect(local.getItem('s2a_chat_owner')).toBe('1');
	});

	it('keeps the listed keys', async () => {
		const { clearEmbedStorage, localStorage: ls } = await import('../storage');
		ls.setItem('token', 't');
		ls.setItem('theme', 'dark');
		ls.setItem('sidebar', 'true');
		clearEmbedStorage(['token', 'theme']);
		expect(ls.getItem('token')).toBe('t');
		expect(ls.getItem('theme')).toBe('dark');
		expect(ls.getItem('sidebar')).toBeNull();
	});
});
