<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import '../app.css';
	import { connectWebSocket, disconnectWebSocket } from '$lib/stores/websocket';

	import type { Snippet } from 'svelte';

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	onMount(() => {
		connectWebSocket();
	});

	onDestroy(() => {
		disconnectWebSocket();
	});
</script>

{@render children()}
