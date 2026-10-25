import { afterEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/paths', () => ({ base: '/_chat' }));
// reasoning.ts reads storage at import; the storage proxy caches the first global it sees
const local = await vi.hoisted(async () => {
	const { MemoryStorage } = await import('./memoryStorage');
	const storage = new MemoryStorage();
	vi.stubGlobal('localStorage', storage);
	return storage;
});

import type { ModelReasoning } from '../keys';
import {
	REASONING_STORAGE_KEY,
	modelReasoning,
	syncModelReasoning,
	chosenEffort,
	reasoningChoices,
	reasoningFor,
	reasoningLevelKey,
	reasoningModelId,
	reasoningParams,
	reasoningState,
	setReasoningChoice
} from '../reasoning';
import { localStorage } from '../storage';

const OPUS: ModelReasoning = {
	levels: ['low', 'medium', 'high', 'xhigh', 'max'],
	default: 'medium',
	multipliers: { max: 1.5 }
};

afterEach(() => {
	modelReasoning.set({});
	reasoningChoices.set({});
	localStorage.removeItem(REASONING_STORAGE_KEY);
	vi.stubGlobal('fetch', undefined);
});

describe('reasoning state', () => {
	it('shows the default until a valid level is chosen', () => {
		expect(reasoningState('opus', OPUS, undefined)).toEqual({
			modelId: 'opus',
			reasoning: OPUS,
			chosen: undefined,
			current: 'medium'
		});
		expect(reasoningState('opus', OPUS, 'max')?.current).toBe('max');
		// a choice the current key's group no longer allows falls back to the default
		expect(reasoningState('opus', { levels: ['low', 'medium'] }, 'max')).toMatchObject({
			chosen: undefined,
			current: 'low'
		});
		expect(reasoningState('m', { levels: ['low', 'medium', 'high'] }, undefined)?.current).toBe(
			'medium'
		);
	});

	it('hides the picker without a choice to make', () => {
		expect(reasoningState('m', undefined, 'high')).toBeNull();
		expect(reasoningState('m', { levels: ['high'] }, undefined)).toBeNull();
	});

	it('only sends a level the model offers', () => {
		expect(chosenEffort(OPUS, 'xhigh')).toBe('xhigh');
		expect(chosenEffort(OPUS, 'minimal')).toBeUndefined();
		expect(chosenEffort(undefined, 'high')).toBeUndefined();

		modelReasoning.set({ opus: OPUS });
		expect(reasoningParams('opus')).toEqual({});
		setReasoningChoice('opus', 'max');
		expect(reasoningParams('opus')).toEqual({ reasoning_effort: 'max' });
		expect(reasoningParams('other')).toEqual({});
		modelReasoning.set({ opus: { levels: ['low', 'medium'] } });
		expect(reasoningParams('opus')).toEqual({});
	});

	it('remembers choices per model in prefixed storage', () => {
		setReasoningChoice('opus', 'high');
		setReasoningChoice('gpt', 'low');
		expect(JSON.parse(local.getItem(`owui:${REASONING_STORAGE_KEY}`) ?? '')).toEqual({
			opus: 'high',
			gpt: 'low'
		});
		modelReasoning.set({ opus: OPUS });
		expect(get(reasoningFor('opus'))?.chosen).toBe('high');
		expect(get(reasoningFor(null))).toBeNull();
	});

	it('resolves custom models to their base model and labels known levels', () => {
		expect(reasoningModelId({ id: 'my-opus', info: { base_model_id: 'opus' } })).toBe('opus');
		expect(reasoningModelId({ id: 'opus', info: null })).toBe('opus');
		expect(reasoningLevelKey('xhigh')).toBe('reasoning.level.xhigh');
		expect(reasoningLevelKey('ultra')).toBeNull();
	});
});

describe('syncModelReasoning', () => {
	it('loads levels once per key and model list, dropping single-level models', async () => {
		const fetch = vi.fn(async (url: string) => ({
			ok: true,
			status: 200,
			json: async () => ({
				models: url.includes('key_id=8') ? {} : { opus: OPUS, single: { levels: ['high'] } }
			})
		}));
		vi.stubGlobal('fetch', fetch);
		await syncModelReasoning(7, ['opus', 'single', 'opus', '']);
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch.mock.calls[0][0]).toBe(
			'/_chat/__sub2api/model-reasoning?key_id=7&model=opus&model=single'
		);
		expect(get(modelReasoning)).toEqual({ opus: OPUS });
		await syncModelReasoning(7, ['single', 'opus']);
		expect(fetch).toHaveBeenCalledTimes(1);
		await syncModelReasoning(8, ['opus']);
		expect(get(modelReasoning)).toEqual({});
		await syncModelReasoning(null, ['opus']);
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it('hides the picker when loading fails', async () => {
		modelReasoning.set({ opus: OPUS });
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }))
		);
		await syncModelReasoning(9, ['opus']);
		expect(get(modelReasoning)).toEqual({});
	});
});
