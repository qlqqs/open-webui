#!/usr/bin/env node
// sub2api embed: move every inline <script> of the built HTML pages into external files so the
// page CSP can be `script-src 'self'` (no hashes, no 'unsafe-inline'; design §5.2).
//
//   node scripts/embed-postbuild.mjs [buildDir=build]
//
// Only top-level *.html files are processed (SvelteKit's SPA fallback index.html). The artifact
// sandbox page build/embed/artifact-frame.html is skipped on purpose: it is served with its own CSP
// that allows inline scripts. Running the script twice is a no-op (no inline scripts left).
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const dir = path.resolve(process.argv[2] || 'build');
const base = process.env.OWUI_BASE_PATH ?? '/_chat';
const outDir = path.join(dir, '_app', 'immutable', 'inline');

if (!fs.existsSync(path.join(dir, 'index.html'))) {
	console.error(`embed-postbuild: ${dir}/index.html not found (run vite build first)`);
	process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });

let total = 0;
for (const f of fs.readdirSync(dir).filter((f) => f.endsWith('.html'))) {
	const p = path.join(dir, f);
	let html = fs.readFileSync(p, 'utf8');
	let n = 0;
	// <script> without attributes = inline classic script (type="module" etc. are left alone)
	html = html.replace(/<script>([\s\S]*?)<\/script>/g, (_, body) => {
		const h = crypto.createHash('sha256').update(body).digest('hex').slice(0, 16);
		const name = `${h}.js`;
		fs.writeFileSync(path.join(outDir, name), body);
		n++;
		return `<script src="${base}/_app/immutable/inline/${name}"></script>`;
	});
	const remaining = (html.match(/<script(?![^>]*\bsrc=)[^>]*>/g) ?? []).length;
	const handlers = (html.match(/\son[a-z]+=["']/g) ?? []).length;
	fs.writeFileSync(p, html);
	total += n;
	console.log(
		`embed-postbuild ${f}: externalized ${n} inline scripts; remaining inline scripts ${remaining}, inline handlers ${handlers}`
	);
	if (remaining || handlers) process.exitCode = 1;
}
if (!fs.existsSync(path.join(dir, 'embed', 'artifact-frame.html'))) {
	console.error('embed-postbuild: build/embed/artifact-frame.html missing (static/embed not copied?)');
	process.exitCode = 1;
}
console.log(`embed-postbuild: ${total} scripts written to ${path.relative(process.cwd(), outDir)}`);
