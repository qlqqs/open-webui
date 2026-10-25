// sub2api embed: artifact sandbox helpers (see ArtifactFrame.svelte and
// static/embed/artifact-frame.html; protocol in docs/sub2api-embed-frontend.md#artifact-frame).
import { withBase } from './paths';

export const ARTIFACT_FRAME_PATH = '/embed/artifact-frame.html';
export const ARTIFACT_PROTOCOL = 'sub2api-artifact';

export type ArtifactRenderMessage = {
	protocol: typeof ARTIFACT_PROTOCOL;
	type: 'render';
	html: string;
	/** false: the requested sandbox had no allow-scripts → the frame adds `script-src 'none'` */
	scripts: boolean;
	/** report the content height with { type: 'iframe:height', height } */
	autoHeight: boolean;
};

/** sandbox tokens: never allow-same-origin / top navigation; allow-scripts is needed by the loader. */
export function artifactSandbox(requested: string | null | undefined): {
	sandbox: string;
	scripts: boolean;
} {
	const tokens = new Set(
		String(requested ?? '')
			.split(/\s+/)
			.filter(Boolean)
	);
	const scripts = tokens.has('allow-scripts');
	tokens.delete('allow-same-origin');
	tokens.delete('allow-top-navigation');
	tokens.delete('allow-top-navigation-by-user-activation');
	tokens.delete('allow-scripts');
	return { sandbox: ['allow-scripts', ...tokens].join(' '), scripts };
}

export function renderMessage(html: string, scripts: boolean, autoHeight: boolean): ArtifactRenderMessage {
	return { protocol: ARTIFACT_PROTOCOL, type: 'render', html, scripts, autoHeight };
}

export const isArtifactReady = (data: unknown): boolean =>
	!!data &&
	typeof data === 'object' &&
	(data as Record<string, unknown>).protocol === ARTIFACT_PROTOCOL &&
	(data as Record<string, unknown>).type === 'ready';

export const artifactFrameUrl = () => withBase(ARTIFACT_FRAME_PATH);
