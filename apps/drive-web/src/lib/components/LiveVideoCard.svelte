<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import Hls from 'hls.js';
	import { resolveLiveVideoUrl } from '$lib/runtime-config';
	import { playWithAbortRetry } from '$lib/media-play';

	interface Props {
		cameraId: string;
		streamUrl?: string;
		liveVideoUrlTemplate: string;
		sourceLabel?: string;
	}

	let {
		cameraId,
		streamUrl = '',
		liveVideoUrlTemplate,
		sourceLabel = 'Raw'
	}: Props = $props();

	let videoEl = $state<HTMLVideoElement | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let connected = $state(false);
	let mjpegUrl = $state('');
	let player: Hls | null = null;
	let connectionKey = '';
	let connectionRevision = 0;

	function destroyPlayer() {
		player?.destroy();
		player = null;
		mjpegUrl = '';
		if (videoEl) {
			videoEl.pause();
			videoEl.removeAttribute('src');
			videoEl.load();
		}
		connected = false;
	}

	function isImageStream(url: string): boolean {
		const cleanUrl = url.split('?')[0].toLowerCase();
		return (
			cleanUrl.endsWith('.mjpg') ||
			cleanUrl.endsWith('.mjpeg') ||
			cleanUrl.endsWith('.jpg') ||
			cleanUrl.endsWith('.jpeg') ||
			cleanUrl.endsWith('.png') ||
			cleanUrl.endsWith('.svg')
		);
	}

	async function attachHls(url: string, useCredentials: boolean) {
		if (!videoEl) throw new Error('Video element unavailable');
		videoEl.crossOrigin = useCredentials ? 'use-credentials' : 'anonymous';
		if (Hls.isSupported()) {
			player = new Hls({
				enableWorker: true,
				lowLatencyMode: false,
				...(useCredentials
					? {
							xhrSetup: (xhr: XMLHttpRequest) => {
								xhr.withCredentials = true;
							}
						}
					: {})
			});
			player.loadSource(url);
			player.attachMedia(videoEl);
		} else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
			videoEl.src = url;
		} else {
			throw new Error('HLS playback is not supported in this browser');
		}
		await playWithAbortRetry(videoEl);
	}

	async function connect() {
		const revision = ++connectionRevision;
		loading = true;
		error = null;
		destroyPlayer();
		await tick();
		if (revision !== connectionRevision) return;

		try {
			const explicitStreamUrl = streamUrl.trim();
			const sourceUrl =
				explicitStreamUrl || resolveLiveVideoUrl(liveVideoUrlTemplate, cameraId);
			if (!sourceUrl) {
				throw new Error('Video source not configured');
			}
			if (isImageStream(sourceUrl)) {
				mjpegUrl = sourceUrl;
				return;
			}
			await attachHls(
				sourceUrl,
				Boolean(liveVideoUrlTemplate.trim() && !explicitStreamUrl)
			);
			if (revision === connectionRevision) connected = true;
		} catch (err) {
			if (revision !== connectionRevision) return;
			error = err instanceof Error ? err.message : 'Unknown playback error';
			destroyPlayer();
		} finally {
			if (revision === connectionRevision) loading = false;
		}
	}

	$effect(() => {
		const key = `${cameraId}|${streamUrl}|${liveVideoUrlTemplate}`;
		if (key === connectionKey) return;
		connectionKey = key;
		void connect();
	});

	onDestroy(() => {
		connectionRevision += 1;
		destroyPlayer();
	});
</script>

<div class="relative overflow-hidden border border-gray-900 bg-black" style="aspect-ratio: 4 / 3;">
	<div class="absolute top-2 left-2 z-10 bg-black/70 px-2 py-1 text-[10px] font-medium tracking-[0.18em] text-gray-200 uppercase">
		{cameraId}
	</div>

	<div class="absolute top-2 right-2 z-10 flex items-center gap-2">
		<span class="bg-black/70 px-2 py-1 text-[10px] font-medium tracking-[0.16em] text-gray-200 uppercase">
			{sourceLabel}
		</span>
		{#if connected}
			<span class="bg-red-600 px-2 py-1 text-[10px] font-semibold tracking-[0.16em] text-white uppercase">
				Live
			</span>
		{/if}
	</div>

	<div class="absolute inset-0">
		{#if mjpegUrl}
			<img
				src={mjpegUrl}
				alt={`${cameraId} perception stream`}
				class="h-full w-full object-cover"
				onload={() => {
					connected = true;
				}}
				onerror={() => {
					error = 'Perception stream unavailable';
					connected = false;
				}}
			/>
		{:else}
			<video
				bind:this={videoEl}
				class="absolute inset-0 h-full w-full object-cover"
				playsinline
				muted
			></video>
		{/if}

		{#if !connected && !loading}
			<div class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/55">
				<button
					class="border border-gray-600 bg-black/80 px-4 py-2 text-[11px] font-medium tracking-[0.16em] text-white uppercase hover:border-gray-400"
					onclick={connect}
				>
					Reconnect
				</button>
			</div>
		{/if}

		{#if loading}
			<div class="absolute inset-0 flex items-center justify-center bg-black/45">
				<div class="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-cyan-300"></div>
			</div>
		{/if}
	</div>

	{#if error}
		<div class="absolute right-0 bottom-0 left-0 z-10 bg-black/85 px-3 py-2 text-[11px] text-rose-300">
			{error}
		</div>
	{/if}
</div>
