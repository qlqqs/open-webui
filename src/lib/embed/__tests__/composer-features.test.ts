import { describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/paths', () => ({ base: '/_chat' }));
// composer-features.ts reads storage at import; the storage proxy caches the first global it sees
const local = await vi.hoisted(async () => {
	const { MemoryStorage } = await import('./memoryStorage');
	const storage = new MemoryStorage();
	storage.setItem('owui:s2a:features', '{"web_search":true,"image_generation":"yes"}');
	vi.stubGlobal('localStorage', storage);
	return storage;
});

import { FEATURES_STORAGE_KEY, composerFeatures, setComposerFeature } from '../composer-features';

describe('composer feature toggles', () => {
	it('loads only explicit true values and remembers changes under the owui: prefix', () => {
		expect(get(composerFeatures)).toEqual({ web_search: true, image_generation: false });

		setComposerFeature('image_generation', true);
		setComposerFeature('web_search', false);

		expect(get(composerFeatures)).toEqual({ web_search: false, image_generation: true });
		expect(JSON.parse(local.getItem('owui:' + FEATURES_STORAGE_KEY) as string)).toEqual({
			web_search: false,
			image_generation: true
		});
	});
});
