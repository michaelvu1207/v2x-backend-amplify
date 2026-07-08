<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { fetchDetectionsPage, fetchDetectionsRange } from '$lib/api';
	import type { DetectionItem } from '$lib/types';

	interface Props {
		limit?: number;
		refreshMs?: number;
		/** When set, shows detections in this window instead of live-polling. */
		range?: { start: string; end: string } | null;
		highlightObjectId?: string | null;
	}

	let { limit = 25, refreshMs = 5000, range = null, highlightObjectId = null }: Props = $props();

	let items = $state<DetectionItem[]>([]);
	let isLoading = $state(false);
	let error = $state<string | null>(null);
	let lastUpdated = $state<string | null>(null);
	let refreshTimer: ReturnType<typeof setInterval> | null = null;
	let loadedRangeKey = '';

	function displayValue(value: unknown): string {
		return value == null ? '' : String(value);
	}

	function displayConfidence(value: DetectionItem['confidence_score']): string {
		if (typeof value === 'number') return value.toFixed(2);
		return displayValue(value);
	}

	async function loadItems() {
		error = null;
		isLoading = items.length === 0;

		try {
			const response = range
				? await fetchDetectionsRange({ start: range.start, end: range.end, limit })
				: await fetchDetectionsPage({ mode: 'recent', limit });
			items = response.items || [];
			lastUpdated = new Date().toLocaleTimeString();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to fetch detections.';
		} finally {
			isLoading = false;
		}
	}

	function startPolling() {
		stopPolling();
		refreshTimer = setInterval(() => {
			void loadItems();
		}, refreshMs);
	}

	function stopPolling() {
		if (refreshTimer) {
			clearInterval(refreshTimer);
			refreshTimer = null;
		}
	}

	$effect(() => {
		const key = range ? `${range.start}|${range.end}` : 'live';
		if (key === loadedRangeKey) return;
		loadedRangeKey = key;
		void loadItems();
		if (range) {
			stopPolling();
		} else {
			startPolling();
		}
	});

	onMount(() => {
		if (!range) startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});
</script>

<section class="border-t border-gray-800 bg-gray-950">
	<div class="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div>
				<h1 class="text-lg font-semibold text-white">
					Objects DB
					{#if range}
						<span class="ml-2 align-middle text-[10px] font-medium tracking-[0.16em] text-amber-300 uppercase">Time-locked</span>
					{:else}
						<span class="ml-2 align-middle text-[10px] font-medium tracking-[0.16em] text-emerald-300 uppercase">Live</span>
					{/if}
				</h1>
				{#if lastUpdated}
					<p class="mt-1 text-xs text-gray-500">Updated {lastUpdated}</p>
				{/if}
			</div>
			<button
				class="border border-gray-700 bg-gray-900 px-3 py-2 text-xs font-medium tracking-[0.14em] text-gray-200 uppercase transition hover:border-gray-500 hover:text-white"
				onclick={loadItems}
			>
				Refresh
			</button>
		</div>

		{#if error}
			<p class="text-sm text-red-300">{error}</p>
		{/if}

		<div class="overflow-auto border border-gray-800">
			<table class="min-w-full border-collapse text-left text-sm">
				<thead class="bg-black">
					<tr class="border-b border-gray-800 text-[11px] tracking-[0.16em] text-gray-500 uppercase">
						<th class="px-4 py-3 font-medium">Time</th>
						<th class="px-4 py-3 font-medium">Object</th>
						<th class="px-4 py-3 font-medium">Type</th>
						<th class="px-4 py-3 font-medium">Confidence</th>
						<th class="px-4 py-3 font-medium">Device</th>
					</tr>
				</thead>
				<tbody class="font-mono text-xs text-gray-200">
					{#if isLoading}
						<tr>
							<td colspan="5" class="px-4 py-8 text-center text-sm text-gray-500">
								Loading...
							</td>
						</tr>
					{:else if items.length === 0}
						<tr>
							<td colspan="5" class="px-4 py-8 text-center text-sm text-gray-500">
								No detections returned for this query yet.
							</td>
						</tr>
					{:else}
						{#each items as item}
							<tr
								class={`border-b border-gray-900/80 transition hover:bg-white/[0.03] ${
									highlightObjectId != null && item.object_id === highlightObjectId
										? 'bg-amber-400/10'
										: ''
								}`}
							>
								<td class="px-4 py-3 align-top">{displayValue(item.timestamp_utc)}</td>
								<td class="px-4 py-3 align-top">{displayValue(item.object_id)}</td>
								<td class="px-4 py-3 align-top">{displayValue(item.object_type)}</td>
								<td class="px-4 py-3 align-top">{displayConfidence(item.confidence_score)}</td>
								<td class="px-4 py-3 align-top">{displayValue(item.device_id)}</td>
							</tr>
						{/each}
					{/if}
				</tbody>
			</table>
		</div>
	</div>
</section>
