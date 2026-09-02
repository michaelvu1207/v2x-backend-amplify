<script lang="ts">
	import { onMount } from 'svelte';
	import {
		trajectoryList,
		trajectoryStatus,
		requestTrajectories,
		uploadTrajectory,
		startTrajectory,
		stopTrajectory,
		requestTrajectoryStatus,
	} from '$lib/stores/driveSocket';

	interface Props {
		onClose: () => void;
	}

	let { onClose }: Props = $props();

	let selectedFile = $state<string>('');
	let uploadName = $state<string>('');
	let uploading = $state(false);
	let lastResult = $state<string>('');
	let statusInterval: ReturnType<typeof setInterval> | null = null;
	let fileInput: HTMLInputElement | null = $state(null);

	onMount(() => {
		requestTrajectories();
		statusInterval = setInterval(() => {
			if ($trajectoryStatus.active) requestTrajectoryStatus();
		}, 1000);
		return () => {
			if (statusInterval) clearInterval(statusInterval);
		};
	});

	$effect(() => {
		// Default to first available trajectory once the list arrives
		if (!selectedFile && $trajectoryList.length > 0) {
			selectedFile = $trajectoryList[0].file;
		}
	});

	async function handleFile(event: Event) {
		const input = event.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		uploading = true;
		lastResult = '';
		try {
			const text = await file.text();
			const data = JSON.parse(text);
			if (!Array.isArray(data)) throw new Error('Trajectory JSON must be a list');
			const name = uploadName.trim() || file.name.replace(/\.json$/i, '');
			uploadTrajectory(name, data);
			lastResult = `Uploaded ${name}`;
			uploadName = '';
		} catch (e) {
			lastResult = `Upload failed: ${(e as Error).message}`;
		} finally {
			uploading = false;
			if (fileInput) fileInput.value = '';
		}
	}

	function start() {
		if (!selectedFile) return;
		startTrajectory(selectedFile);
		lastResult = `Starting ${selectedFile}...`;
	}

	function stop() {
		stopTrajectory();
		lastResult = 'Stopped';
	}

	let progressPct = $derived(() => {
		const s = $trajectoryStatus;
		if (!s.active || !s.duration) return 0;
		return Math.min(100, ((s.elapsed ?? 0) / s.duration) * 100);
	});
</script>

<div class="absolute bottom-16 right-2 z-30 w-72 bg-gray-900/95 border border-gray-700 rounded-xl overflow-hidden pointer-events-auto flex flex-col">
	<!-- Header -->
	<div class="p-2.5 border-b border-gray-700 flex items-center justify-between">
		<span class="text-xs font-semibold text-white tracking-wider uppercase">Trajectory</span>
		<button onclick={onClose}
			class="px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300">
			X
		</button>
	</div>

	<!-- Picker + Start/Stop -->
	<div class="p-2 flex flex-col gap-2">
		<label class="text-[10px] text-gray-500 uppercase tracking-wider" for="traj-select">Available</label>
		<select
			id="traj-select"
			bind:value={selectedFile}
			disabled={$trajectoryList.length === 0 || $trajectoryStatus.active}
			class="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
		>
			{#each $trajectoryList as t}
				<option value={t.file}>{t.file} ({t.samples})</option>
			{/each}
			{#if $trajectoryList.length === 0}
				<option value="">No trajectories</option>
			{/if}
		</select>

		<div class="flex gap-1">
			<button
				onclick={start}
				disabled={!selectedFile || $trajectoryStatus.active}
				class="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors
					{$trajectoryStatus.active
						? 'bg-gray-800 text-gray-500 cursor-not-allowed'
						: 'bg-blue-600 hover:bg-blue-500 text-white'}"
			>
				Start
			</button>
			<button
				onclick={stop}
				disabled={!$trajectoryStatus.active}
				class="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors
					{!$trajectoryStatus.active
						? 'bg-gray-800 text-gray-500 cursor-not-allowed'
						: 'bg-red-600 hover:bg-red-500 text-white'}"
			>
				Stop
			</button>
		</div>
	</div>

	<!-- Status / progress -->
	{#if $trajectoryStatus.active}
		<div class="px-2 pb-2 flex flex-col gap-1">
			<div class="flex items-center justify-between text-[10px] text-gray-400">
				<span>{$trajectoryStatus.name ?? '?'}</span>
				<span class="font-mono">
					{($trajectoryStatus.elapsed ?? 0).toFixed(1)} / {($trajectoryStatus.duration ?? 0).toFixed(1)}s
				</span>
			</div>
			<div class="h-1 bg-gray-800 rounded overflow-hidden">
				<div class="h-full bg-blue-500 transition-all" style="width: {progressPct()}%"></div>
			</div>
			{#if $trajectoryStatus.finished}
				<span class="text-[10px] text-amber-400">Reached end of path — vehicle stopped</span>
			{/if}
		</div>
	{/if}

	<!-- Upload -->
	<div class="border-t border-gray-700 p-2 flex flex-col gap-1.5">
		<label class="text-[10px] text-gray-500 uppercase tracking-wider" for="traj-upload-name">Upload JSON</label>
		<input
			id="traj-upload-name"
			type="text"
			placeholder="(optional name)"
			bind:value={uploadName}
			disabled={uploading}
			class="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder:text-gray-600"
		/>
		<input
			bind:this={fileInput}
			type="file"
			accept="application/json,.json"
			onchange={handleFile}
			disabled={uploading}
			class="text-[10px] text-gray-400 file:mr-2 file:rounded file:border-0 file:bg-gray-700 file:px-2 file:py-1 file:text-xs file:text-gray-200 hover:file:bg-gray-600"
		/>
	</div>

	<!-- Footer -->
	{#if lastResult}
		<div class="px-2.5 py-1.5 border-t border-gray-700 text-[10px] text-gray-400">{lastResult}</div>
	{/if}
</div>
