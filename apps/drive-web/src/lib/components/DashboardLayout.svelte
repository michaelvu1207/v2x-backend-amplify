<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		header: Snippet;
		grid: Snippet;
		map: Snippet;
		detail?: Snippet;
	}

	let { header, grid, map, detail }: Props = $props();
</script>

<div class="flex h-screen flex-col overflow-hidden bg-gray-950">
	<!-- Header -->
	{@render header()}

	<!-- Main content area -->
	<div class="flex min-h-0 flex-1 flex-col lg:flex-row">
		<!-- Left: Feed Grid -->
		<div class="min-h-0 flex-1 overflow-y-auto lg:w-[65%] lg:flex-none">
			{@render grid()}
		</div>

		<!-- Divider -->
		<div class="hidden w-px bg-gray-800 lg:block"></div>
		<div class="h-px bg-gray-800 lg:hidden"></div>

		<!-- Right: Map -->
		<div class="h-[300px] shrink-0 p-2 lg:h-auto lg:flex-1">
			{@render map()}
		</div>
	</div>

	<!-- Detail panel overlay -->
	{#if detail}
		{@render detail()}
	{/if}
</div>
