<script context="module" lang="ts">
	export type KeyPickerOption = {
		value: number;
		title: string;
		subtitle?: string;
		/** Shown as a warning tag; the row stays selectable only when it is the current value. */
		reason?: string;
		disabled?: boolean;
	};
</script>

<script lang="ts">
	// sub2api embed: key dropdown for 「模型与密钥」, replacing the native <select>.
	// Each row shows the key name, its group and masked key on a second line, and why it is unusable.
	import Dropdown from '$lib/components/common/Dropdown.svelte';

	export let id: string;
	export let value: number | null;
	export let options: KeyPickerOption[] = [];
	export let placeholder: string;
	/** Row for "no key", e.g. 「不单独设置」; omitted when null. */
	export let noneLabel: string | null = null;
	export let disabled = false;
	export let onChange: (value: number | null) => void = () => {};

	let show = false;
	let triggerWidth = 0;
	let active = -1;
	let triggerEl: HTMLButtonElement | null = null;

	$: rows = [
		...(noneLabel !== null ? [{ value: 0, title: noneLabel } as KeyPickerOption] : []),
		...options
	];
	$: current = options.find((o) => o.value === value) ?? null;

	const selectable = (i: number) => i >= 0 && i < rows.length && !rows[i].disabled;

	const pick = (row: KeyPickerOption) => {
		if (row.disabled) return;
		show = false;
		const next = row.value > 0 ? row.value : null;
		if (next !== value) onChange(next);
	};

	const move = (step: number) => {
		if (rows.length === 0) return;
		let i = active;
		for (let n = 0; n < rows.length; n++) {
			i = (i + step + rows.length) % rows.length;
			if (selectable(i)) {
				active = i;
				return;
			}
		}
	};

	$: if (show)
		active = Math.max(
			0,
			rows.findIndex((r) => r.value === (value ?? 0))
		);

	// Captured on window so Escape closes only this menu, not the settings modal behind it.
	const onKeydown = (e: KeyboardEvent) => {
		if (!show) return;
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			move(e.key === 'ArrowDown' ? 1 : -1);
		} else if (e.key === 'Enter') {
			if (selectable(active)) pick(rows[active]);
		} else if (e.key === 'Escape') {
			show = false;
		} else {
			return;
		}
		e.preventDefault();
		e.stopImmediatePropagation();
		if (!show) triggerEl?.focus();
	};
</script>

<svelte:window on:keydown|capture={onKeydown} />

<div class="w-full" bind:clientWidth={triggerWidth}>
	<Dropdown bind:show contentClass="s2a-key-menu" maxHeight="min(20rem, calc(100dvh - 2rem))">
		<button
			{id}
			bind:this={triggerEl}
			type="button"
			class="s2a-key-trigger"
			class:s2a-key-trigger-open={show}
			{disabled}
			data-value={value ?? 0}
			aria-haspopup="listbox"
			aria-expanded={show}
		>
			{#if current}
				<span class="flex min-w-0 flex-1 items-baseline gap-2">
					<span class="truncate font-medium">{current.title}</span>
					{#if current.subtitle}
						<span class="truncate text-xs s2a-muted">{current.subtitle}</span>
					{/if}
				</span>
			{:else}
				<span class="min-w-0 flex-1 truncate s2a-muted"
					>{value ? placeholder : (noneLabel ?? placeholder)}</span
				>
			{/if}
			<svg
				class="size-3.5 shrink-0 s2a-muted transition-transform {show ? 'rotate-180' : ''}"
				aria-hidden="true"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
			</svg>
		</button>

		<div
			slot="content"
			role="listbox"
			aria-labelledby={id}
			class="flex flex-col gap-0.5 p-1"
			style:width="{triggerWidth}px"
			data-testid="{id}-menu"
		>
			{#each rows as row, i (row.value)}
				<button
					type="button"
					role="option"
					data-value={row.value}
					aria-selected={row.value === (value ?? 0)}
					aria-disabled={row.disabled || undefined}
					class="s2a-key-option"
					class:s2a-key-option-active={i === active}
					class:s2a-key-option-disabled={row.disabled}
					on:mouseenter={() => {
						if (!row.disabled) active = i;
					}}
					on:click={() => pick(row)}
				>
					<span class="flex min-w-0 flex-1 flex-col">
						<span class="flex min-w-0 items-center gap-2">
							<span class="truncate {row.value > 0 ? 'font-medium' : 's2a-muted'}">{row.title}</span
							>
							{#if row.reason}
								<span class="s2a-key-reason">{row.reason}</span>
							{/if}
						</span>
						{#if row.subtitle}
							<span class="truncate text-xs s2a-muted">{row.subtitle}</span>
						{/if}
					</span>
					{#if row.value === (value ?? 0)}
						<svg
							class="size-4 shrink-0 text-[var(--s2a-blue,#1d4eff)]"
							aria-hidden="true"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
						</svg>
					{/if}
				</button>
			{/each}
		</div>
	</Dropdown>
</div>
