<script lang="ts">
	import Info from '$lib/components/icons/Info.svelte';
	// sub2api-embed: gateway errors in Chinese + 去充值 / 模型与密钥
	import GatewayErrorHint from '$lib/embed/GatewayErrorHint.svelte';
	import { embedMode } from '$lib/embed/mode';
	import { mapGatewayError } from '$lib/embed/errors';

	export let content: unknown = '';

	const getErrorMessage = (value: unknown): string => {
		if (typeof value === 'string') {
			return value;
		}

		if (typeof value === 'object' && value !== null) {
			const error = 'error' in value ? value.error : null;

			if (
				typeof error === 'object' &&
				error !== null &&
				'message' in error &&
				typeof error.message === 'string'
			) {
				return error.message;
			}

			if ('detail' in value && typeof value.detail === 'string') {
				return value.detail;
			}

			if ('message' in value && typeof value.message === 'string') {
				return value.message;
			}

			return JSON.stringify(value) ?? String(value);
		}

		return JSON.stringify(value) ?? String(value);
	};

	$: message = getErrorMessage(content) || 'Error submitting message';
	$: mapped = $embedMode ? mapGatewayError(content) : null;
</script>

<div
	class="my-1.5 flex w-full items-start gap-2 rounded-2xl bg-black/[0.03] px-3 py-2 text-gray-500 dark:bg-white/[0.04] dark:text-gray-400"
>
	<Info className="mt-0.5 size-4 shrink-0 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />

	{#if mapped}
		<GatewayErrorHint {mapped} raw={message} />
	{:else}
		<div class="min-w-0 break-words text-[0.8125rem] leading-5">
			{message}
		</div>
	{/if}
</div>
