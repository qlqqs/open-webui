<script lang="ts">
	import { goto } from '$lib/embed/navigation';
	import { onMount } from 'svelte';
	import { isEmbedMode } from '$lib/embed/mode'; // sub2api-embed

	onMount(() => {
		// sub2api-embed: only functions / tools / tool servers are administered here
		goto(isEmbedMode() ? '/admin/functions' : '/admin/users', { replaceState: true });
	});
</script>
