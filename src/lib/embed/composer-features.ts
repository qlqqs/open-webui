// sub2api embed: the composer's 「联网搜索」/「图片生成」 toggles. Upstream treats them as per-message
// selections and clears them on every new chat, chat switch and model change; in the embed they are
// a preference remembered in this browser (off until the user turns one on), and MessageInput keeps
// the per-chat flags in sync with it. While a toggle is on the model receives the tool and decides
// itself whether to search or draw.
import { writable } from 'svelte/store';
import { localStorage } from './storage';

export const FEATURES_STORAGE_KEY = 's2a:features';

export type ComposerFeature = 'web_search' | 'image_generation';
export type ComposerFeatures = Record<ComposerFeature, boolean>;

const DEFAULTS: ComposerFeatures = { web_search: false, image_generation: false };

const load = (): ComposerFeatures => {
	try {
		const raw = JSON.parse(localStorage.getItem(FEATURES_STORAGE_KEY) ?? '{}');
		if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return { ...DEFAULTS };
		return {
			web_search: raw.web_search === true,
			image_generation: raw.image_generation === true
		};
	} catch {
		return { ...DEFAULTS };
	}
};

export const composerFeatures = writable<ComposerFeatures>(load());

export function setComposerFeature(feature: ComposerFeature, enabled: boolean): void {
	composerFeatures.update((current) => {
		const next = { ...current, [feature]: enabled };
		try {
			localStorage.setItem(FEATURES_STORAGE_KEY, JSON.stringify(next));
		} catch {
			// storage full or blocked: the choice still applies for this page
		}
		return next;
	});
}
