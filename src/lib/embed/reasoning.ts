// sub2api embed: thinking-effort picker state. The levels per model come from sub2api
// (`/__sub2api/model-reasoning`, capped by the key's group); the user's choice is remembered per
// model in this browser and sent as `params.reasoning_effort`. No choice = the gateway default.
import { derived, get, writable, type Readable } from 'svelte/store';
import { localStorage } from './storage';
import { fetchModelReasoning, type ModelReasoning } from './keys';
import type { EmbedStringKey } from './i18n';

export const REASONING_STORAGE_KEY = 's2a:reasoning';

/** model id → effort levels for the selected chat key (models without a choice are absent) */
export const modelReasoning = writable<Record<string, ModelReasoning>>({});

let syncedFor = '';
/**
 * Load levels for the composer's model list under the chat key. Repeated calls with the same
 * key and models are no-ops; a failed load hides the picker rather than guessing.
 */
export async function syncModelReasoning(keyId: number | null, modelIds: string[]): Promise<void> {
	const ids = [...new Set(modelIds.filter(Boolean))].sort();
	const tag = keyId === null || ids.length === 0 ? '' : `${keyId}:${ids.join('\n')}`;
	if (tag === syncedFor) return;
	syncedFor = tag;
	if (!tag) {
		modelReasoning.set({});
		return;
	}
	try {
		const levels = await fetchModelReasoning(keyId as number, ids);
		if (syncedFor === tag) modelReasoning.set(levels);
	} catch {
		if (syncedFor === tag) modelReasoning.set({});
	}
}

const load = (): Record<string, string> => {
	try {
		const raw = JSON.parse(localStorage.getItem(REASONING_STORAGE_KEY) ?? '{}');
		if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
		return Object.fromEntries(
			Object.entries(raw).filter(([, v]) => typeof v === 'string' && v)
		) as Record<string, string>;
	} catch {
		return {};
	}
};

/** model id → chosen reasoning_effort */
export const reasoningChoices = writable<Record<string, string>>(load());

export function setReasoningChoice(modelId: string, level: string): void {
	reasoningChoices.update((choices) => {
		const next = { ...choices, [modelId]: level };
		try {
			localStorage.setItem(REASONING_STORAGE_KEY, JSON.stringify(next));
		} catch {
			// storage full or blocked: the choice still applies for this page
		}
		return next;
	});
}

/** The stored choice, if the model (under the current key) still offers it. */
export function chosenEffort(
	reasoning: ModelReasoning | undefined,
	choice: string | undefined
): string | undefined {
	return reasoning && choice && reasoning.levels.includes(choice) ? choice : undefined;
}

/** Model ids as sub2api knows them: custom models resolve to their base model. */
export const reasoningModelId = (model: {
	id: string;
	info?: { base_model_id?: string | null } | null;
}): string => model.info?.base_model_id ?? model.id;

export type ReasoningState = {
	modelId: string;
	reasoning: ModelReasoning;
	/** explicit choice still valid for this model, undefined = gateway default */
	chosen?: string;
	/** level the slider shows: the choice, else the default, else the middle level */
	current: string;
};

export function reasoningState(
	modelId: string,
	reasoning: ModelReasoning | undefined,
	choice: string | undefined
): ReasoningState | null {
	if (!reasoning || reasoning.levels.length < 2) return null;
	const chosen = chosenEffort(reasoning, choice);
	const fallback =
		reasoning.default && reasoning.levels.includes(reasoning.default)
			? reasoning.default
			: reasoning.levels[Math.floor((reasoning.levels.length - 1) / 2)];
	return { modelId, reasoning, chosen, current: chosen ?? fallback };
}

export const reasoningFor = (modelId: string | null | undefined): Readable<ReasoningState | null> =>
	derived([modelReasoning, reasoningChoices], ([$reasoning, $choices]) =>
		modelId ? reasoningState(modelId, $reasoning[modelId], $choices[modelId]) : null
	);

/** Extra chat params for one model's request; empty when there is nothing to send. */
export function reasoningParams(modelId: string): { reasoning_effort?: string } {
	const effort = chosenEffort(get(modelReasoning)[modelId], get(reasoningChoices)[modelId]);
	return effort ? { reasoning_effort: effort } : {};
}

const LABELLED = new Set(['minimal', 'low', 'medium', 'high', 'xhigh', 'max']);

/** i18n key for a level, or null for values without a translation (shown raw). */
export const reasoningLevelKey = (level: string): EmbedStringKey | null =>
	LABELLED.has(level) ? (`reasoning.level.${level}` as EmbedStringKey) : null;
