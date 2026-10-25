<script lang="ts">
	// sub2api embed: replaces the avatar menu at the bottom of the sidebar (PRD R7.4). No account,
	// sign-out or profile entries: identity belongs to the console.
	import { goto } from './navigation';
	import { showSettings, showSidebar, mobile, user } from '$lib/stores';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Settings from '$lib/components/icons/Settings.svelte';
	import WrenchAlt from '$lib/components/icons/WrenchAlt.svelte';
	import { et } from './i18n';

	export let collapsed = false;

	const openSettings = () => {
		showSettings.set(true);
		if ($mobile) showSidebar.set(false);
	};
	const openPlugins = () => {
		goto('/admin/functions');
		if ($mobile) showSidebar.set(false);
	};

	const rowClass =
		'flex items-center gap-2.5 rounded-xl py-1.5 px-2 w-full text-left hover:bg-gray-100 dark:hover:bg-gray-900 transition';
	const iconClass =
		'flex size-8.5 items-center justify-center rounded-lg transition hover:bg-gray-100 dark:hover:bg-gray-900';
</script>

{#if collapsed}
	<div class="flex flex-col items-center gap-0.5" data-testid="s2a-sidebar-settings">
		{#if $user?.role === 'admin'}
			<Tooltip content={$et('settings.plugins')} placement="right">
				<button type="button" class={iconClass} aria-label={$et('settings.plugins')} on:click={openPlugins}>
					<WrenchAlt className="size-4" strokeWidth="1.5" />
				</button>
			</Tooltip>
		{/if}
		<Tooltip content={$et('settings.button')} placement="right">
			<button type="button" class={iconClass} aria-label={$et('settings.button')} on:click={openSettings}>
				<Settings className="size-4" strokeWidth="1.5" />
			</button>
		</Tooltip>
	</div>
{:else}
	<div class="flex flex-col gap-0.5" data-testid="s2a-sidebar-settings">
		{#if $user?.role === 'admin'}
			<button type="button" class={rowClass} on:click={openPlugins}>
				<WrenchAlt className="size-4" strokeWidth="1.5" />
				<span class="text-[0.8125rem] leading-5">{$et('settings.plugins')}</span>
			</button>
		{/if}
		<button type="button" class={rowClass} on:click={openSettings}>
			<Settings className="size-4" strokeWidth="1.5" />
			<span class="text-[0.8125rem] leading-5">{$et('settings.button')}</span>
		</button>
	</div>
{/if}
