<script lang="ts">
	// sub2api embed: gateway errors in Chinese with the matching action (PRD R6.2).
	import { showSettings } from '$lib/stores';
	import { et } from './i18n';
	import { navigateConsole } from './bridge';
	import { ACTION_PATHS, type MappedGatewayError } from './errors';

	export let mapped: MappedGatewayError;
	export let raw = '';

	const act = () => {
		if (mapped.action === 'settings') showSettings.set('sub2api');
		else if (mapped.action) navigateConsole(ACTION_PATHS[mapped.action]);
	};

	$: actionLabel =
		mapped.action === 'purchase'
			? $et('error.purchase')
			: mapped.action === 'keys'
				? $et('error.keys')
				: mapped.action === 'settings'
					? $et('error.settings')
					: '';
</script>

<div class="min-w-0 break-words text-[0.8125rem] leading-5" data-testid="s2a-gateway-error" data-kind={mapped.kind}>
	<div class="text-gray-700 dark:text-gray-200">{mapped.original || $et(mapped.messageKey)}</div>
	{#if actionLabel}
		<button type="button" class="s2a-btn-primary mt-1.5 !py-1" on:click={act}>{actionLabel}</button>
	{/if}
	{#if raw && raw !== mapped.original}
		<details class="mt-1 text-xs text-gray-400 dark:text-gray-500">
			<summary class="cursor-pointer select-none">{$et('error.detail')}</summary>
			<div class="mt-0.5 font-mono break-all">{raw}</div>
		</details>
	{/if}
</div>
