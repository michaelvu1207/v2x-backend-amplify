<script lang="ts">
	import { v2xSignals, v2xSignalCount, placeV2xSignal, removeV2xSignal, undoV2xSignal } from '$lib/stores/driveSocket';

	let message = $state('');
	let signalType = $state<'warning' | 'info' | 'alert'>('warning');
	let radius = $state(30);

	let signals = $derived($v2xSignals);
	let count = $derived($v2xSignalCount);

	interface Props {
		onClose: () => void;
	}

	let { onClose }: Props = $props();

	function handlePlace() {
		const msg = message.trim();
		if (!msg) return;
		placeV2xSignal(msg, signalType, radius);
		message = '';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handlePlace();
		if (e.key === 'Escape') onClose();
	}

	function typeColor(type: string): string {
		switch (type) {
			case 'warning': return 'bg-red-500';
			case 'alert': return 'bg-orange-500';
			case 'info': return 'bg-blue-500';
			default: return 'bg-gray-500';
		}
	}
</script>

<div class="absolute bottom-16 left-2 z-30 w-80 max-h-96 bg-gray-900/95 border border-gray-700 rounded-xl overflow-hidden pointer-events-auto flex flex-col">
	<!-- Header -->
	<div class="p-2 border-b border-gray-700 flex items-center justify-between">
		<span class="text-xs font-semibold text-white">V2X Signals</span>
		<div class="flex gap-1">
			<button onclick={() => undoV2xSignal()}
				class="px-2 py-1 bg-yellow-600/70 hover:bg-yellow-600 rounded text-xs text-white"
				title="Undo last signal">
				Undo
			</button>
			<button onclick={onClose}
				class="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300">
				X
			</button>
		</div>
	</div>

	<!-- Signal composer -->
	<div class="p-2 border-b border-gray-700 space-y-2">
		<input
			type="text"
			bind:value={message}
			placeholder="Signal message..."
			class="w-full px-2 py-1.5 bg-gray-800 border border-gray-600 rounded text-xs text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
			onkeydown={handleKeydown}
		/>

		<div class="flex items-center gap-2">
			<!-- Signal type -->
			<div class="flex bg-gray-800 rounded p-0.5 flex-1">
				{#each ['warning', 'alert', 'info'] as type}
					<button onclick={() => signalType = type as 'warning' | 'info' | 'alert'}
						class="flex-1 px-2 py-1 rounded text-[10px] font-medium transition-colors {signalType === type
							? (type === 'warning' ? 'bg-red-600 text-white' : type === 'alert' ? 'bg-orange-600 text-white' : 'bg-blue-600 text-white')
							: 'text-gray-400 hover:text-white'}">
						{type.charAt(0).toUpperCase() + type.slice(1)}
					</button>
				{/each}
			</div>
		</div>

		<!-- Radius slider -->
		<div class="flex items-center gap-2">
			<span class="text-[10px] text-gray-400 w-12">Range</span>
			<input
				type="range"
				min="10"
				max="100"
				step="5"
				bind:value={radius}
				class="flex-1 h-1 accent-blue-500"
			/>
			<span class="text-[10px] text-gray-300 w-8 text-right">{radius}m</span>
		</div>

		<button onclick={handlePlace}
			disabled={!message.trim()}
			class="w-full py-1.5 bg-green-600/80 hover:bg-green-600 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs font-medium text-white transition-colors">
			Place Signal
		</button>
	</div>

	<!-- Placed signals list -->
	<div class="overflow-y-auto flex-1 max-h-40">
		{#each signals as sig (sig.id)}
			<div class="px-3 py-1.5 flex items-center gap-2 hover:bg-gray-800 group">
				<span class="w-1.5 h-1.5 rounded-full {typeColor(sig.signal_type)}"></span>
				<span class="text-xs text-white truncate flex-1">{sig.message}</span>
				<span class="text-[10px] text-gray-500">{sig.radius}m</span>
				<button onclick={() => removeV2xSignal(sig.id)}
					class="text-[10px] text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
					✕
				</button>
			</div>
		{:else}
			<p class="p-3 text-xs text-gray-500 text-center">No signals placed</p>
		{/each}
	</div>

	<!-- Footer -->
	<div class="p-1.5 border-t border-gray-700">
		<span class="text-[10px] text-gray-500">V toggle | Place signals that alert nearby vehicles</span>
	</div>
</div>
