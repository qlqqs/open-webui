import { describe, expect, it } from 'vitest';
import { errorText, mapGatewayError } from '../errors';

const kind = (v: unknown) => mapGatewayError(v)?.kind ?? null;

describe('gateway error mapping', () => {
	it('recognises sub2api API key middleware errors', () => {
		expect(kind({ code: 'INSUFFICIENT_BALANCE', message: 'Insufficient account balance' })).toBe('balance');
		expect(kind('Insufficient account balance')).toBe('balance');
		expect(kind({ error: { type: 'insufficient_quota', message: 'API key 额度已用完' } })).toBe('keyQuota');
		expect(kind({ code: 'INVALID_API_KEY', message: 'Invalid API key' })).toBe('key');
		expect(kind('API key is disabled')).toBe('key');
		expect(kind({ code: 'API_KEY_EXPIRED', message: 'API key 已过期' })).toBe('key');
		expect(kind({ detail: '请选择可用的 Key' })).toBe('key');
		expect(kind({ code: 'USAGE_LIMIT_EXCEEDED', message: 'daily limit exceeded' })).toBe('usageLimit');
	});

	it('recognises rate limits, moderation and outages', () => {
		expect(kind({ error: { type: 'rate_limit_error', message: 'Concurrency limit exceeded for user, please retry later' } })).toBe('rateLimit');
		expect(kind('Too many pending requests, please retry later')).toBe('rateLimit');
		expect(kind({ error: { code: 'content_policy_violation', message: '内容审计命中风险规则，请调整输入后重试' } })).toBe('moderation');
		expect(kind({ error: { type: 'api_error', message: 'No available accounts' } })).toBe('unavailable');
		expect(kind('Service temporarily unavailable, please retry later')).toBe('unavailable');
		expect(kind({ error: { code: 'CHAT_SESSION_INVALID', message: '登录已失效' } })).toBe('session');
	});

	it('balance wins over the generic 403 wording', () => {
		expect(mapGatewayError('403: {"code":"INSUFFICIENT_BALANCE","message":"Insufficient account balance"}')?.action).toBe('purchase');
	});

	it('actions match the PRD (top up / keys / settings)', () => {
		expect(mapGatewayError('Insufficient account balance')?.action).toBe('purchase');
		expect(mapGatewayError('API key 额度已用完')?.action).toBe('keys');
		expect(mapGatewayError('Invalid API key')?.action).toBe('settings');
		expect(mapGatewayError('rate limit exceeded')?.action).toBeNull();
	});

	it('keeps the gateway\'s own Chinese moderation message', () => {
		const m = mapGatewayError({ error: { code: 'content_policy_violation', message: '内容审计命中风险规则，请调整输入后重试' } });
		expect(m?.original).toBe('内容审计命中风险规则，请调整输入后重试');
		expect(mapGatewayError('content moderation blocked this request')?.original).toBe('');
	});

	it('returns null for unrelated errors', () => {
		expect(kind('Uh-oh! There was an issue with the response.')).toBeNull();
		expect(kind('')).toBeNull();
		expect(kind(null)).toBeNull();
	});

	it('flattens nested payloads', () => {
		expect(errorText({ detail: { error: { message: 'x', code: 'y' } } })).toContain('x');
		expect(errorText({ error: { message: 'inner' } })).toBe('inner');
	});
});
