// sub2api embed: neutral model avatars when branding is hidden (PRD R7.1).
//
// Models without their own image are served by the backend as a 302 to the Open WebUI logo
// (/static/favicon.png); many components also fall back to /favicon.png on error. Instead of
// hooking every <img>, one MutationObserver swaps those sources for a neutral icon while
// `hide_branding` is on. Custom avatars (admin presets with an uploaded image) are kept.
import { withBase } from './paths';

export const NEUTRAL_AVATAR_PATH = '/embed/model-avatar.svg';

type ModelLike = { id?: string; info?: { meta?: { profile_image_url?: string | null } | null } | null };

const DEFAULT_IMAGES = ['/static/favicon.png', '/favicon.png', '/static/favicon.svg', ''];

const pathOf = (src: string): string => {
	try {
		return new URL(src, 'http://x').pathname;
	} catch {
		return src;
	}
};

/** true when a model has no avatar of its own (the backend would serve the Open WebUI logo). */
export function hasDefaultAvatar(model: ModelLike | undefined): boolean {
	const url = model?.info?.meta?.profile_image_url ?? '';
	if (!url) return true;
	if (url.startsWith('data:')) return false;
	const p = pathOf(url).replace(/^\/_chat(?=\/)/, '');
	return DEFAULT_IMAGES.includes(p);
}

/** Decide the replacement for an <img src>; null keeps the original. */
export function neutralAvatarFor(
	src: string,
	basePath: string,
	findModel: (id: string) => ModelLike | undefined
): string | null {
	if (!src || src.startsWith('data:') || src.startsWith('blob:')) return null;
	let url: URL;
	try {
		url = new URL(src, 'http://x');
	} catch {
		return null;
	}
	const path = basePath && url.pathname.startsWith(basePath + '/') ? url.pathname.slice(basePath.length) : url.pathname;
	if (path === NEUTRAL_AVATAR_PATH) return null;
	if (path === '/static/favicon.png' || path === '/favicon.png') return NEUTRAL_AVATAR_PATH;
	if (path === '/api/v1/models/model/profile/image') {
		const id = url.searchParams.get('id') ?? '';
		return hasDefaultAvatar(findModel(id)) ? NEUTRAL_AVATAR_PATH : null;
	}
	return null;
}

let observer: MutationObserver | null = null;

export function startNeutralAvatars(
	basePath: string,
	findModel: (id: string) => ModelLike | undefined,
	root: Document = document
): () => void {
	stopNeutralAvatars();
	const fix = (img: HTMLImageElement) => {
		const next = neutralAvatarFor(img.getAttribute('src') ?? '', basePath, findModel);
		if (next) img.setAttribute('src', withBase(next));
	};
	const scan = (node: Node) => {
		if (node instanceof HTMLImageElement) fix(node);
		else if (node instanceof Element) node.querySelectorAll('img').forEach(fix);
	};
	observer = new MutationObserver((records) => {
		for (const r of records) {
			if (r.type === 'attributes' && r.target instanceof HTMLImageElement) fix(r.target);
			else r.addedNodes.forEach(scan);
		}
	});
	observer.observe(root.documentElement, {
		subtree: true,
		childList: true,
		attributes: true,
		attributeFilter: ['src']
	});
	scan(root.documentElement);
	return stopNeutralAvatars;
}

export function stopNeutralAvatars(): void {
	observer?.disconnect();
	observer = null;
}
