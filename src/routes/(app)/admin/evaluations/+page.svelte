<script>
	import { goto } from '$lib/embed/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto('/admin/evaluations/leaderboard', { replaceState: true });
	});
</script>
