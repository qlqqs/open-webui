import { beforeEach, describe, expect, it, vi } from 'vitest';
const testState = await vi.hoisted(async () => {
	const { writable } = await import('svelte/store');
	return {
		settings: writable<Record<string, unknown>>({}),
		models: writable<unknown[]>([]),
		user: writable({ id: 'a' })
	};
});
vi.mock('$lib/stores', () => testState);
vi.mock('$app/paths', () => ({ base: '/_chat' }));
vi.mock('$lib/apis', () => ({ getModels: vi.fn().mockResolvedValue([{ id: 'gpt-6.1-sol' }]) }));
vi.mock('$lib/apis/users', () => ({
	updateUserSettings: vi.fn(async (_token, value) => ({
		ui: { ...value.ui, sub2api_initialized: true }
	}))
}));
vi.mock('../storage', () => ({ localStorage: { token: 'token' } }));
vi.mock('../keys', () => ({
	SUB2API_API: '/_chat/__sub2api',
	setKeySelection: vi.fn(),
	fetchModelReasoning: vi
		.fn()
		.mockResolvedValue({ 'gpt-6.1-sol': { levels: ['low', 'medium', 'high'] } })
}));
vi.mock('svelte-sonner', () => ({ toast: { info: vi.fn() } }));
import { get } from 'svelte/store';
import { updateUserSettings } from '$lib/apis/users';
import {
	defaultWorkbenchKey,
	initializeWorkbench,
	type WorkbenchDefaults
} from '../workbench-defaults';
import type { Sub2apiKey } from '../keys';
const state: WorkbenchDefaults = {
	eligible: true,
	initialized: false,
	group_id: 2,
	group_name: 'Codex 稳定分组',
	text_model: 'gpt-6.1-sol',
	image_model: 'gpt-image-2.5-sunburst',
	reasoning_effort: 'medium'
};
const key: Sub2apiKey = {
	id: 3,
	name: state.group_name,
	status: 'active',
	usable: true,
	supports_chat: true,
	supports_images: true,
	group: { id: 2, name: state.group_name, platform: 'openai' }
};
beforeEach(() => {
	vi.clearAllMocks();
	testState.settings.set({});
	testState.user.set({ id: 'a' });
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(state))));
});
describe('new user defaults', () => {
	it('matches group ID as well as key name and status', () => {
		expect(defaultWorkbenchKey([{ ...key, group: { ...key.group!, id: 8 } }, key], state)?.id).toBe(
			3
		);
		expect(defaultWorkbenchKey([{ ...key, usable: false }], state)).toBeUndefined();
	});
	it('persists exact defaults through conditional initialization', async () => {
		await initializeWorkbench([key]);
		expect(updateUserSettings).toHaveBeenCalledWith(
			'token',
			expect.objectContaining({
				sub2api_initialize: true,
				ui: expect.objectContaining({
					sub2api: { key_id: 3, image_key_id: 3 },
					models: ['gpt-6.1-sol'],
					sub2api_reasoning: { 'gpt-6.1-sol': 'medium' }
				})
			})
		);
		expect(get(testState.settings).sub2api_initialized).toBe(true);
	});
	it('preserves an explicit clear and never regenerates keys', async () => {
		testState.settings.set({ sub2api: { key_id: null, image_key_id: null } });
		await initializeWorkbench([key]);
		expect(updateUserSettings).not.toHaveBeenCalled();
	});
	it('does not initialize existing users', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...state, eligible: false })))
		);
		await initializeWorkbench([key]);
		expect(updateUserSettings).not.toHaveBeenCalled();
	});
	it('records an empty selection when no matching key exists', async () => {
		await initializeWorkbench([]);
		expect(get(testState.settings).sub2api).toEqual({ key_id: null, image_key_id: null });
	});
});
