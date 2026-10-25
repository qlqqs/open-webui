// sub2api embed: namespaced Web Storage.
//
// Open WebUI shares the origin with the sub2api console when it is embedded under /_chat, and both
// sides use keys like `token`, `theme` and `locale`. `scripts/embed-codemod.mjs` adds
//   import { localStorage, sessionStorage } from '$lib/embed/storage';
// to every frontend module that touches Web Storage, so the identifiers resolve to these proxies
// instead of the globals. Every key is transparently stored as `owui:<key>`; keys without the prefix
// (the console's) are invisible to Open WebUI and are never modified by it.
//
// The proxies support the Storage API (getItem / setItem / removeItem / clear / key / length) as
// well as property access (`localStorage.token`, `localStorage.token = x`, `delete localStorage.x`,
// `Object.keys(localStorage)`, `'x' in localStorage`).

export const STORAGE_PREFIX = 'owui:';

const STORAGE_METHODS = new Set(['getItem', 'setItem', 'removeItem', 'clear', 'key', 'length']);

type StorageResolver = () => Storage | undefined;

const ownKeys = (target: Storage | undefined, prefix: string): string[] => {
	if (!target) return [];
	const keys: string[] = [];
	for (let i = 0; i < target.length; i++) {
		const key = target.key(i);
		if (key !== null && key.startsWith(prefix)) keys.push(key.slice(prefix.length));
	}
	return keys;
};

/** Build a Storage-compatible proxy that namespaces every key with `prefix`. */
export function createPrefixedStorage(resolve: StorageResolver, prefix = STORAGE_PREFIX): Storage {
	const api = {
		getItem: (key: string) => resolve()?.getItem(prefix + String(key)) ?? null,
		setItem: (key: string, value: unknown) => {
			resolve()?.setItem(prefix + String(key), String(value));
		},
		removeItem: (key: string) => {
			resolve()?.removeItem(prefix + String(key));
		},
		clear: () => {
			const target = resolve();
			for (const key of ownKeys(target, prefix)) target?.removeItem(prefix + key);
		},
		key: (index: number) => ownKeys(resolve(), prefix)[index] ?? null
	};

	return new Proxy({} as Storage, {
		get(_target, prop) {
			if (typeof prop !== 'string') return undefined;
			if (prop === 'length') return ownKeys(resolve(), prefix).length;
			if (prop in api) return api[prop as keyof typeof api];
			const value = resolve()?.getItem(prefix + prop);
			return value === null ? undefined : value;
		},
		set(_target, prop, value) {
			if (typeof prop !== 'string' || STORAGE_METHODS.has(prop)) return false;
			resolve()?.setItem(prefix + prop, String(value));
			return true;
		},
		deleteProperty(_target, prop) {
			if (typeof prop === 'string') resolve()?.removeItem(prefix + prop);
			return true;
		},
		has(_target, prop) {
			if (typeof prop !== 'string') return false;
			if (STORAGE_METHODS.has(prop)) return true;
			return (resolve()?.getItem(prefix + prop) ?? null) !== null;
		},
		ownKeys() {
			return ownKeys(resolve(), prefix);
		},
		getOwnPropertyDescriptor(_target, prop) {
			if (typeof prop !== 'string') return undefined;
			const value = resolve()?.getItem(prefix + prop) ?? null;
			if (value === null) return undefined;
			return { value, writable: true, enumerable: true, configurable: true };
		}
	});
}

const browserStorage = (name: 'localStorage' | 'sessionStorage'): StorageResolver => {
	let cached: Storage | undefined;
	return () => {
		if (cached) return cached;
		try {
			cached = (globalThis as unknown as Record<string, Storage | undefined>)[name];
		} catch {
			cached = undefined; // storage disabled (sandboxed / privacy mode)
		}
		return cached;
	};
};

export const localStorage: Storage = createPrefixedStorage(browserStorage('localStorage'));
export const sessionStorage: Storage = createPrefixedStorage(browserStorage('sessionStorage'));

/** Remove every namespaced key from both storages (account switch / revoke). */
export function clearEmbedStorage(except: string[] = []): void {
	for (const store of [localStorage, sessionStorage]) {
		for (const key of Object.keys(store)) {
			if (!except.includes(key)) store.removeItem(key);
		}
	}
}
