<script lang="ts">
	import type { TrackedObject, SnapshotHistoryEntry } from '$lib/types';
	import { OBJECT_COLORS, FRESHNESS_THRESHOLDS } from '$lib/constants';

	interface Props {
		object: TrackedObject | null;
		onClose: () => void;
	}

	let { object, onClose }: Props = $props();

	let snapshots = $state<SnapshotHistoryEntry[]>([]);
	let loadingSnapshots = $state(false);
	let now = $state(Date.now());

	// Tick every second for freshness
	$effect(() => {
		const interval = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(interval);
	});

	let objectColor = $derived(
		object ? (OBJECT_COLORS[object.object_type] ?? OBJECT_COLORS.default) : OBJECT_COLORS.default
	);

	let freshnessMs = $derived(
		object?.snapshot_timestamp
			? now - new Date(object.snapshot_timestamp).getTime()
			: Infinity
	);

	let freshnessLabel = $derived(
		freshnessMs < FRESHNESS_THRESHOLDS.fresh
			? 'Fresh'
			: freshnessMs < FRESHNESS_THRESHOLDS.stale
				? 'Stale'
				: 'Old'
	);

	let freshnessColor = $derived(
		freshnessMs < FRESHNESS_THRESHOLDS.fresh
			? 'text-green-400'
			: freshnessMs < FRESHNESS_THRESHOLDS.stale
				? 'text-amber-400'
				: 'text-red-400'
	);

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			onClose();
		}
	}

	function formatTimestamp(ts: string): string {
		try {
			return new Date(ts).toLocaleString();
		} catch {
			return ts;
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Backdrop -->
{#if object}
	<div
		class="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-300"
		role="button"
		tabindex="-1"
		onclick={onClose}
		onkeydown={(e) => e.key === 'Enter' && onClose()}
		aria-label="Close detail panel"
	></div>
{/if}

<!-- Panel -->
<div
	class="fixed top-0 right-0 z-50 flex h-full w-full max-w-md transform flex-col border-l border-gray-700/50
	       bg-gray-900 shadow-2xl shadow-black/50 transition-transform duration-300 ease-out
	       {object ? 'translate-x-0' : 'translate-x-full'}"
>
	{#if object}
		<!-- Header -->
		<div class="flex items-center justify-between border-b border-gray-700/50 px-4 py-3">
			<div class="flex items-center gap-3">
				<span
					class="h-3 w-3 rounded-full"
					style="background-color: {objectColor};"
				></span>
				<div>
					<h2 class="text-sm font-semibold text-white">{object.object_id}</h2>
					<p class="text-xs capitalize text-gray-400">{object.object_type.replace(/_/g, ' ')}</p>
				</div>
			</div>
			<button
				onclick={onClose}
				class="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors
				       hover:bg-gray-800 hover:text-white"
				aria-label="Close panel"
			>
				<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
				</svg>
			</button>
		</div>

		<!-- Content -->
		<div class="flex-1 overflow-y-auto">
			<!-- Main snapshot -->
			<div class="relative aspect-[4/3] w-full bg-gray-950">
				{#if object.snapshot_url}
					<img
						src={object.snapshot_url}
						alt="Latest snapshot of {object.object_id}"
						class="h-full w-full object-cover"
					/>
				{:else}
					<div class="flex h-full items-center justify-center">
						<span class="text-sm text-gray-600">No snapshot available</span>
					</div>
				{/if}

				<!-- Freshness badge on image -->
				<div class="absolute top-3 right-3">
					<span class="rounded-full bg-black/70 px-2.5 py-1 text-xs font-medium backdrop-blur-sm {freshnessColor}">
						{freshnessLabel}
					</span>
				</div>
			</div>

			<!-- Details grid -->
			<div class="border-b border-gray-800 p-4">
				<h3 class="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Details</h3>
				<dl class="grid grid-cols-2 gap-x-4 gap-y-3">
					<div>
						<dt class="text-[10px] uppercase tracking-wide text-gray-500">Type</dt>
						<dd class="mt-0.5 text-sm capitalize text-white">{object.object_type.replace(/_/g, ' ')}</dd>
					</div>
					<div>
						<dt class="text-[10px] uppercase tracking-wide text-gray-500">Confidence</dt>
						<dd class="mt-0.5 text-sm text-white">
							{object.confidence != null ? `${Math.round(object.confidence * 100)}%` : 'N/A'}
						</dd>
					</div>
					<div>
						<dt class="text-[10px] uppercase tracking-wide text-gray-500">Latitude</dt>
						<dd class="mt-0.5 text-sm font-mono text-white">{object.lat.toFixed(6)}</dd>
					</div>
					<div>
						<dt class="text-[10px] uppercase tracking-wide text-gray-500">Longitude</dt>
						<dd class="mt-0.5 text-sm font-mono text-white">{object.lon.toFixed(6)}</dd>
					</div>
					<div class="col-span-2">
						<dt class="text-[10px] uppercase tracking-wide text-gray-500">Street</dt>
						<dd class="mt-0.5 text-sm text-white">{object.street_name || 'Unknown'}</dd>
					</div>
					<div class="col-span-2">
						<dt class="text-[10px] uppercase tracking-wide text-gray-500">Last Updated</dt>
						<dd class="mt-0.5 text-sm text-white">
							{object.timestamp_utc ? formatTimestamp(object.timestamp_utc) : 'N/A'}
						</dd>
					</div>
				</dl>
			</div>

			<!-- Snapshot history filmstrip -->
			<div class="p-4">
				<h3 class="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
					Snapshot History
				</h3>

				{#if loadingSnapshots}
					<div class="flex items-center justify-center py-6">
						<div class="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-gray-300"></div>
					</div>
				{:else if snapshots.length > 0}
					<div class="flex gap-2 overflow-x-auto pb-2">
						{#each snapshots as snap (snap.timestamp)}
							<div class="shrink-0">
								<div class="h-16 w-[86px] overflow-hidden rounded border border-gray-700 bg-gray-950">
									<img
										src={snap.url}
										alt="Snapshot from {snap.timestamp}"
										class="h-full w-full object-cover"
										loading="lazy"
									/>
								</div>
								<p class="mt-1 text-center text-[9px] text-gray-500">
									{new Date(snap.timestamp).toLocaleTimeString()}
								</p>
							</div>
						{/each}
					</div>
				{:else}
					<div class="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
						<p class="text-xs text-gray-500">No snapshot history available</p>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
