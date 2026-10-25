import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/paths', () => ({ base: '/_chat' }));

import {
	addKeyHeaders,
	chatKeyOptions,
	imageKeyOptions,
	isBaseUrl,
	keyHeaders,
	newKeyName,
	normalizeSelection,
	resolveKeys,
	defaultCreateGroup,
	type Sub2apiKey
} from '../keys';

const key = (id: number, over: Partial<Sub2apiKey> = {}): Sub2apiKey => ({
	id,
	name: `k${id}`,
	status: 'active',
	usable: true,
	unusable_reason: '',
	group: { id: 1, name: 'Claude', platform: 'anthropic' },
	supports_chat: true,
	supports_images: false,
	quota: 0,
	quota_used: 0,
	expires_at: null,
	...over
});

const KEYS = [
	key(1),
	key(2, { usable: false, status: 'inactive', unusable_reason: 'disabled' }),
	key(3, { group: { id: 2, name: 'OpenAI', platform: 'openai' }, supports_images: true }),
	key(4, { supports_images: true, usable: false, unusable_reason: 'quota_exhausted' }),
	key(5, { supports_chat: false, supports_images: true, group: { id: 3, name: 'Images', platform: 'openai' } })
];

describe('selection', () => {
	it('normalises ui.sub2api', () => {
		expect(normalizeSelection(undefined)).toEqual({ key_id: null, image_key_id: null });
		expect(normalizeSelection({ key_id: '12', image_key_id: 0 })).toEqual({ key_id: 12, image_key_id: null });
		expect(normalizeSelection({ key_id: -1, image_key_id: 3.5 })).toEqual({ key_id: null, image_key_id: null });
	});

	it('greys out unusable chat keys with a reason, usable first', () => {
		const options = chatKeyOptions(KEYS);
		expect(options.map((o) => [o.key.id, o.reason])).toEqual([
			[1, ''],
			[3, ''],
			[2, 'disabled'],
			[4, 'quota_exhausted'],
			[5, 'no_chat']
		]);
	});

	it('lists only image-capable keys for the image key', () => {
		expect(imageKeyOptions(KEYS).map((o) => [o.key.id, o.reason])).toEqual([
			[3, ''],
			[5, ''],
			[4, 'quota_exhausted']
		]);
	});

	it('needs setup without a usable chat key', () => {
		expect(resolveKeys(KEYS, {}).needsSetup).toBe(true);
		expect(resolveKeys(KEYS, { key_id: 2 })).toMatchObject({ needsSetup: true, chatKeyProblem: 'disabled' });
		expect(resolveKeys(KEYS, { key_id: 99 })).toMatchObject({ needsSetup: true, chatKeyProblem: 'unknown' });
		expect(resolveKeys(KEYS, { key_id: 1 })).toMatchObject({ needsSetup: false, chatKeyProblem: '' });
	});

	it('image generation: image key, else chat key if it supports images, else none (R5.6)', () => {
		expect(resolveKeys(KEYS, { key_id: 1 })).toMatchObject({ imageKey: null, imageVia: null });
		expect(resolveKeys(KEYS, { key_id: 3 }).imageVia).toBe('chat');
		const r = resolveKeys(KEYS, { key_id: 1, image_key_id: 5 });
		expect(r.imageKey?.id).toBe(5);
		expect(r.imageVia).toBe('image');
		// unusable image key: sub2api injects none → falls back to the chat key only if it can
		expect(resolveKeys(KEYS, { key_id: 1, image_key_id: 4 }).imageKey).toBeNull();
		expect(resolveKeys(KEYS, { key_id: 3, image_key_id: 4 }).imageVia).toBe('chat');
		// a non-image key stored as image key is ignored
		expect(resolveKeys(KEYS, { key_id: 1, image_key_id: 1 }).imageKey).toBeNull();
	});
});

describe('request headers', () => {
	it('sends key IDs only when selected', () => {
		expect(keyHeaders({})).toEqual({});
		expect(keyHeaders({ key_id: 12 })).toEqual({ 'X-Sub2API-Key-Id': '12' });
		expect(keyHeaders({ key_id: 12, image_key_id: 34 })).toEqual({
			'X-Sub2API-Key-Id': '12',
			'X-Sub2API-Image-Key-Id': '34'
		});
	});

	it('limits headers to same-origin URLs under the base path', () => {
		const o = 'https://site.example';
		expect(isBaseUrl('/_chat/api/chat/completions', o, '/_chat')).toBe(true);
		expect(isBaseUrl('https://site.example/_chat/__sub2api/keys', o, '/_chat')).toBe(true);
		expect(isBaseUrl('/api/v1/keys', o, '/_chat')).toBe(false);
		expect(isBaseUrl('/_chatter/x', o, '/_chat')).toBe(false);
		expect(isBaseUrl('https://evil.example/_chat/api', o, '/_chat')).toBe(false);
	});

	it('merges headers without overriding existing ones', () => {
		const o = 'https://site.example';
		const h = { 'X-Sub2API-Key-Id': '7' };
		const [, init] = addKeyHeaders('/_chat/api/models', { headers: { Authorization: 'Bearer t' } }, h, o, '/_chat');
		const headers = init?.headers as Headers;
		expect(headers.get('authorization')).toBe('Bearer t');
		expect(headers.get('x-sub2api-key-id')).toBe('7');

		const [, init2] = addKeyHeaders('/_chat/api/models', { headers: { 'X-Sub2API-Key-Id': '1' } }, h, o, '/_chat');
		expect((init2?.headers as Headers).get('x-sub2api-key-id')).toBe('1');

		const [i3, init3] = addKeyHeaders('https://other.example/x', undefined, h, o, '/_chat');
		expect(i3).toBe('https://other.example/x');
		expect(init3).toBeUndefined();
	});
});

describe('one-click create', () => {
	it('picks a unique name', () => {
		expect(newKeyName([key(1, { name: '对话' })], '对话')).toBe('对话-2');
		expect(newKeyName([], '对话')).toBe('对话');
	});

	it('defaults to a chat-only anthropic group, then openai, then the first', () => {
		const g = (id: number, platform: string, supports_images = false) => ({ id, name: `g${id}`, platform, supports_images });
		expect(defaultCreateGroup([g(1, 'openai', true), g(2, 'gemini'), g(3, 'anthropic')])?.id).toBe(3);
		expect(defaultCreateGroup([g(1, 'gemini'), g(2, 'anthropic', true), g(3, 'openai', true)])?.id).toBe(3);
		expect(defaultCreateGroup([g(1, 'gemini'), g(2, 'antigravity')])?.id).toBe(1);
		expect(defaultCreateGroup([])).toBeNull();
	});
});
