<script lang="ts">
	import type { TrackedObject } from '$lib/types';
	import FeedCell from './FeedCell.svelte';

	interface Props {
		objects: TrackedObject[];
		onselect?: (objectId: string) => void;
	}

	let { objects, onselect }: Props = $props();
</script>

{#if objects.length > 0}
	<div
		class="grid gap-2 p-2"
		style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));"
	>
		{#each objects as object (object.object_id)}
			<FeedCell {object} {onselect} />
		{/each}
	</div>
{:else}
	<div class="flex h-full flex-col items-center justify-center gap-3 p-8">
		<svg class="h-16 w-16 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
			<path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
		</svg>
		<p class="text-sm font-medium text-gray-500">No objects tracked</p>
		<p class="text-xs text-gray-600">
			Waiting for data from CARLA simulator...
		</p>
	</div>
{/if}
