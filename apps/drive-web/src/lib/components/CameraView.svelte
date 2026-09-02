<script lang="ts">
	import { CAMERA_VIEWS } from '$lib/constants';
	import type { CameraView } from '$lib/types';

	interface Props {
		activeView: CameraView;
		onSwitchView: (view: CameraView) => void;
		onZoom?: (factor: number) => void;
		onZoomReset?: () => void;
	}
	let { activeView, onSwitchView, onZoom, onZoomReset }: Props = $props();

	let imgSrc = $state<string | null>(null);
	let frameCount = $state(0);

	// Keyboard zoom step per press; matches one wheel notch.
	const KEY_ZOOM_STEP = 1.15;

	// Keyboard shortcuts for camera views + bird's-eye zoom
	function handleKeydown(e: KeyboardEvent) {
		if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
		const view = CAMERA_VIEWS.find((v) => v.key === e.key);
		if (view) {
			onSwitchView(view.id as CameraView);
			return;
		}
		if (activeView !== 'bird') return;
		if (e.key === '+' || e.key === '=') {
			onZoom?.(1 / KEY_ZOOM_STEP);
		} else if (e.key === '-' || e.key === '_') {
			onZoom?.(KEY_ZOOM_STEP);
		} else if (e.key === '0') {
			onZoomReset?.();
		}
	}

	// Bird's-eye wheel zoom: coalesce deltas into one multiplicative factor
	// per flush so a fast scroll doesn't flood the WebSocket.
	const ZOOM_FLUSH_MS = 60;
	const PX_PER_LINE = 16;
	let pendingZoom = 1;
	let zoomFlushId: number | null = null;

	function flushZoom() {
		zoomFlushId = null;
		if (pendingZoom !== 1) {
			onZoom?.(pendingZoom);
			pendingZoom = 1;
		}
	}

	function handleWheel(e: WheelEvent) {
		if (activeView !== 'bird') return;
		e.preventDefault();
		let dy = e.deltaY;
		if (e.deltaMode === 1) dy *= PX_PER_LINE;
		else if (e.deltaMode === 2) dy *= window.innerHeight || 800;
		dy = Math.max(-100, Math.min(100, dy));
		// Scroll down zooms out (camera climbs); ctrl+wheel is trackpad
		// pinch, which reports tiny deltas, so it gets a stronger gain.
		const k = e.ctrlKey ? 0.01 : 0.0015;
		pendingZoom *= Math.exp(dy * k);
		if (zoomFlushId === null) {
			zoomFlushId = window.setTimeout(flushZoom, ZOOM_FLUSH_MS);
		}
	}

	$effect(() => {
		window.addEventListener('keydown', handleKeydown);
		return () => {
			window.removeEventListener('keydown', handleKeydown);
			if (zoomFlushId !== null) {
				clearTimeout(zoomFlushId);
				zoomFlushId = null;
			}
		};
	});

	/**
	 * Feed a JPEG frame (as a Blob or ArrayBuffer) into the view.
	 * Called by the parent when a binary WebSocket message arrives.
	 */
	export function pushFrame(data: Blob | ArrayBuffer) {
		// Revoke previous object URL to prevent memory leak
		if (imgSrc) {
			URL.revokeObjectURL(imgSrc);
		}

		const blob = data instanceof Blob ? data : new Blob([data], { type: 'image/jpeg' });
		imgSrc = URL.createObjectURL(blob);
		frameCount++;
	}
</script>

<div class="relative w-full h-full bg-black" onwheel={handleWheel}>
	{#if imgSrc}
		<!-- MJPEG frame display -->
		<img src={imgSrc} alt="CARLA camera feed"
			class="w-full h-full object-contain" />
	{:else}
		<!-- Placeholder when no frames received yet -->
		<div class="absolute inset-0 flex items-center justify-center">
			<div class="text-center">
				<div class="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
					<svg class="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
					</svg>
				</div>
				<p class="text-sm text-gray-500">Waiting for camera feed...</p>
				<p class="text-xs text-gray-600 mt-1">Frames will appear once driving starts</p>
			</div>
		</div>
	{/if}

	<!-- Camera view toggle buttons removed — moved to top bar in drive page -->
</div>
