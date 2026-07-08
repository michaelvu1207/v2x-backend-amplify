<script lang="ts">
	import { onMount } from 'svelte';
	import TwinCameraView from './TwinCameraView.svelte';
	import LiveVideoCard from './LiveVideoCard.svelte';
	import RecentDetectionsPanel from './RecentDetectionsPanel.svelte';
	import { loadRuntimeConfig, type RuntimeConfig } from '$lib/runtime-config';

	interface Props {
		/** Drive server WS base URL (the selected tunnel). */
		wsBaseUrl: string;
	}

	let { wsBaseUrl }: Props = $props();

	let config = $state<RuntimeConfig | null>(null);
	let selectedCamera = $state('ch1');
	let showAll = $state(false);

	let cameraIds = $derived(config?.videoCameraIds ?? ['ch1', 'ch2', 'ch3', 'ch4']);

	function perceptionStreamUrl(cameraId: string): string {
		if (!config) return '';
		const explicitUrl = config.perceptionStreamUrls[cameraId];
		if (explicitUrl) return explicitUrl;
		if (!config.perceptionStreamBaseUrl) return '';
		const path = config.perceptionStreamPathTemplate.replace(
			'{camera_id}',
			encodeURIComponent(cameraId)
		);
		return `${config.perceptionStreamBaseUrl}${path.startsWith('/') ? path : `/${path}`}`;
	}

	onMount(async () => {
		config = await loadRuntimeConfig();
	});
</script>

<div class="flex h-full flex-col overflow-y-auto bg-gray-950">
	<div class="flex items-center gap-2 border-b border-gray-800 px-4 py-3">
		<span class="text-[11px] font-semibold tracking-[0.18em] text-gray-300 uppercase">
			Digital Twin · Live Mirror
		</span>
		<div class="ml-4 flex items-center gap-1">
			{#each cameraIds as cameraId}
				<button
					class={`border px-3 py-1 text-[11px] font-medium tracking-[0.14em] uppercase transition ${
						!showAll && selectedCamera === cameraId
							? 'border-cyan-400/60 bg-cyan-400/10 text-cyan-200'
							: 'border-gray-700 bg-gray-900 text-gray-300 hover:border-gray-500 hover:text-white'
					}`}
					onclick={() => {
						selectedCamera = cameraId;
						showAll = false;
					}}
				>
					{cameraId}
				</button>
			{/each}
			<button
				class={`border px-3 py-1 text-[11px] font-medium tracking-[0.14em] uppercase transition ${
					showAll
						? 'border-cyan-400/60 bg-cyan-400/10 text-cyan-200'
						: 'border-gray-700 bg-gray-900 text-gray-300 hover:border-gray-500 hover:text-white'
				}`}
				onclick={() => (showAll = !showAll)}
			>
				All
			</button>
		</div>
		<span class="ml-auto text-[11px] text-gray-500">
			Left: CARLA twin render · Right: real street camera
		</span>
	</div>

	{#if showAll}
		<div class="grid grid-cols-1 gap-px bg-gray-900 xl:grid-cols-2">
			{#each cameraIds as cameraId}
				<div class="grid grid-cols-2 gap-px bg-gray-900">
					<TwinCameraView {cameraId} {wsBaseUrl} />
					<LiveVideoCard
						{cameraId}
						streamUrl={perceptionStreamUrl(cameraId)}
						sourceLabel={perceptionStreamUrl(cameraId) ? 'Perception' : 'Raw'}
					/>
				</div>
			{/each}
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-px bg-gray-900 lg:grid-cols-2">
			<TwinCameraView cameraId={selectedCamera} {wsBaseUrl} />
			<LiveVideoCard
				cameraId={selectedCamera}
				streamUrl={perceptionStreamUrl(selectedCamera)}
				sourceLabel={perceptionStreamUrl(selectedCamera) ? 'Perception' : 'Raw'}
			/>
		</div>
	{/if}

	<!-- Live Objects DB feeding the twin -->
	<RecentDetectionsPanel limit={25} />
</div>
