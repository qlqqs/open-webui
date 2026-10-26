// Signup defaults are initialized once; normal user settings remain authoritative afterwards.
import { get } from 'svelte/store';
import { settings, models, user } from '$lib/stores';
import { getModels } from '$lib/apis';
import { updateUserSettings } from '$lib/apis/users';
import { localStorage } from './storage';
import { SUB2API_API, setKeySelection, fetchModelReasoning, type Sub2apiKey } from './keys';
import { toast } from 'svelte-sonner';
import i18next from 'i18next';
import { translate } from './i18n';

export type WorkbenchDefaults = {
	eligible: boolean;
	initialized: boolean;
	group_id: number;
	group_name: string;
	text_model: string;
	image_model: string;
	reasoning_effort: string;
};
export function defaultWorkbenchKey(keys: Sub2apiKey[], state: WorkbenchDefaults) {
	return keys
		.filter(
			(k) =>
				k.usable && k.supports_chat && k.group?.id === state.group_id && k.name === state.group_name
		)
		.sort((a, b) => a.id - b.id)[0];
}
export async function initializeWorkbench(keys: Sub2apiKey[]): Promise<void> {
	const owner = get(user)?.id;
	const res = await fetch(`${SUB2API_API}/workbench`, { credentials: 'same-origin' });
	if (!res.ok || get(user)?.id !== owner) return;
	const state: WorkbenchDefaults = await res.json();
	const original = get(settings) ?? {};
	if (
		!state.eligible ||
		original.sub2api_initialized ||
		original.sub2api !== undefined ||
		original.models?.length
	)
		return;
	const key = defaultWorkbenchKey(keys, state);
	const selection = key
		? { key_id: key.id, image_key_id: key.supports_images ? key.id : null }
		: { key_id: null, image_key_id: null };
	setKeySelection(selection);
	const available = key ? await getModels(localStorage.token) : [];
	const reasoning = key ? await fetchModelReasoning(key.id, [state.text_model]) : {};
	if (get(user)?.id !== owner || get(settings)?.sub2api !== undefined) return;
	const textAvailable =
		available.some((m: { id: string }) => m.id === state.text_model) &&
		reasoning[state.text_model]?.levels.includes(state.reasoning_effort);
	if (!textAvailable) selection.key_id = null;
	const next = {
		sub2api: selection,
		models: [state.text_model],
		sub2api_defaults: {
			text_model: state.text_model,
			image_model: state.image_model,
			reasoning_effort: state.reasoning_effort
		},
		sub2api_reasoning: { [state.text_model]: state.reasoning_effort }
	};
	const stored = await updateUserSettings(localStorage.token, {
		ui: next,
		sub2api_initialize: true
	});
	if (!stored?.ui) throw new Error(translate(i18next.language, 'defaults.saveFailed'));
	if (get(user)?.id !== owner) return;
	settings.update((s) => ({ ...s, ...stored.ui }));
	setKeySelection(stored.ui.sub2api);
	models.set(await getModels(localStorage.token));
	if (!key) toast.info(translate(i18next.language, 'guide.body'));
	else if (!textAvailable) {
		toast.info(translate(i18next.language, 'defaults.unavailable'));
	}
}
