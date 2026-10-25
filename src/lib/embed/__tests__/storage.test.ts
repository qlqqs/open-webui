import { describe, expect, it } from 'vitest';
import { createPrefixedStorage, STORAGE_PREFIX } from '../storage';
import { MemoryStorage } from './memoryStorage';

const setup = () => {
	const raw = new MemoryStorage();
	raw.setItem('theme', 'dark'); // sub2api console key
	raw.setItem('auth_token', 'console-jwt');
	const store = createPrefixedStorage(() => raw);
	return { raw, store };
};

describe('prefixed storage', () => {
	it('stores every key under owui:', () => {
		const { raw, store } = setup();
		store.setItem('token', 'abc');
		expect(raw.getItem('owui:token')).toBe('abc');
		expect(raw.getItem('token')).toBeNull();
		expect(STORAGE_PREFIX).toBe('owui:');
	});

	it('never sees or touches the console keys', () => {
		const { raw, store } = setup();
		expect(store.getItem('theme')).toBeNull();
		expect(store.theme).toBeUndefined();
		store.setItem('theme', 'light');
		expect(raw.getItem('theme')).toBe('dark');
		expect(raw.getItem('owui:theme')).toBe('light');
	});

	it('supports property access, delete and in', () => {
		const { raw, store } = setup();
		(store as unknown as Record<string, string>).token = 'x';
		expect(raw.getItem('owui:token')).toBe('x');
		expect(store.token).toBe('x');
		expect('token' in store).toBe(true);
		delete (store as unknown as Record<string, string>).token;
		expect(raw.getItem('owui:token')).toBeNull();
		expect('token' in store).toBe(false);
		expect('getItem' in store).toBe(true);
	});

	it('enumerates and clears only its own keys', () => {
		const { raw, store } = setup();
		store.setItem('a', '1');
		store.setItem('chat-input-1', 'draft');
		expect(Object.keys(store).sort()).toEqual(['a', 'chat-input-1']);
		expect(store.length).toBe(2);
		expect([store.key(0), store.key(1)].sort()).toEqual(['a', 'chat-input-1']);
		expect(Object.keys(store).filter((k) => k.startsWith('chat-input'))).toEqual(['chat-input-1']);
		store.clear();
		expect(store.length).toBe(0);
		expect(raw.getItem('theme')).toBe('dark');
		expect(raw.getItem('auth_token')).toBe('console-jwt');
	});

	it('stringifies values like the real Storage', () => {
		const { store } = setup();
		store.setItem('n', 5 as unknown as string);
		(store as unknown as Record<string, unknown>).flag = true;
		expect(store.getItem('n')).toBe('5');
		expect(store.flag).toBe('true');
	});

	it('degrades to a no-op when storage is unavailable', () => {
		const store = createPrefixedStorage(() => undefined);
		store.setItem('x', '1');
		expect(store.getItem('x')).toBeNull();
		expect(store.length).toBe(0);
		expect(Object.keys(store)).toEqual([]);
	});
});
