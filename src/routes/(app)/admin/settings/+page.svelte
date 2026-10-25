<script>
	import { goto } from '$lib/embed/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto('/?settings=admin%3Ageneral', { replaceState: true });
	});
</script>
