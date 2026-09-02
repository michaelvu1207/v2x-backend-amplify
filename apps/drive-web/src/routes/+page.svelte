<script lang="ts">
	import { onMount } from 'svelte';
	import DashboardLayout from '$lib/components/DashboardLayout.svelte';
	import Header from '$lib/components/Header.svelte';
	import FeedGrid from '$lib/components/FeedGrid.svelte';
	import MapOverlay from '$lib/components/MapOverlay.svelte';
	import ObjectDetailPanel from '$lib/components/ObjectDetailPanel.svelte';
	import {
		objects,
		objectList,
		bridgeStatus,
		selectedObjectId,
		selectedObject
	} from '$lib/stores/objects';
	import { fetchMapData } from '$lib/api';
	import { loadRuntimeConfig } from '$lib/runtime-config';

	let roadLines = $state<number[][][]>([]);
	let loadError = $state<string | null>(null);

	onMount(async () => {
		await loadRuntimeConfig();
		try {
			// Fetch static map data (road network) — only needed once
			roadLines = await fetchMapData();
		} catch (err) {
			console.warn('Failed to load map data:', err);
			// Not fatal — objects will still load via polling
		}
	});

	function handleSelect(objectId: string) {
		selectedObjectId.set(objectId);
	}

	function handleCloseDetail() {
		selectedObjectId.set(null);
	}

	// Reactive reads from stores
	let currentObjects = $derived($objectList);
	let currentSelectedId = $derived($selectedObjectId);
	let currentSelectedObject = $derived($selectedObject);
</script>

<svelte:head>
	<title>V2X Drive</title>
</svelte:head>

<DashboardLayout>
	{#snippet header()}
		<Header />
	{/snippet}

	{#snippet grid()}
		{#if loadError}
			<div class="flex h-full flex-col items-center justify-center gap-3 p-8">
				<svg class="h-12 w-12 text-red-500/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
				</svg>
				<p class="text-sm font-medium text-red-400">Failed to load data</p>
				<p class="text-xs text-gray-500">{loadError}</p>
				<button
					onclick={() => location.reload()}
					class="mt-2 rounded-lg bg-gray-800 px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-gray-700"
				>
					Retry
				</button>
			</div>
		{:else}
			<FeedGrid objects={currentObjects} onselect={handleSelect} />
		{/if}
	{/snippet}

	{#snippet map()}
		<MapOverlay
			objects={currentObjects}
			{roadLines}
			selectedId={currentSelectedId}
			onselect={handleSelect}
		/>
	{/snippet}

	{#snippet detail()}
		<ObjectDetailPanel
			object={currentSelectedObject}
			onClose={handleCloseDetail}
		/>
	{/snippet}
</DashboardLayout>
