import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/paths', () => ({ base: '/_chat' }));

import { artifactSandbox, isArtifactReady, renderMessage } from '../artifact';
import { hasDefaultAvatar, neutralAvatarFor } from '../avatar';
import { filterSettingsTabs, isRouteBlocked, isSidebarItemAllowed } from '../features';
import { parseEmbedConfig } from '../mode';
import { translate } from '../i18n';

describe('artifact sandbox', () => {
	it('never grants allow-same-origin and always lets the loader run', () => {
		expect(artifactSandbox('allow-scripts allow-same-origin allow-forms')).toEqual({
			sandbox: 'allow-scripts allow-forms',
			scripts: true
		});
		expect(artifactSandbox('allow-downloads allow-top-navigation')).toEqual({
			sandbox: 'allow-scripts allow-downloads',
			scripts: false
		});
		expect(artifactSandbox(undefined)).toEqual({ sandbox: 'allow-scripts', scripts: false });
	});

	it('builds protocol messages', () => {
		expect(renderMessage('<p>x</p>', true, false)).toEqual({
			protocol: 'sub2api-artifact',
			type: 'render',
			html: '<p>x</p>',
			scripts: true,
			autoHeight: false
		});
		expect(isArtifactReady({ protocol: 'sub2api-artifact', type: 'ready' })).toBe(true);
		expect(isArtifactReady({ type: 'ready' })).toBe(false);
	});
});

describe('neutral avatars', () => {
	const models: Record<string, any> = {
		plain: { id: 'plain', info: { meta: { profile_image_url: '/static/favicon.png' } } },
		none: { id: 'none' },
		custom: { id: 'custom', info: { meta: { profile_image_url: 'data:image/png;base64,AA' } } }
	};
	const find = (id: string) => models[id];

	it('detects models without their own image', () => {
		expect(hasDefaultAvatar(models.plain)).toBe(true);
		expect(hasDefaultAvatar(models.none)).toBe(true);
		expect(hasDefaultAvatar(models.custom)).toBe(false);
	});

	it('replaces only default logos', () => {
		const url = (id: string) => `/_chat/api/v1/models/model/profile/image?id=${id}&lang=zh-CN`;
		expect(neutralAvatarFor(url('plain'), '/_chat', find)).toBe('/embed/model-avatar.svg');
		expect(neutralAvatarFor(url('custom'), '/_chat', find)).toBeNull();
		expect(neutralAvatarFor('/_chat/static/favicon.png', '/_chat', find)).toBe('/embed/model-avatar.svg');
		expect(neutralAvatarFor('/_chat/favicon.png', '/_chat', find)).toBe('/embed/model-avatar.svg');
		expect(neutralAvatarFor('/_chat/embed/model-avatar.svg', '/_chat', find)).toBeNull();
		expect(neutralAvatarFor('/_chat/api/v1/users/1/profile/image', '/_chat', find)).toBeNull();
		expect(neutralAvatarFor('data:image/png;base64,AA', '/_chat', find)).toBeNull();
	});
});

describe('feature table', () => {
	const tabs = ['general', 'interface', 'connections', 'sub2api', 'audio', 'account', 'about', 'personalization', 'data_controls', 'admin:general', 'admin:integrations'].map((id) => ({ id }));

	it('keeps only the allowed settings tabs in embed mode', () => {
		expect(filterSettingsTabs(tabs, true).map((t) => t.id)).toEqual([
			'general',
			'interface',
			'sub2api',
			'data_controls',
			'admin:integrations'
		]);
		expect(filterSettingsTabs(tabs, false)).toHaveLength(tabs.length);
	});

	it('blocks removed routes only in embed mode', () => {
		expect(isRouteBlocked('/channels/abc', true)).toBe(true);
		expect(isRouteBlocked('/workspace/knowledge', true)).toBe(true);
		expect(isRouteBlocked('/workspace/models', true)).toBe(false);
		expect(isRouteBlocked('/admin/functions', true)).toBe(false);
		expect(isRouteBlocked('/admin/users', true)).toBe(true);
		expect(isRouteBlocked('/channels/abc', false)).toBe(false);
		expect(isRouteBlocked('/', true)).toBe(false);
	});

	it('sidebar items', () => {
		expect(isSidebarItemAllowed('notes', true)).toBe(true);
		expect(isSidebarItemAllowed('playground', true)).toBe(false);
		expect(isSidebarItemAllowed('automations', true)).toBe(false);
		expect(isSidebarItemAllowed('playground', false)).toBe(true);
	});
});

describe('embed mode', () => {
	it('is driven by /api/config sub2api', () => {
		expect(parseEmbedConfig({})).toBeNull();
		expect(parseEmbedConfig({ sub2api: { embed: false } })).toBeNull();
		expect(parseEmbedConfig({ sub2api: { embed: true, hide_branding: true } })).toEqual({
			embed: true,
			hide_branding: true,
			native_web_search: true,
			image_generation: true
		});
	});

	it('translates embed strings in both locales', () => {
		expect(translate('zh-CN', 'settings.tab')).toBe('模型与密钥');
		expect(translate('en-US', 'settings.tab')).toBe('Models & Keys');
		expect(translate('zh-TW', 'keys.created', { name: 'x' })).toContain('x');
	});
});
