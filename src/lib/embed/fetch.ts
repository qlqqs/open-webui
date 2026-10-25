// sub2api embed: the fetch wrapper (installed before upstream's own window.fetch override).
//
// 1. Requests under the base path carry the selected key IDs (contract A).
// 2. A 401 from sub2api itself — body {"error":{"code":"CHAT_SESSION_INVALID"}} (contract B.3), i.e.
//    the s2a_chat cookie expired — is not Open WebUI's 401: post `chat:session-expired`, wait for the
//    console to re-issue the cookie (next chat-session revision) and retry once. If that fails the
//    response is handed on as 403 so upstream's 401 handler does not sign the Open WebUI session out
//    (that would only loop through /auth while the console session is gone).
import { base } from '$app/paths';
import { addKeyHeaders, getKeySelection, isBaseUrl, keyHeaders } from './keys';
import { renewSession } from './bridge';
import { isEmbedMode } from './mode';

export const SESSION_INVALID_CODE = 'CHAT_SESSION_INVALID';

type FetchInput = RequestInfo | URL;

/** true for sub2api's own 401 (expired / missing s2a_chat cookie). */
export async function isSub2apiSessionError(response: Response): Promise<boolean> {
	if (response.status !== 401) return false;
	const type = response.headers.get('content-type') ?? '';
	if (!type.includes('json')) return false;
	try {
		const body = await response.clone().json();
		const code = body?.error?.code ?? body?.code;
		return code === SESSION_INVALID_CODE;
	} catch {
		return false;
	}
}

const canReplay = (input: FetchInput, init?: RequestInit): boolean => {
	if (typeof input === 'object' && 'body' in input && (input as Request).bodyUsed) return false;
	const body = init?.body;
	return !(typeof ReadableStream !== 'undefined' && body instanceof ReadableStream);
};

async function asForbidden(response: Response): Promise<Response> {
	const body = await response.text();
	return new Response(body, {
		status: 403,
		statusText: 'Forbidden',
		headers: response.headers
	});
}

export function createEmbedFetch(
	inner: typeof fetch,
	origin: () => string,
	renew: () => Promise<boolean> = () => renewSession()
): typeof fetch {
	return (async (input: FetchInput, init?: RequestInit) => {
		const [i, o] = addKeyHeaders(input, init, keyHeaders(getKeySelection()), origin(), base);
		const url = typeof i === 'string' || i instanceof URL ? String(i) : i.url;
		const ours = isEmbedMode() && isBaseUrl(url, origin(), base);
		const replayable = ours && canReplay(i, o);
		const request = replayable && typeof i === 'object' && !(i instanceof URL) ? i.clone() : i;
		const response = await inner(request, o);
		if (!ours || !(await isSub2apiSessionError(response))) return response;
		if (replayable && (await renew())) {
			const retry = await inner(i, o);
			if (!(await isSub2apiSessionError(retry))) return retry;
			return asForbidden(retry);
		}
		return asForbidden(response);
	}) as typeof fetch;
}

let installed = false;

export function installEmbedFetch(): void {
	if (installed || typeof window === 'undefined') return;
	installed = true;
	window.fetch = createEmbedFetch(window.fetch.bind(window), () => window.location.origin);
}
