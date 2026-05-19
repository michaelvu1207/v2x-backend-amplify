<script lang="ts">
	import type { VehicleTelemetry } from '$lib/types';

	interface Props {
		telemetry: VehicleTelemetry;
		isRecording?: boolean;
	}
	let { telemetry, isRecording = false }: Props = $props();
</script>

<!--
	Bottom HUD (speed/throttle/brake/steering/gear) was moved into the
	dedicated Tesla-style DriverDashboard strip below the camera viewport.
	This overlay now only carries the camera-corner accents — REC badge
	and GPS coordinates — which still live on top of the camera image.
-->
<div class="absolute inset-0 pointer-events-none select-none">
	<!-- Recording indicator -->
	{#if isRecording}
		<div class="absolute top-12 sm:top-14 right-2 sm:right-4 flex items-center gap-1.5">
			<div class="w-2 h-2 bg-accent rounded-full animate-pulse shadow-[0_0_6px_rgba(220,38,38,0.5)]"></div>
			<span class="text-[10px] font-body text-accent/80 tracking-widest">REC</span>
		</div>
	{/if}

	<!-- GPS position -->
	<div class="absolute top-12 sm:top-14 left-2 sm:left-4 text-[10px] sm:text-xs font-mono text-gray-600 tracking-wider">
		{telemetry.pos[0].toFixed(1)}, {telemetry.pos[1].toFixed(1)}
	</div>
</div>
