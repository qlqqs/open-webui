// sub2api embed: helpers for serving Open WebUI under a SvelteKit `paths.base` (e.g. /_chat).
import { base } from '$app/paths';

export const BASE = base;

const hasBase = (u: string) =>
	u === base || u.startsWith(base + '/') || u.startsWith(base + '?') || u.startsWith(base + '#');

/** Prefix a root-relative URL ("/x") with the base path. Idempotent; other values pass through. */
export function withBase<T>(u: T): T {
	if (!base || typeof u !== 'string') return u;
	if (u.startsWith('/') && !u.startsWith('//') && !hasBase(u)) {
		return (base + u) as unknown as T;
	}
	return u;
}

/** Strip the base path from a pathname so route comparisons keep working ("/_chat/c/1" -> "/c/1"). */
export function stripBase<T>(p: T): T {
	if (!base || typeof p !== 'string') return p;
	if (p === base) return '/' as unknown as T;
	if (p.startsWith(base + '/')) return p.slice(base.length) as unknown as T;
	return p;
}
