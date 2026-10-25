// sub2api embed: drop-in replacement for '$app/navigation' that adds the base path to goto().
import { goto as kitGoto } from '$app/navigation';
import { withBase } from './paths';

export * from '$app/navigation';

export const goto: typeof kitGoto = (url, opts) =>
	kitGoto(typeof url === 'string' ? withBase(url) : url, opts);
