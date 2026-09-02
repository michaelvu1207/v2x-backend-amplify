<script lang="ts">
	import { spawnTraffic, despawnTraffic, telemetry } from '$lib/stores/driveSocket';
	import type { TrafficPreset } from '$lib/types';

	interface Props {
		onClose: () => void;
	}

	let { onClose }: Props = $props();

	let activePreset = $state<TrafficPreset>('none');
	let spawning = $state(false);
	let lastResult = $state<string>('');

	const PRESETS: { id: TrafficPreset; label: string; count: string; desc: string }[] = [
		{ id: 'none',   label: 'None',    count: '0',   desc: 'Empty map' },
		{ id: 'light',  label: 'Light',   count: '20',  desc: 'Sparse, slow, docile' },
		{ id: 'medium', label: 'Medium',  count: '60',  desc: 'Default mix' },
		{ id: 'heavy',  label: 'Heavy',   count: '120', desc: 'Dense, some aggressive' },
		{ id: 'chaos',  label: 'Chaos',   count: '180', desc: 'V2X stress test' },
	];

	async function apply(preset: TrafficPreset) {
		spawning = true;
		activePreset = preset;
		lastResult = '';
		if (preset === 'none') {
			despawnTraffic();
			lastResult = 'Cleared';
		} else {
			spawnTraffic(preset);
			lastResult = `Spawning ${preset}...`;
		}
		// Spawning is async on the server, no ack here
		setTimeout(() => { spawning = false; }, 2000);
	}

	// Count traffic visible in telemetry (actors the player can see)
	let visibleTraffic = $derived(
		($telemetry.nearby_actors ?? []).filter(a => a.type === 'traffic').length
	);
</script>

<div class="absolute bottom-16 right-2 z-30 w-64 bg-gray-900/95 border border-gray-700 rounded-xl overflow-hidden pointer-events-auto flex flex-col">
	<!-- Header -->
	<div class="p-2.5 border-b border-gray-700 flex items-center justify-between">
		<span class="text-xs font-semibold text-white tracking-wider uppercase">Traffic</span>
		<button onclick={onClose}
			class="px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300">
			X
		</button>
	</div>

	<!-- Presets -->
	<div class="flex-1 p-2 flex flex-col gap-1">
		{#each PRESETS as p}
			<button
				onclick={() => apply(p.id)}
				disabled={spawning}
				class="flex items-center justify-between px-3 py-2 rounded text-left transition-colors
					{activePreset === p.id
						? 'bg-blue-600/30 border border-blue-500/50 text-white'
						: 'bg-gray-800 hover:bg-gray-700 text-gray-300 border border-transparent'}
					{spawning ? 'opacity-60 cursor-wait' : 'cursor-pointer'}"
			>
				<div class="flex flex-col">
					<span class="text-xs font-medium">{p.label}</span>
					<span class="text-[10px] text-gray-500">{p.desc}</span>
				</div>
				<span class="text-[10px] font-mono text-gray-500">{p.count}</span>
			</button>
		{/each}
	</div>

	<!-- Status footer -->
	<div class="px-2.5 py-2 border-t border-gray-700 flex items-center justify-between">
		<span class="text-[10px] text-gray-500">
			{#if visibleTraffic > 0}
				<span class="text-amber-400 font-mono">{visibleTraffic}</span> nearby
			{:else}
				No traffic visible
			{/if}
		</span>
		{#if lastResult}
			<span class="text-[10px] text-gray-400">{lastResult}</span>
		{/if}
	</div>
</div>
