// sub2api embed: the frontend half of the blocklist (backend: open_webui/embed/blocklist.py).
//
// Upstream components check `$embedHides('<feature>')` (or the helpers below) at each entry point,
// next to a `sub2api-embed` comment. When rebasing, review this table together with blocklist.py.
import { derived, get, type Readable } from 'svelte/store';
import { embedMode } from './mode';

/** UI entry points removed in embed mode (PRD R7.4 / R9). */
export const HIDDEN_FEATURES = {
	// layout / chrome
	userMenu: 'avatar menu → plain 「设置」 button (EmbedSidebarFooter)',
	changelog: 'ChangelogModal',
	updateToast: 'version update toast',
	banners: 'admin banners',
	onboarding: 'first-run onboarding',
	channels: 'channels section + channel routes',
	automations: 'automations (phase 2)',
	playground: 'playground',
	knowledge: 'knowledge bases (no embedding model)',
	skills: 'skills',
	// message input
	mic: 'voice input (no /v1/audio)',
	call: 'voice call',
	codeInterpreter: 'code interpreter toggle',
	terminal: 'terminal / open terminal integrations',
	// responses
	tts: 'read aloud',
	rating: 'thumbs up / down',
	share: 'chat sharing',
	// settings
	themeSelect: 'theme picker (the console drives light / dark)',
	languageSelect: 'language picker (the console drives the locale)',
	iframeSameOrigin: 'iframeSandboxAllowSameOrigin toggle',
	// external resources (CSP: img-src / connect-src 'self')
	gravatar: 'Gravatar avatars',
	externalFavicons: 'google.com/s2/favicons in citations',
	osmTiles: 'OpenStreetMap tiles'
} as const;

export type EmbedFeature = keyof typeof HIDDEN_FEATURES;

export const isHiddenFeature = (feature: EmbedFeature, embed: boolean): boolean =>
	embed && feature in HIDDEN_FEATURES;

/** `$embedHides('mic')` → true when the feature must not be offered. */
export const embedHides: Readable<(feature: EmbedFeature) => boolean> = derived(
	embedMode,
	($embed) => (feature: EmbedFeature) => isHiddenFeature(feature, $embed)
);

export const embedHidesNow = (feature: EmbedFeature): boolean =>
	isHiddenFeature(feature, get(embedMode));

/** Personal settings tabs kept in embed mode; `sub2api` is the new 「模型与密钥」 tab. */
export const EMBED_SETTINGS_TABS = [
	'general',
	'interface',
	'sub2api',
	'shortcuts',
	'data_controls',
	'archived_chats'
] as const;

/** Admin settings tabs kept in embed mode (tool servers / MCP only, PRD R9.3). */
export const EMBED_ADMIN_SETTINGS_TABS = ['admin:integrations'] as const;

export function filterSettingsTabs<T extends { id: string }>(tabs: T[], embed: boolean): T[] {
	if (!embed) return tabs;
	const allowed = new Set<string>([...EMBED_SETTINGS_TABS, ...EMBED_ADMIN_SETTINGS_TABS]);
	return tabs.filter((tab) => allowed.has(tab.id));
}

/** Sidebar entries kept in embed mode (workspace only for admins, as upstream decides). */
export const EMBED_SIDEBAR_ITEMS = ['notes', 'calendar', 'workspace'] as const;

export const isSidebarItemAllowed = (id: string, embed: boolean): boolean =>
	!embed || (EMBED_SIDEBAR_ITEMS as readonly string[]).includes(id);

/** Workspace sections kept in embed mode (presets = models, prompt library, admin tools). */
export const EMBED_WORKSPACE_SECTIONS = ['models', 'prompts', 'tools'] as const;

/** Client routes that are redirected to `/` in embed mode. */
export const EMBED_BLOCKED_ROUTES = [
	'/channels',
	'/automations',
	'/playground',
	'/workspace/knowledge',
	'/workspace/skills',
	'/admin/users',
	'/admin/evaluations',
	'/admin/analytics',
	'/admin/settings',
	'/home'
] as const;

export function isRouteBlocked(pathname: string, embed: boolean): boolean {
	if (!embed) return false;
	return EMBED_BLOCKED_ROUTES.some((p) => pathname === p || pathname.startsWith(p + '/'));
}
