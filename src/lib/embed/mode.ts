// sub2api embed: embed-mode detection.
//
// The fork backend adds `sub2api` to `/api/config` only in embed mode (contract D):
//   "sub2api": {"embed": true, "hide_branding": false, "native_web_search": true, "image_generation": true}
// Every embed-only behaviour in the frontend keys off the stores below, so the fork behaves like
// upstream Open WebUI when the field is absent.
import { derived, get, type Readable } from 'svelte/store';
import { config } from '$lib/stores';
import { localStorage } from './storage';

export type EmbedConfig = {
	embed: true;
	hide_branding: boolean;
	native_web_search: boolean;
	image_generation: boolean;
};

/** Parse the `sub2api` field of `/api/config`; null outside embed mode. */
export function parseEmbedConfig(backendConfig: unknown): EmbedConfig | null {
	const raw = (backendConfig as { sub2api?: Record<string, unknown> } | null | undefined)?.sub2api;
	if (!raw || typeof raw !== 'object' || raw.embed !== true) return null;
	return {
		embed: true,
		hide_branding: raw.hide_branding === true,
		native_web_search: raw.native_web_search !== false,
		image_generation: raw.image_generation !== false
	};
}

export const embedConfig: Readable<EmbedConfig | null> = derived(config, ($config) =>
	parseEmbedConfig($config)
);

/** true inside the sub2api console (embed mode). */
export const embedMode: Readable<boolean> = derived(embedConfig, ($e) => $e !== null);

/** true when every Open WebUI name / logo must be hidden (embed mode + S2A_HIDE_BRANDING=1). */
export const hideBranding: Readable<boolean> = derived(embedConfig, ($e) => !!$e?.hide_branding);

export const isEmbedMode = (): boolean => get(embedMode);
export const isBrandingHidden = (): boolean => get(hideBranding);

/** Branding cache read by the app.html boot script (splash logo before /api/config arrives). */
export const HIDE_BRANDING_CACHE_KEY = 's2a:hide-branding';

export function cacheBrandingFlag(e: EmbedConfig | null): void {
	try {
		localStorage.setItem(HIDE_BRANDING_CACHE_KEY, e?.hide_branding ? '1' : '0');
	} catch {
		// storage unavailable
	}
	if (typeof document !== 'undefined') {
		document.documentElement.classList.toggle('s2a-hide-branding', !!e?.hide_branding);
		document.documentElement.classList.toggle('s2a-embed', !!e);
	}
}
