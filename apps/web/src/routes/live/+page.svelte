<script lang="ts">
	import { onMount } from 'svelte';
	import Header from '$lib/components/Header.svelte';
	import LiveCameraPanel from '$lib/components/LiveCameraPanel.svelte';
	import LiveDetectionsPanel from '$lib/components/LiveDetectionsPanel.svelte';
	import RecentDetectionsPanel from '$lib/components/RecentDetectionsPanel.svelte';
	import { loadRuntimeConfig, type RuntimeConfig } from '$lib/runtime-config';

	let runtimeConfig = $state<RuntimeConfig | null>(null);

	onMount(async () => {
		runtimeConfig = await loadRuntimeConfig();
	});
</script>

<svelte:head>
	<title>V2X Cyber-Physical System Street View</title>
</svelte:head>

<div class="flex h-screen flex-col overflow-hidden bg-gray-950">
	<Header />

	<div class="min-h-0 flex-1 overflow-y-auto bg-black">
		<div class="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_20rem]">
			<LiveCameraPanel config={runtimeConfig} />
			<LiveDetectionsPanel config={runtimeConfig} />
		</div>
		<RecentDetectionsPanel limit={50} />
	</div>
</div>
