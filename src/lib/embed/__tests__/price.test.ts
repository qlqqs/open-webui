import { describe, expect, it } from 'vitest';

import { compactPriceText } from '../price';

const TOKEN_TIERS =
	'0–272000 tokens：输入 ¥0.56 / 百万 tokens · 输出 ¥3.36 / 百万 tokens；≥272000 tokens：输入 ¥1.12 / 百万 tokens · 输出 ¥5.04 / 百万 tokens';

describe('compactPriceText', () => {
	it('returns empty for missing or blank values', () => {
		expect(compactPriceText(undefined)).toBe('');
		expect(compactPriceText(null)).toBe('');
		expect(compactPriceText(12)).toBe('');
		expect(compactPriceText('')).toBe('');
		expect(compactPriceText('  ')).toBe('');
		expect(compactPriceText('；')).toBe('');
	});

	it('folds the shared unit of a single token segment', () => {
		expect(compactPriceText('输入 ¥0.56 / 百万 tokens · 输出 ¥3.36 / 百万 tokens')).toBe(
			'输入 ¥0.56 · 输出 ¥3.36 / 百万 tokens'
		);
		expect(compactPriceText('输入 ¥2.00 / 百万 tokens')).toBe('输入 ¥2.00 / 百万 tokens');
		expect(compactPriceText('输入 ¥1e-7 / 百万 tokens · 输出 ¥0.30 / 百万 tokens')).toBe(
			'输入 ¥1e-7 · 输出 ¥0.30 / 百万 tokens'
		);
	});

	it('shows only the first token tier without its range label', () => {
		expect(compactPriceText(TOKEN_TIERS)).toBe('输入 ¥0.56 · 输出 ¥3.36 / 百万 tokens');
	});

	it('uses the standard period of time-based pricing', () => {
		expect(
			compactPriceText(
				`标准时段：${TOKEN_TIERS}；工作日 09:00–18:00 (Asia/Shanghai)：0–272000 tokens：输入 ¥1.12 / 百万 tokens · 输出 ¥6.72 / 百万 tokens`
			)
		).toBe('输入 ¥0.56 · 输出 ¥3.36 / 百万 tokens');
	});

	it('collapses per-image tiers with one price', () => {
		expect(compactPriceText('1K：¥0.15 / 张；2K：¥0.15 / 张；4K：¥0.15 / 张')).toBe('¥0.15 / 张');
		expect(compactPriceText('¥0.15 / 张')).toBe('¥0.15 / 张');
		expect(compactPriceText('¥0.02 / 次')).toBe('¥0.02 / 次');
	});

	it('shows the lowest per-image tier with 起 when prices differ', () => {
		expect(compactPriceText('1K：¥0.30 / 张；2K：¥0.15 / 张；4K：¥0.60 / 张')).toBe(
			'¥0.15 起 / 张'
		);
		expect(
			compactPriceText(
				'标准时段：1K：¥0.15 / 张；2K：¥0.20 / 张；00:00–08:00 (UTC)：1K：¥0.075 / 张'
			)
		).toBe('¥0.075 起 / 张');
	});

	it('falls back to the first segment body for mixed or unknown formats', () => {
		expect(compactPriceText('1K：¥0.15 / 张；2K：¥0.15 / 次')).toBe('¥0.15 / 张');
		expect(compactPriceText('- / 张')).toBe('- / 张');
		expect(compactPriceText('按量计费')).toBe('按量计费');
	});
});
