<script lang="ts">
	// sub2api embed: <iframe srcdoc> replacement for the strict CSP (contract F). The HTML is posted
	// into /_chat/embed/artifact-frame.html, which renders it in an opaque origin under its own CSP.
	import { createEventDispatcher, onDestroy, onMount } from 'svelte';
	import { artifactFrameUrl, artifactSandbox, isArtifactReady, renderMessage } from './artifact';

	export let html = '';
	export let sandbox: string | null | undefined = 'allow-scripts';
	export let title = '';
	export let className = '';
	export let style = '';
	export let autoHeight = false;
	export let allowFullscreen = false;
	export let iframe: HTMLIFrameElement | null = null;

	const dispatch = createEventDispatcher();

	$: policy = artifactSandbox(sandbox);
	// a new document per content version, like srcdoc did
	let version = 0;
	let lastHtml: string | null = null;
	$: if (html !== lastHtml) {
		lastHtml = html;
		version += 1;
	}

	let sentFor = -1;
	const send = () => {
		if (!iframe?.contentWindow || sentFor === version) return;
		sentFor = version;
		iframe.contentWindow.postMessage(renderMessage(lastHtml ?? '', policy.scripts, autoHeight), '*');
	};

	const onMessage = (event: MessageEvent) => {
		if (!iframe || event.source !== iframe.contentWindow) return;
		if (isArtifactReady(event.data)) send();
	};

	onMount(() => window.addEventListener('message', onMessage));
	onDestroy(() => window.removeEventListener('message', onMessage));
</script>

{#key version}
	<iframe
		bind:this={iframe}
		src={artifactFrameUrl()}
		{title}
		class={className}
		{style}
		sandbox={policy.sandbox}
		allowfullscreen={allowFullscreen}
		referrerpolicy="no-referrer"
		frameborder="0"
		width="100%"
		on:load={(e) => {
			send();
			dispatch('load', e);
		}}
	></iframe>
{/key}
