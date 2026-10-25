<script lang="ts">
	// sub2api embed: settings tab 「模型与密钥」 (replaces Connections in embed mode, PRD R5).
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { localStorage } from './storage';
	import { models, settings } from '$lib/stores';
	import { getModels } from '$lib/apis';
	import { updateUserSettings } from '$lib/apis/users';
	import { et } from './i18n';
	import type { EmbedStringKey } from './i18n';
	import { navigateConsole } from './bridge';
	import {
		chatKeyOptions,
		createKey,
		fetchGroups,
		imageKeyOptions,
		newKeyName,
		normalizeSelection,
		refreshKeys,
		refreshModelPrices,
		resolveKeys,
		setKeySelection,
		defaultCreateGroup,
		sub2apiKeys,
		sub2apiKeysError,
		type Sub2apiGroup,
		type Sub2apiKey
	} from './keys';

	let loading = true;
	let saving = false;
	let creating = false;
	let groups: Sub2apiGroup[] = [];
	let groupId: number | null = null;

	$: keys = $sub2apiKeys ?? [];
	$: ui = ($settings ?? {}) as Record<string, unknown>;
	$: selection = normalizeSelection(ui.sub2api);
	$: resolved = resolveKeys(keys, ui.sub2api);
	$: chatOptions = chatKeyOptions(keys);
	$: imageOptions = imageKeyOptions(keys);
	$: hasUsableChatKey = chatOptions.some((o) => !o.reason);
	$: selectedChat = keys.find((k) => k.id === selection.key_id) ?? null;

	const KNOWN_REASONS = new Set(['disabled', 'expired', 'quota_exhausted', 'group_unavailable', 'no_chat']);
	const reasonText = (reason: string) =>
		$et((KNOWN_REASONS.has(reason) ? `keys.reason.${reason}` : 'keys.reason.unknown') as EmbedStringKey);

	const optionLabel = (key: Sub2apiKey, reason: string) =>
		`${key.name}${key.group ? ` · ${key.group.name}` : ''}${key.masked ? ` (${key.masked})` : ''}${
			reason ? ` — ${reasonText(reason)}` : ''
		}`;

	const formatDate = (iso: string) => {
		const d = new Date(iso);
		return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
	};

	const save = async (next: { key_id: number | null; image_key_id: number | null }) => {
		saving = true;
		try {
			await updateUserSettings(localStorage.token, { ui: { sub2api: next } });
			settings.update((s) => ({ ...(s ?? {}), sub2api: next }));
			setKeySelection(next);
			if (next.key_id) toast.dismiss('s2a-key-guide');
			toast.success($et('keys.saved'));
			// the model list and prices depend on the chat key
			models.set(await getModels(localStorage.token));
			await refreshModelPrices(next.key_id, true);
		} catch (e) {
			toast.error($et('keys.saveFailed', { error: String((e as Error)?.message ?? e) }));
		} finally {
			saving = false;
		}
	};

	const onChatChange = (e: Event) => {
		const v = Number((e.currentTarget as HTMLSelectElement).value);
		save({ key_id: v > 0 ? v : null, image_key_id: selection.image_key_id });
	};
	const onImageChange = (e: Event) => {
		const v = Number((e.currentTarget as HTMLSelectElement).value);
		save({ key_id: selection.key_id, image_key_id: v > 0 ? v : null });
	};

	const create = async () => {
		if (!groupId) return;
		creating = true;
		try {
			const key = await createKey(newKeyName(keys, $et('keys.defaultName')), groupId);
			await refreshKeys();
			toast.success($et('keys.created', { name: key.name }));
			await save({ key_id: key.id, image_key_id: selection.image_key_id });
		} catch (e) {
			toast.error($et('keys.createFailed', { error: String((e as Error)?.message ?? e) }));
		} finally {
			creating = false;
		}
	};

	onMount(async () => {
		await refreshKeys();
		try {
			groups = await fetchGroups();
			groupId = defaultCreateGroup(groups)?.id ?? null;
		} catch {
			groups = [];
		}
		loading = false;
	});
</script>

<div class="flex flex-col h-full justify-between text-sm" id="tab-sub2api">
	<div class="overflow-y-auto scrollbar-hidden h-full pr-1">
		<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-1">{$et('keys.title')}</h2>
		<p class="text-xs s2a-muted mb-4">{$et('keys.intro')}</p>

		{#if loading && $sub2apiKeys === null}
			<div class="text-xs s2a-muted">{$et('keys.loading')}</div>
		{:else}
			{#if $sub2apiKeysError}
				<div class="text-xs text-red-600 dark:text-red-400 mb-3">
					{$et('keys.loadFailed', { error: $sub2apiKeysError })}
				</div>
			{/if}

			{#if !hasUsableChatKey}
				<div class="s2a-card p-3 mb-4" data-testid="s2a-create-key">
					<div class="text-[0.8125rem] mb-2">{$et('keys.empty')}</div>
					{#if groups.length > 0}
						<div class="flex flex-wrap items-center gap-2">
							<select class="s2a-select !w-auto max-w-full" bind:value={groupId} aria-label="group">
								{#each groups as group (group.id)}
									<option value={group.id}>{$et('keys.createIn', { group: group.name })}</option>
								{/each}
							</select>
							<button class="s2a-btn-primary" disabled={creating || !groupId} on:click={create}>
								{creating ? $et('keys.creating') : $et('keys.create')}
							</button>
						</div>
					{/if}
				</div>
			{/if}

			<div class="mb-5">
				<label class="block text-[0.8125rem] font-medium mb-1.5" for="s2a-chat-key"
					>{$et('keys.chat')}</label
				>
				<select
					id="s2a-chat-key"
					class="s2a-select"
					value={selection.key_id ?? 0}
					disabled={saving}
					on:change={onChatChange}
				>
					<option value={0} disabled>{$et('keys.placeholder')}</option>
					{#each chatOptions as option (option.key.id)}
						<option value={option.key.id} disabled={!!option.reason && option.key.id !== selection.key_id}
							>{optionLabel(option.key, option.reason)}</option
						>
					{/each}
				</select>
				<div class="text-xs s2a-muted mt-1.5">{$et('keys.chatHint')}</div>
				{#if resolved.chatKeyProblem}
					<div class="text-xs text-amber-600 dark:text-amber-400 mt-1">
						{$et('keys.selectedUnusable', { reason: reasonText(resolved.chatKeyProblem) })}
					</div>
				{/if}
				{#if selectedChat}
					<div class="text-xs s2a-muted mt-1 flex flex-wrap gap-x-3">
						<span
							>{selectedChat.group
								? $et('keys.group', { group: selectedChat.group.name })
								: $et('keys.noGroup')}</span
						>
						{#if (selectedChat.quota ?? 0) > 0}
							<span
								>{$et('keys.quota', {
									used: (selectedChat.quota_used ?? 0).toFixed(2),
									quota: (selectedChat.quota ?? 0).toFixed(2)
								})}</span
							>
						{/if}
						{#if selectedChat.expires_at}
							<span>{$et('keys.expires', { date: formatDate(selectedChat.expires_at) })}</span>
						{/if}
					</div>
				{/if}
			</div>

			<div class="mb-5">
				<label class="block text-[0.8125rem] font-medium mb-1.5" for="s2a-image-key"
					>{$et('keys.image')}</label
				>
				<select
					id="s2a-image-key"
					class="s2a-select"
					value={selection.image_key_id ?? 0}
					disabled={saving}
					on:change={onImageChange}
				>
					<option value={0}>{$et('keys.imageNone')}</option>
					{#each imageOptions as option (option.key.id)}
						<option
							value={option.key.id}
							disabled={!!option.reason && option.key.id !== selection.image_key_id}
							>{optionLabel(option.key, option.reason)}</option
						>
					{/each}
				</select>
				<div class="text-xs s2a-muted mt-1.5">{$et('keys.imageHint')}</div>
				<div class="text-xs mt-1" data-testid="s2a-image-status">
					{#if resolved.imageKey}
						{$et('keys.imageReady', { name: resolved.imageKey.name })}
					{:else}
						<span class="s2a-muted">{$et('keys.imageUnavailable')}</span>
					{/if}
				</div>
			</div>

			<button class="s2a-btn-outline" type="button" on:click={() => navigateConsole('/keys')}>
				{$et('keys.manage')}
			</button>
		{/if}
	</div>
</div>
