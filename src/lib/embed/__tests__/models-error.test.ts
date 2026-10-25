import { describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/paths', () => ({ base: '/_chat' }));

import { config } from '$lib/stores';
import { embedModelsError, mapModelsError, setEmbedModelsError } from '../errors';
import { getModels } from '$lib/apis';

const balanceBody = {
	detail: '账户余额不足',
	s2a_gateway_error: { status: 403, code: 'INSUFFICIENT_BALANCE', message: 'Insufficient account balance' }
};

describe('/api/models failures (contract D)', () => {
	it('maps the gateway error carried by /api/models', () => {
		expect(mapModelsError(balanceBody)).toMatchObject({ kind: 'balance', action: 'purchase' });
		expect(
			mapModelsError({ detail: 'x', s2a_gateway_error: { status: 401, code: 'INVALID_API_KEY', message: 'Invalid API key' } })
		).toMatchObject({ kind: 'key', action: 'settings' });
		expect(mapModelsError({ detail: '请选择可用的 Key' })).toMatchObject({ kind: 'key', action: 'settings' });
		expect(mapModelsError({ detail: '网关模型列表不可用' })).toMatchObject({
			kind: 'models',
			action: null,
			original: '网关模型列表不可用'
		});
	});

	it('store is set on failure and cleared on success', () => {
		setEmbedModelsError(balanceBody);
		expect(get(embedModelsError)?.mapped.kind).toBe('balance');
		setEmbedModelsError(null);
		expect(get(embedModelsError)).toBeNull();
	});

	it('getModels resolves to [] (no rejection) in embed mode and records the error', async () => {
		config.set({ sub2api: { embed: true } } as any);
		const fetchMock = vi.fn().mockResolvedValue(
			new Response(JSON.stringify(balanceBody), { status: 403, headers: { 'content-type': 'application/json' } })
		);
		vi.stubGlobal('fetch', fetchMock);
		await expect(getModels('t')).resolves.toEqual([]);
		expect(get(embedModelsError)?.mapped.action).toBe('purchase');
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ data: [{ id: 'm' }] }), { status: 200 }));
		const models = await getModels('t');
		expect(models.map((m: any) => m.id)).toEqual(['m']);
		expect(get(embedModelsError)).toBeNull();
		// upstream behaviour outside embed mode: the rejection is kept
		config.set({} as any);
		fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'x' }), { status: 500 }));
		await expect(getModels('t')).rejects.toEqual({ detail: 'x' });
		vi.unstubAllGlobals();
	});
});
