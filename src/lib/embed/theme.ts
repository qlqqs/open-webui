// sub2api embed: light / dark driven by the console (bridge) instead of the theme picker.
import { theme } from '$lib/stores';
import { localStorage } from './storage';
import type { ChatTheme } from './bridge';

const INLINE_GRAYS = ['--color-gray-800', '--color-gray-850', '--color-gray-900', '--color-gray-950'];
const THEME_CLASSES = ['dark', 'light', 'oled-dark', 'her'];

/** Page background per mode (theme.css `--s2a-page`), used for <meta name="theme-color">. */
export const EMBED_PAGE_COLOR: Record<ChatTheme, string> = { light: '#ffffff', dark: '#0b0f17' };

export function applyEmbedTheme(next: ChatTheme, doc: Document = document): void {
	try {
		localStorage.setItem('theme', next);
	} catch {
		// ignore
	}
	theme.set(next);
	const root = doc.documentElement;
	// upstream writes these inline for dark / oled themes; inline styles would beat theme.css
	for (const prop of INLINE_GRAYS) root.style.removeProperty(prop);
	for (const cls of THEME_CLASSES) if (cls !== next) root.classList.remove(cls);
	root.classList.add(next);
	root.classList.add('s2a-embed');
	doc.querySelector('meta[name="theme-color"]')?.setAttribute('content', EMBED_PAGE_COLOR[next]);
}

/** Embed mode without a session message yet: pin whatever app.html chose to plain light / dark. */
export function normalizeInitialTheme(doc: Document = document): void {
	const dark = doc.documentElement.classList.contains('dark');
	applyEmbedTheme(dark ? 'dark' : 'light', doc);
}
