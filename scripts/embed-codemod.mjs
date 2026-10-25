#!/usr/bin/env node
// sub2api embed codemod: mechanical changes that let Open WebUI run under a SvelteKit `paths.base`
// (default `/_chat`) next to the sub2api console on the same origin.
//
//   node scripts/embed-codemod.mjs           apply
//   node scripts/embed-codemod.mjs --dry     report only
//   node scripts/embed-codemod.mjs --check   exit 1 if anything would change (idempotency / CI)
//
// Rules are idempotent: running the script on its own output changes nothing. Hand-written embed
// hooks live in src/lib/embed/ (skipped here) or carry a `sub2api-embed` comment in upstream files;
// they must not contain patterns these rules would rewrite (e.g. bare '/api/...' strings).
//
// When rebasing onto a new upstream tag: re-run this script on the pristine upstream tree, then
// re-apply the hand-written hook commit. A PATCHES entry whose anchor is gone prints `MISSING`;
// fix the anchor (or the upstream code moved and needs a new rule).
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const DRY = process.argv.includes('--dry') || process.argv.includes('--check');
const CHECK = process.argv.includes('--check');
const SRC = path.join(ROOT, 'src');

const stats = {};
const sites = {};
const problems = [];
const bump = (rule, file, n = 1) => {
	if (!n) return;
	stats[rule] = (stats[rule] || 0) + n;
	(sites[rule] ||= new Set()).add(path.relative(ROOT, file));
};

function walk(dir, out = []) {
	for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
		const p = path.join(dir, e.name);
		if (e.isDirectory()) {
			if (p.includes(path.join('lib', 'i18n', 'locales'))) continue;
			walk(p, out);
		} else if (/\.(svelte|ts|js)$/.test(e.name) && !/\.(test|spec)\.ts$/.test(e.name)) out.push(p);
	}
	return out;
}

const rel = (file) => path.relative(ROOT, file).split(path.sep).join('/');
const startsWithAny = (file, list) => list.some((x) => rel(file).startsWith(x));

// Files where root-relative strings are NOT our own server paths (terminal servers etc.),
// or are handled by PATCHES below.
const R7_EXCLUDE = [
	'src/lib/components/chat/XTerminal.svelte', // /api/terminals on the terminal server
	'src/lib/components/chat/FileNav/FilePreview.svelte', // substring test on terminal URL
	'src/lib/utils/safeImageUrl.ts', // PATCHES: already concatenates WEBUI_BASE_URL
	'src/lib/components/workspace/Models/ModelEditor.svelte', // stored URL: keep unprefixed in DB
	'src/lib/workers/', // no $app/* inside workers: PATCHES
	'src/lib/pyodide/' // PATCHES
];
// Modules that must not import $lib/embed/* (workers run without SvelteKit's module graph).
const NO_IMPORT = ['src/lib/workers/', 'src/lib/embed/', 'src/service-worker'];

// Find the matching close brace for an expression starting right after '{'.
function matchBrace(s, i) {
	let depth = 1;
	let q = null;
	for (; i < s.length; i++) {
		const c = s[i];
		if (q) {
			if (c === '\\') i++;
			else if (c === q) q = null;
			continue;
		}
		if (c === '"' || c === "'" || c === '`') q = c;
		else if (c === '{') depth++;
		else if (c === '}' && --depth === 0) return i;
	}
	return -1;
}

function wrapAttrExpr(src, attr, file, rule) {
	// attr={expr} -> attr={withBase(expr)}
	const re = new RegExp(`(\\s${attr}=)\\{`, 'g');
	let out = '';
	let last = 0;
	let m;
	let n = 0;
	while ((m = re.exec(src))) {
		const start = m.index + m[0].length;
		const end = matchBrace(src, start);
		if (end < 0) continue;
		const expr = src.slice(start, end);
		// already prefixed / absolute: skip (keeps the diff small)
		if (/^\s*withBase\(/.test(expr)) continue;
		if (/^\s*[`'"](\$\{WEBUI_(API_)?BASE_URL\}|\$\{BASE\}|https?:|data:|blob:|#)/.test(expr)) continue;
		if (/^\s*WEBUI_(API_)?BASE_URL\b/.test(expr)) continue;
		out += src.slice(last, start) + `withBase(${expr})`;
		last = end;
		re.lastIndex = end;
		n++;
	}
	bump(rule, file, n);
	return out + src.slice(last);
}

function ensureImport(src, file, names, from) {
	const isSvelte = file.endsWith('.svelte');
	const esc = from.replace(/[$/]/g, '\\$&');
	const existing = new RegExp(`import \\{([^}]*)\\} from '${esc}';`);
	const m = src.match(existing);
	if (m) {
		const have = m[1]
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean);
		const merged = [...new Set([...have, ...names])].sort();
		if (merged.length === have.length) return src;
		return src.replace(existing, `import { ${merged.join(', ')} } from '${from}';`);
	}
	const line = `import { ${[...names].sort().join(', ')} } from '${from}';`;
	if (!isSvelte) return line + '\n' + src;
	// instance <script> (not context="module")
	const scriptRe = /<script(?![^>]*context=["']module["'])(?![^>]*\bmodule\b)[^>]*>/;
	const sm = src.match(scriptRe);
	if (sm) {
		const at = sm.index + sm[0].length;
		return src.slice(0, at) + `\n\t${line}` + src.slice(at);
	}
	return `<script>\n\t${line}\n</script>\n\n` + src;
}

const ROOT_REL_STR =
	/(?<![=\w$}\]\)])(?<!withBase\()(['"`])(\/(?:static|api|audio|assets|favicon\.png|user\.png|opensearch\.xml|manifest\.json|ws\/)[^'"`\n]*)\1/g;

// Identifier use of Web Storage (not a property access like `foo.localStorage`, not inside a word).
const STORAGE_RE = /(?<![\w$.'"`/-])(localStorage|sessionStorage)(?![\w$'"`:-])/g;

// Exact-text patches for spots the generic rules cannot express. Each entry: [file, from, to].
// `to` must not be matched again by `from` after applying (idempotency).
const PATCHES = [
	// socket.io: a non-empty WEBUI_BASE_URL would be taken as a namespace; use the base path as path.
	[
		'src/routes/+layout.svelte',
		"const _socket = io(`${WEBUI_BASE_URL}` || undefined, {",
		'const _socket = io(undefined, {'
	],
	['src/routes/+layout.svelte', "path: '/ws/socket.io',", "path: withBase('/ws/socket.io'),"],
	// the session cookie is scoped to the base path (backend sets Path=/_chat)
	[
		'src/routes/+layout.svelte',
		"document.cookie = 'token=; Max-Age=0; path=/';",
		"document.cookie = `token=; Max-Age=0; path=${BASE || '/'}`;"
	],
	[
		'src/lib/components/chat/MessageInput.svelte',
		"if (location.pathname !== '/') {",
		"if (stripBase(location.pathname) !== '/') {"
	],
	[
		'src/lib/components/chat/Messages/Markdown/MarkdownInlineTokens.svelte',
		'const match = url.pathname.match(/^\\/notes\\/([^/]+)$/);',
		'const match = stripBase(url.pathname).match(/^\\/notes\\/([^/]+)$/);'
	],
	[
		'src/lib/components/chat/Messages/Markdown/MarkdownInlineTokens.svelte',
		"(url.pathname.startsWith('/notes/') ||\n\t\t\t\t\turl.pathname.startsWith('/c/') ||\n\t\t\t\t\turl.pathname.startsWith('/channels/'))",
		"(stripBase(url.pathname).startsWith('/notes/') ||\n\t\t\t\t\tstripBase(url.pathname).startsWith('/c/') ||\n\t\t\t\t\tstripBase(url.pathname).startsWith('/channels/'))"
	],
	[
		'src/lib/apis/auths/index.ts',
		"const logoutUrl = new URL('/auth?state=logout', window.location.origin);\n\tconst postLogoutUrl = new URL('/auth', window.location.origin);",
		"const logoutUrl = new URL(withBase('/auth?state=logout'), window.location.origin);\n\tconst postLogoutUrl = new URL(withBase('/auth'), window.location.origin);"
	],
	[
		'src/lib/apis/auths/index.ts',
		"if (url.origin === window.location.origin && url.pathname === '/auth') {",
		"if (url.origin === window.location.origin && stripBase(url.pathname) === '/auth') {"
	],
	[
		'src/lib/apis/auths/index.ts',
		"configuredPostLogoutUrl.pathname === '/auth'",
		"stripBase(configuredPostLogoutUrl.pathname) === '/auth'"
	],
	// root-relative URLs stored in the DB ("/user.png", "/api/v1/...") get the base path
	[
		'src/lib/utils/safeImageUrl.ts',
		"\t\turl.startsWith('data:') ||\n\t\turl.startsWith('/')\n\t) {\n\t\treturn url;\n\t}\n",
		"\t\turl.startsWith('data:')\n\t) {\n\t\treturn url;\n\t}\n\n\tif (url.startsWith('/') && !url.startsWith('//')) {\n\t\treturn withBase(url);\n\t}\n"
	],
	// callers already pass withBase(src) (R4c); prefixing again would give /_chat/_chat/...
	[
		'src/lib/components/common/Image.svelte',
		"$: _src = safeImageUrl(src.startsWith('/') ? `${WEBUI_BASE_URL}${src}` : src, allowExternal);",
		'$: _src = safeImageUrl(withBase(src), allowExternal);'
	],
	// workers cannot import $app/paths: derive the base from the worker script URL
	[
		'src/lib/workers/pyodide.worker.ts',
		"indexURL: '/pyodide/',",
		"indexURL: self.location.pathname.split('/_app/')[0] + '/pyodide/',"
	],
	[
		'src/lib/workers/kokoro.worker.ts',
		"env.backends.onnx.wasm.wasmPaths = '/wasm/';",
		"env.backends.onnx.wasm.wasmPaths = self.location.pathname.split('/_app/')[0] + '/wasm/';"
	],
	[
		'src/lib/pyodide/pyodideSandboxHost.ts',
		"const pyodideIndexURL = `${globalThis.location?.origin ?? ''}/pyodide/`;",
		"const pyodideIndexURL = `${globalThis.location?.origin ?? ''}${BASE}/pyodide/`;"
	],
	// i18next's detector reads window.localStorage directly; keep its key in our namespace
	['src/lib/i18n/index.ts', "lookupLocalStorage: 'locale',", "lookupLocalStorage: 'owui:locale',"]
];
// helper imports a PATCHES replacement needs
const PATCH_NEEDS = [
	[/\bwithBase\(/, 'withBase'],
	[/\bstripBase\(/, 'stripBase'],
	[/\$\{BASE\b/, 'BASE']
];

let changedFiles = 0;
const files = walk(SRC);
for (const file of files) {
	const r = rel(file);
	if (r.startsWith('src/lib/embed/')) continue;
	let src = fs.readFileSync(file, 'utf8');
	const orig = src;
	const isSvelte = file.endsWith('.svelte');
	const need = new Set();
	const canImport = !startsWithAny(file, NO_IMPORT);

	// P: exact patches
	for (const [f, from, to] of PATCHES) {
		if (f !== r) continue;
		if (src.includes(to)) continue;
		if (!src.includes(from)) {
			problems.push(`MISSING patch anchor in ${f}: ${from.slice(0, 70).replace(/\n/g, '\\n')}`);
			continue;
		}
		src = src.replace(from, to);
		bump('P  exact patches', file);
		if (canImport) for (const [re, name] of PATCH_NEEDS) if (re.test(to)) need.add(name);
	}

	// R3 $app/navigation -> $lib/embed/navigation (goto wrapper adds base)
	src = src.replace(/from '\$app\/navigation'/g, () => {
		bump('R3 import $app/navigation', file);
		return "from '$lib/embed/navigation'";
	});

	if (isSvelte) {
		// R4a static attribute: href="/x" src="/x" poster="/x" -> "{BASE}/x"
		src = src.replace(/(\s(?:href|src|poster|action)=)"(\/(?!\/)[^"]*)"/g, (_, a, v) => {
			bump('R4a attr="/..." literal', file);
			need.add('BASE');
			return `${a}"{BASE}${v}"`;
		});
		// R4b dynamic attribute: href={expr} / src={expr} -> withBase(expr)
		const before = src;
		src = wrapAttrExpr(src, 'href', file, 'R4b href={expr}');
		src = wrapAttrExpr(src, 'src', file, 'R4c src={expr}');
		if (src !== before) need.add('withBase');
	}

	// R5 location.href = '/x'
	src = src.replace(/((?:window\.)?location\.href\s*=\s*)(['`])(\/[^'`]*)\2/g, (_, a, q, v) => {
		bump('R5 location.href = "/..."', file);
		need.add('withBase');
		return `${a}withBase(${q}${v}${q})`;
	});

	// R6 $page.url.pathname -> stripBase($page.url.pathname)
	src = src.replace(/(?<!stripBase\()\$page(\s*)\.url\.pathname/g, (_, ws) => {
		bump('R6 $page.url.pathname', file);
		need.add('stripBase');
		return `stripBase($page${ws}.url.pathname)`;
	});

	// R7 root-relative server/static strings in code: '/api/...', '/static/...', '/favicon.png' ...
	if (!startsWithAny(file, R7_EXCLUDE)) {
		src = src.replace(ROOT_REL_STR, (m0, q, v) => {
			bump('R7 "/api|/static|..." string', file);
			need.add('withBase');
			return `withBase(${q}${v}${q})`;
		});
	}

	// R12 history.replaceState/pushState(state, '', '/x') -> withBase('/x')  (own window only)
	src = src.replace(
		/((?<!contentWindow\.)history\.(?:replaceState|pushState)\([^,]+,\s*(['"`])[^'"`]*\2,\s*)(([`'"])\/[^`'"]*\4)\)/g,
		(_, a, _q, v) => {
			bump('R12 history.replaceState("/...")', file);
			need.add('withBase');
			return `${a}withBase(${v}))`;
		}
	);

	// R11 `${window.location.origin}/x` -> `${window.location.origin}${BASE}/x`
	src = src.replace(/\$\{window\.location\.origin\}\/(?!\$\{BASE\})/g, () => {
		bump('R11 ${location.origin}/...', file);
		need.add('BASE');
		return '${window.location.origin}${BASE}/';
	});

	if (need.size && !canImport) {
		problems.push(`${r}: rule needs ${[...need].join(', ')} but this module cannot import $lib/embed`);
	}
	if (need.size && canImport) src = ensureImport(src, file, [...need], '$lib/embed/paths');

	// R13 Web Storage -> namespaced proxies from $lib/embed/storage (identifier shadowing)
	if (canImport && !r.startsWith('src/lib/i18n/locales')) {
		const used = new Set();
		const code = src.replace(/^\s*(\/\/|\*).*$/gm, ''); // ignore comment-only lines
		for (const m of code.matchAll(STORAGE_RE)) used.add(m[1]);
		if (used.size) {
			const before = src;
			src = ensureImport(src, file, [...used], '$lib/embed/storage');
			if (src !== before) bump('R13 import $lib/embed/storage', file);
		}
	}

	if (src !== orig) {
		changedFiles++;
		if (!DRY) fs.writeFileSync(file, src);
	}
}
for (const [f] of PATCHES) {
	if (!files.some((file) => rel(file) === f)) problems.push(`MISSING patch file ${f}`);
}

// R1 svelte.config.js paths.base
{
	const f = path.join(ROOT, 'svelte.config.js');
	let s = fs.readFileSync(f, 'utf8');
	if (!s.includes('paths:')) {
		s = s.replace(
			/kit: \{\n/,
			"kit: {\n\t\t// sub2api embed: serve under a sub-path (OWUI_BASE_PATH='' restores the root)\n\t\tpaths: { base: process.env.OWUI_BASE_PATH ?? '/_chat', relative: false },\n"
		);
		bump('R1 svelte.config paths.base', f);
		changedFiles++;
		if (!DRY) fs.writeFileSync(f, s);
	}
}

// R2 WEBUI_BASE_URL derived from $app/paths
{
	const f = path.join(SRC, 'lib/constants.ts');
	let s = fs.readFileSync(f, 'utf8');
	if (s.includes("export const WEBUI_BASE_URL = '';")) {
		s = s.replace("export const WEBUI_BASE_URL = '';", 'export const WEBUI_BASE_URL = base;');
		s = "import { base } from '$app/paths';\n" + s;
		bump('R2 WEBUI_BASE_URL = base', f);
		changedFiles++;
		if (!DRY) fs.writeFileSync(f, s);
	}
}

// R9 app.html
{
	const f = path.join(SRC, 'app.html');
	const orig = fs.readFileSync(f, 'utf8');
	let s = orig;
	// R9a root-relative asset URLs -> %sveltekit.assets% (also inside the inline splash script)
	s = s.replace(/(["'])\/(static\/|manifest\.json)/g, (_, q, p) => {
		bump('R9a app.html asset URL', f);
		return `${q}%sveltekit.assets%/${p}`;
	});
	// R9b drop the unused resizeIframe() inline script (one less inline script for the CSP)
	s = s.replace(
		/\n\t\t<script>\n\t\t\tfunction resizeIframe\(obj\) \{\n[\s\S]*?\n\t\t<\/script>\n/,
		() => {
			bump('R9b app.html drop resizeIframe', f);
			return '';
		}
	);
	// R9c theme key lives in the owui: namespace (see src/lib/embed/storage.ts)
	s = s.replace(/localStorage(\??)\.theme\b/g, (_, opt) => {
		bump('R9c app.html localStorage.theme', f);
		return `localStorage${opt}${opt ? '.' : ''}['owui:theme']`;
	});
	// R9d embed boot: theme from ?theme=, splash branding hidden inside the console iframe
	if (!s.includes('sub2api-embed boot')) {
		s = s.replace(
			/\n(\t\t<script>\n\t\t\t\/\/ On page load or when changing themes)/,
			(_, rest) => {
				bump('R9d app.html embed boot', f);
				return `
		<script>
			// sub2api-embed boot: see src/lib/embed/theme.ts (theme query) and mode.ts (branding cache)
			(() => {
				try {
					const q = new URLSearchParams(location.search).get('theme');
					if (q === 'light' || q === 'dark') localStorage.setItem('owui:theme', q);
					const hide = localStorage.getItem('owui:s2a:hide-branding');
					if (hide === '1' || (hide === null && window.self !== window.top)) {
						document.documentElement.classList.add('s2a-hide-branding');
					}
				} catch (e) {}
			})();
		</script>
${rest}`;
			}
		);
		s = s.replace(/(\n\t\thtml\.her #logo \{\n\t\t\tdisplay: none;\n\t\t\})/, (m) => {
			bump('R9d app.html embed boot', f);
			return `${m}

		/* sub2api-embed: no splash branding inside the console iframe */
		html.s2a-hide-branding #logo,
		html.s2a-hide-branding #logo-her {
			display: none !important;
		}`;
		});
	}
	if (s !== orig) {
		changedFiles++;
		if (!DRY) fs.writeFileSync(f, s);
	}
}

console.log(`files changed: ${changedFiles}${DRY ? ' (dry run)' : ''}`);
for (const [k, v] of Object.entries(stats).sort()) {
	console.log(`${k.padEnd(34)} ${String(v).padStart(4)} sites in ${sites[k].size} files`);
}
for (const p of problems) console.log('WARN ' + p);
if (CHECK && changedFiles > 0) {
	console.error('embed-codemod --check: the tree is not up to date (run without --check)');
	process.exit(1);
}
if (problems.length) process.exitCode = 2;
