// sub2api model picker: compact one-line form of the gateway's `price_text`.
//
// The full text (contract C, `/__sub2api/model-prices`) mirrors the model plaza and can be long:
//   token:        `输入 ¥0.56 / 百万 tokens · 输出 ¥3.36 / 百万 tokens`
//   token tiers:  `0–272000 tokens：<token>；≥272000 tokens：<token>`
//   image / call: `1K：¥0.15 / 张；2K：¥0.15 / 张；4K：¥0.30 / 张`  (or `¥0.02 / 次`)
//   time pricing: `标准时段：<any of the above>；工作日 09:00–18:00 (Asia/Shanghai)：<…>`
// Segments are separated by `；`, labels end with a full-width `：`, and the price body itself never
// contains `：` (time labels use an ASCII `:`), so the body is whatever follows the last `：`.
//
// Rules (the picker shows the full text on hover):
//   - every segment is a flat price `¥x / unit` with the same unit (image tiers, per-call tiers,
//     time periods): one price → `¥x / unit`; differing prices → `¥min 起 / unit`
//   - otherwise the first segment, without its label(s); a token body whose parts share one unit
//     is folded to `输入 ¥a · 输出 ¥b / 百万 tokens`
//   - empty / non-string → ''; anything unrecognised falls through unchanged (CSS truncates it)

const SEGMENT_SEP = '；';
const LABEL_SEP = '：';
const FLAT_PRICE = /^¥(\S+) \/ (.+)$/;
const VALUE_UNIT = /^(.*?\S)\s*\/\s*(\S.*)$/;

const segmentBody = (segment: string) => segment.slice(segment.lastIndexOf(LABEL_SEP) + 1).trim();

/** `输入 ¥a / 百万 tokens · 输出 ¥b / 百万 tokens` → `输入 ¥a · 输出 ¥b / 百万 tokens` */
function foldSharedUnit(body: string): string {
	const parts = body.split(' · ').map((p) => VALUE_UNIT.exec(p.trim()));
	if (parts.length < 2 || parts.some((m) => !m)) return body;
	const unit = parts[0]![2];
	if (parts.some((m) => m![2] !== unit)) return body;
	return `${parts.map((m) => m![1]).join(' · ')} / ${unit}`;
}

/** Collapse flat `¥x / unit` segments; null when any segment is not flat or units differ. */
function collapseFlat(bodies: string[]): string | null {
	const flats = bodies.map((b) => FLAT_PRICE.exec(b));
	if (flats.some((m) => !m)) return null;
	const unit = flats[0]![2];
	if (flats.some((m) => m![2] !== unit)) return null;
	const values = flats.map((m) => m![1]);
	if (values.every((v) => v === values[0])) return `¥${values[0]} / ${unit}`;
	const numbers = values.map(Number);
	if (numbers.some((n) => !Number.isFinite(n))) return `¥${values[0]} / ${unit}`;
	const min = values[numbers.indexOf(Math.min(...numbers))];
	return `¥${min} 起 / ${unit}`;
}

export function compactPriceText(text: unknown): string {
	if (typeof text !== 'string') return '';
	const bodies = text
		.split(SEGMENT_SEP)
		.map(segmentBody)
		.filter((b) => b !== '');
	if (bodies.length === 0) return '';
	return collapseFlat(bodies) ?? foldSharedUnit(bodies[0]);
}
