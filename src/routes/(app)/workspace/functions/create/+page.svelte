<script lang="ts">
	import { goto } from '$lib/embed/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto('/admin/functions/create', { replaceState: true });
	});
</script>
