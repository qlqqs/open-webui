<script lang="ts">
	// sub2api embed: copyright notice + LICENSE link kept as small print at the bottom of the
	// settings page while the About tab is hidden (PRD R7.1; LICENSE clause 1 / BRANDING.md).
	import { et } from './i18n';
</script>

<div
	class="mt-2 pt-2 border-t border-gray-100 dark:border-gray-850 text-[0.6875rem] leading-4 text-gray-400 dark:text-gray-500 flex flex-wrap gap-x-2 gap-y-0.5"
	data-testid="s2a-license-footer"
>
	<span>{$et('footer.copyright')}</span>
	<span
		>Copyright (c) 2023- Open WebUI Inc. All rights reserved.
		<a
			class="underline"
			href="https://github.com/open-webui/open-webui/blob/main/LICENSE"
			target="_blank"
			rel="noopener noreferrer">{$et('footer.license')}</a
		></span
	>
	<span
		>Emoji: <a
			class="underline"
			href="https://github.com/jdecked/twemoji"
			target="_blank"
			rel="noopener noreferrer">Twemoji</a
		>, CC-BY 4.0</span
	>
</div>
