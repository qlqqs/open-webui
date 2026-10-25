<script lang="ts">
	// sub2api embed: ChatGPT-style thinking-effort pill in the composer. The popover shows the
	// level name and a stepped slider (lowest left, highest right); the name toggles a plain
	// list of levels for precise picking. Hidden when the model has no levels to choose from.
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import { et } from './i18n';
	import { reasoningFor, reasoningLevelKey, setReasoningChoice } from './reasoning';

	export let modelId: string | null = null;

	let show = false;
	let listView = false;
	/** index shown while dragging; committed on release */
	let dragIndex: number | null = null;
	let track: HTMLDivElement | null = null;

	$: picker = reasoningFor(modelId);
	$: levels = $picker?.reasoning.levels ?? [];
	$: currentIndex = Math.max(0, levels.indexOf($picker?.current ?? ''));
	$: index = dragIndex ?? currentIndex;
	$: shown = levels[index] ?? '';
	$: last = Math.max(1, levels.length - 1);
	$: if (!show) {
		listView = false;
		dragIndex = null;
	}

	const label = (level: string) => {
		const key = reasoningLevelKey(level);
		return key ? $et(key) : level;
	};
	const multiplier = (level: string) => {
		const n = $picker?.reasoning.multipliers?.[level];
		return n && n !== 1 ? $et('reasoning.multiplier', { n: +n.toFixed(4) }) : '';
	};

	const commit = (i: number) => {
		const level = levels[Math.min(levels.length - 1, Math.max(0, i))];
		if ($picker && level && level !== $picker.chosen) setReasoningChoice($picker.modelId, level);
	};

	// Thumb centres sit `inset` from each end so the end stops stay inside the track.
	const inset = '0.875rem';
	const at = (i: number) => `calc(${inset} + (100% - 2 * ${inset}) * ${i / last})`;

	const indexFromPointer = (e: PointerEvent) => {
		if (!track) return index;
		const rect = track.getBoundingClientRect();
		const pad = 14;
		const ratio = (e.clientX - rect.left - pad) / Math.max(1, rect.width - 2 * pad);
		return Math.round(Math.min(1, Math.max(0, ratio)) * last);
	};
	const onPointerDown = (e: PointerEvent) => {
		if (e.button !== 0) return;
		e.preventDefault();
		track?.setPointerCapture(e.pointerId);
		track?.focus();
		dragIndex = indexFromPointer(e);
	};
	const onPointerMove = (e: PointerEvent) => {
		if (dragIndex !== null) dragIndex = indexFromPointer(e);
	};
	const onPointerUp = (e: PointerEvent) => {
		if (dragIndex === null) return;
		const i = indexFromPointer(e);
		dragIndex = null;
		commit(i);
	};
	const onKeydown = (e: KeyboardEvent) => {
		const next =
			e.key === 'ArrowLeft' || e.key === 'ArrowDown'
				? index - 1
				: e.key === 'ArrowRight' || e.key === 'ArrowUp'
					? index + 1
					: e.key === 'Home'
						? 0
						: e.key === 'End'
							? levels.length - 1
							: null;
		if (next === null) return;
		e.preventDefault();
		e.stopPropagation();
		commit(next);
	};
	const pick = (level: string) => {
		commit(levels.indexOf(level));
		show = false;
	};
</script>

{#if $picker}
	<Dropdown
		bind:show
		align="end"
		visualViewportAware
		contentClass="z-50 w-64 max-w-[calc(100vw-1rem)] rounded-2xl border border-gray-100 bg-white p-3 text-gray-800 shadow-lg outline-hidden dark:border-gray-800 dark:bg-gray-850 dark:text-gray-100"
	>
		<button
			type="button"
			data-testid="s2a-reasoning-trigger"
			aria-haspopup="dialog"
			aria-expanded={show}
			class="mr-1 flex h-8 shrink-0 items-center gap-1 self-center rounded-full px-3 text-[0.8125rem] text-gray-600 transition-colors duration-100 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-100 {show
				? 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-100'
				: ''}"
		>
			<span class="max-w-[7rem] truncate">
				{$picker.chosen ? label($picker.chosen) : $et('reasoning.title')}
			</span>
			<svg
				class="size-3.5 shrink-0 opacity-70 transition-transform {show ? 'rotate-180' : ''}"
				aria-hidden="true"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
			</svg>
		</button>

		<div slot="content" data-testid="s2a-reasoning-menu">
			<button
				type="button"
				class="mx-auto flex items-center gap-0.5 rounded-lg px-2 py-1 text-[0.9375rem] font-medium transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
				aria-label={listView ? $et('reasoning.showSlider') : $et('reasoning.showLevels')}
				aria-expanded={listView}
				on:click={() => (listView = !listView)}
			>
				<span>{label(shown)}</span>
				<svg
					class="size-3.5 opacity-60 transition-transform {listView ? 'rotate-90' : ''}"
					aria-hidden="true"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
				</svg>
			</button>

			{#if listView}
				<div role="listbox" aria-label={$et('reasoning.title')} class="mt-2 flex flex-col gap-0.5">
					{#each levels as level (level)}
						<button
							type="button"
							role="option"
							data-level={level}
							aria-selected={level === $picker.current}
							class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[0.8125rem] transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 {level ===
							$picker.current
								? 'bg-gray-50 dark:bg-gray-800'
								: ''}"
							on:click={() => pick(level)}
						>
							<span class="min-w-0 flex-1 truncate">{label(level)}</span>
							{#if multiplier(level)}
								<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400"
									>{multiplier(level)}</span
								>
							{/if}
							{#if level === $picker.reasoning.default}
								<span class="shrink-0 text-xs text-gray-400 dark:text-gray-500"
									>{$et('reasoning.default')}</span
								>
							{/if}
							<span class="flex size-3.5 shrink-0 items-center justify-center">
								{#if level === $picker.current}
									<svg
										class="size-3.5"
										aria-hidden="true"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="2.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="m4.5 12.75 6 6 9-13.5"
										/>
									</svg>
								{/if}
							</span>
						</button>
					{/each}
				</div>
			{:else}
				<div
					bind:this={track}
					role="slider"
					tabindex="0"
					data-testid="s2a-reasoning-slider"
					aria-label={$et('reasoning.slider')}
					aria-valuemin={0}
					aria-valuemax={levels.length - 1}
					aria-valuenow={index}
					aria-valuetext={label(shown)}
					class="relative mt-3 h-7 w-full cursor-pointer touch-none select-none rounded-full bg-gray-100 outline-hidden focus-visible:ring-2 focus-visible:ring-blue-500/50 dark:bg-gray-800"
					on:pointerdown={onPointerDown}
					on:pointermove={onPointerMove}
					on:pointerup={onPointerUp}
					on:pointercancel={() => (dragIndex = null)}
					on:keydown={onKeydown}
				>
					<div
						class="absolute inset-y-0 left-0 rounded-full bg-blue-600 {dragIndex === null
							? 'transition-[width] duration-150'
							: ''}"
						style:width="calc({at(index)} + {inset})"
					></div>
					{#each levels as level, i (level)}
						<span
							class="pointer-events-none absolute top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full {i <=
							index
								? 'bg-white/70'
								: 'bg-gray-400 dark:bg-gray-500'}"
							style:left={at(i)}
						></span>
					{/each}
					<span
						class="pointer-events-none absolute top-1/2 size-8 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-md ring-1 ring-black/5 {dragIndex ===
						null
							? 'transition-[left] duration-150'
							: ''}"
						style:left={at(index)}
					></span>
				</div>
				{#if multiplier(shown)}
					<div class="mt-2 text-center text-xs text-gray-500 dark:text-gray-400">
						{multiplier(shown)}
					</div>
				{/if}
			{/if}
		</div>
	</Dropdown>
{/if}
