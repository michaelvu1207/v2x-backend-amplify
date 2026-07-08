<script lang="ts">
	import { onDestroy } from 'svelte';

	interface Props {
		cameraId: string;
		/** Drive server WS base URL (wss://...); /twin?cam= is appended. */
		wsBaseUrl: string;
	}

	let { cameraId, wsBaseUrl }: Props = $props();

	let frameUrl = $state<string | null>(null);
	let connected = $state(false);
	let error = $state<string | null>(null);
	let info = $state<{ width: number; height: number; fps: number } | null>(null);
	let ws: WebSocket | null = null;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let connectionKey = '';

	function disconnect() {
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		if (ws) {
			ws.onclose = null;
			ws.close();
			ws = null;
		}
		if (frameUrl) {
			URL.revokeObjectURL(frameUrl);
			frameUrl = null;
		}
		connected = false;
	}

	function scheduleReconnect() {
		if (reconnectTimer) return;
		reconnectTimer = setTimeout(() => {
			reconnectTimer = null;
			connect();
		}, 3000);
	}

	function connect() {
		disconnect();
		error = null;
		const base = wsBaseUrl.replace(/\/+$/, '');
		if (!base) {
			error = 'No drive server URL';
			return;
		}

		try {
			ws = new WebSocket(`${base}/twin?cam=${encodeURIComponent(cameraId)}`);
		} catch (err) {
			error = err instanceof Error ? err.message : 'WebSocket error';
			scheduleReconnect();
			return;
		}
		ws.binaryType = 'blob';

		ws.onmessage = (event) => {
			if (event.data instanceof Blob) {
				const next = URL.createObjectURL(event.data);
				if (frameUrl) URL.revokeObjectURL(frameUrl);
				frameUrl = next;
				connected = true;
				return;
			}
			try {
				const msg = JSON.parse(event.data as string);
				if (msg.type === 'twin_hello') {
					info = { width: msg.width, height: msg.height, fps: msg.fps };
					connected = true;
				} else if (msg.type === 'twin_error') {
					error = msg.message ?? 'Twin camera unavailable';
				}
			} catch {
				// Ignore malformed control messages.
			}
		};
		ws.onerror = () => {
			error = 'Twin stream connection failed';
		};
		ws.onclose = () => {
			connected = false;
			scheduleReconnect();
		};
	}

	$effect(() => {
		const key = `${wsBaseUrl}|${cameraId}`;
		if (key === connectionKey) return;
		connectionKey = key;
		connect();
	});

	onDestroy(() => {
		disconnect();
	});
</script>

<div class="relative overflow-hidden border border-gray-900 bg-black" style="aspect-ratio: 4 / 3;">
	<div class="absolute top-2 left-2 z-10 bg-black/70 px-2 py-1 text-[10px] font-medium tracking-[0.18em] text-gray-200 uppercase">
		{cameraId} · Digital Twin
	</div>

	<div class="absolute top-2 right-2 z-10 flex items-center gap-2">
		{#if connected}
			<span class="bg-cyan-500/90 px-2 py-1 text-[10px] font-semibold tracking-[0.16em] text-black uppercase">
				Twin
			</span>
		{/if}
		{#if info}
			<span class="bg-black/70 px-2 py-1 font-mono text-[10px] text-gray-400">{info.fps} fps</span>
		{/if}
	</div>

	{#if frameUrl}
		<img src={frameUrl} alt={`${cameraId} digital twin render`} class="h-full w-full object-cover" />
	{:else}
		<div class="flex h-full w-full items-center justify-center">
			{#if error}
				<p class="px-4 text-center text-[11px] text-rose-300">{error}</p>
			{:else}
				<div class="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-cyan-300"></div>
			{/if}
		</div>
	{/if}

	{#if error && frameUrl}
		<div class="absolute right-0 bottom-0 left-0 z-10 bg-black/85 px-3 py-2 text-[11px] text-rose-300">
			{error}
		</div>
	{/if}
</div>
