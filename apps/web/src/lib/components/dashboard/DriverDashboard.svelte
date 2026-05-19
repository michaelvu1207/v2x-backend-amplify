<script lang="ts" module>
	import type { NearbyActor as TelemetryNearbyActor } from '$lib/types';
	import type { Gear } from './GearColumn.svelte';
	import type { DashboardWarning } from './WarningStack.svelte';

	export type { DashboardWarning };

	/** Convert CARLA's gear int to a Tesla-style P/R/N/D letter.
	 * CARLA: positive = forward, 0 = neutral, negative = reverse. */
	export function gearFromCarla(gear: number): Gear {
		if (gear > 0) return 'D';
		if (gear < 0) return 'R';
		return 'N';
	}
</script>

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { VehicleTelemetry } from '$lib/types';
	import InstrumentCluster from './InstrumentCluster.svelte';
	import CenterStack from './CenterStack.svelte';

	interface Props {
		/** Latest telemetry from the bridge. May be null on initial mount. */
		telemetry: VehicleTelemetry | null;
		/** All active warnings (V2X, EVA, scenario, verdict, etc.). */
		warnings?: DashboardWarning[];
		/** Override `now` for tests (skips the internal ticker). */
		now?: number;
		/** Speed display unit. */
		speedUnit?: 'mph' | 'kmh';
	}

	let { telemetry, warnings = [], now, speedUnit = 'mph' }: Props = $props();

	// Internal tick: re-evaluate fade state every ~150ms when `now` not injected.
	let tick = $state(Date.now());
	let timerId: ReturnType<typeof setInterval> | null = null;

	onMount(() => {
		if (now === undefined) {
			timerId = setInterval(() => {
				tick = Date.now();
			}, 150);
		}
	});

	onDestroy(() => {
		if (timerId != null) clearInterval(timerId);
	});

	const effectiveNow = $derived(now ?? tick);

	// Derived telemetry pieces with safe defaults so first paint is never blank.
	const speed = $derived(telemetry?.speed ?? 0);
	const gear = $derived(gearFromCarla(telemetry?.gear ?? 1));
	const throttle = $derived(telemetry?.throttle ?? 0);
	const brake = $derived(telemetry?.brake ?? 0);
	const steer = $derived(telemetry?.steer ?? 0);
	const egoPos = $derived<[number, number]>(
		telemetry ? [telemetry.pos[0], telemetry.pos[1]] : [0, 0]
	);
	const egoYaw = $derived(telemetry?.rot?.[1] ?? 0);
	const nearby = $derived<TelemetryNearbyActor[]>(
		telemetry?.nearby_actors ?? []
	);
</script>

<div
	class="flex w-full h-full font-tesla overflow-hidden"
	style="background: var(--color-tesla-bg); border-top: 1px solid var(--color-tesla-divider);"
	data-testid="driver-dashboard"
>
	<!-- Left: instrument cluster -->
	<div
		class="shrink-0"
		style="width: 50%; min-width: 0; border-right: 1px solid var(--color-tesla-divider);"
	>
		<InstrumentCluster {speed} {gear} {throttle} {brake} {steer} {speedUnit} />
	</div>

	<!-- Right: center stack (viz + warnings) -->
	<div class="grow" style="min-width: 0;">
		<CenterStack
			{egoPos}
			{egoYaw}
			{steer}
			{nearby}
			{warnings}
			now={effectiveNow}
		/>
	</div>
</div>
