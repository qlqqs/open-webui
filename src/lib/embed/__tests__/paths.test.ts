import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/paths', () => ({ base: '/_chat' }));
const kitGoto = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...a: unknown[]) => kitGoto(...a), invalidate: vi.fn() }));

import { BASE, stripBase, withBase } from '../paths';
import { goto } from '../navigation';

describe('withBase', () => {
	it('prefixes root-relative URLs once', () => {
		expect(BASE).toBe('/_chat');
		expect(withBase('/')).toBe('/_chat/');
		expect(withBase('/api/v1/files/1/content')).toBe('/_chat/api/v1/files/1/content');
		expect(withBase(withBase('/c/1'))).toBe('/_chat/c/1');
		expect(withBase('/_chat')).toBe('/_chat');
		expect(withBase('/_chat?x=1')).toBe('/_chat?x=1');
	});

	it('leaves other values alone', () => {
		expect(withBase('https://example.com/x')).toBe('https://example.com/x');
		expect(withBase('//cdn.example.com/x')).toBe('//cdn.example.com/x');
		expect(withBase('data:image/png;base64,AA')).toBe('data:image/png;base64,AA');
		expect(withBase('#anchor')).toBe('#anchor');
		expect(withBase('relative/path')).toBe('relative/path');
		expect(withBase(undefined)).toBeUndefined();
		expect(withBase(null)).toBeNull();
		// a different prefix that merely starts with the base is not the base
		expect(withBase('/_chatter')).toBe('/_chat/_chatter');
	});
});

describe('stripBase', () => {
	it('removes the base for route comparisons', () => {
		expect(stripBase('/_chat')).toBe('/');
		expect(stripBase('/_chat/')).toBe('/');
		expect(stripBase('/_chat/c/123')).toBe('/c/123');
		expect(stripBase('/c/123')).toBe('/c/123');
		expect(stripBase('/_chatter/x')).toBe('/_chatter/x');
	});
});

describe('goto wrapper', () => {
	it('adds the base to string targets and forwards options', async () => {
		await goto('/c/1', { replaceState: true });
		expect(kitGoto).toHaveBeenLastCalledWith('/_chat/c/1', { replaceState: true });
		await goto('/_chat/notes');
		expect(kitGoto).toHaveBeenLastCalledWith('/_chat/notes', undefined);
		const url = new URL('http://x/_chat/a');
		await goto(url);
		expect(kitGoto).toHaveBeenLastCalledWith(url, undefined);
	});
});
