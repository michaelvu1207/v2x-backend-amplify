<script lang="ts">
	import SpeedDisplay from './SpeedDisplay.svelte';
	import GearColumn, { type Gear } from './GearColumn.svelte';
	import ThrottleBrakeBars from './ThrottleBrakeBars.svelte';

	interface Props {
		/** Speed in km/h (matches bridge telemetry). */
		speed: number;
		/** Active gear (P/R/N/D). */
		gear: Gear;
		/** Throttle 0-1. */
		throttle: number;
		/** Brake 0-1. */
		brake: number;
		/** Steering input in [-1, 1] (CARLA normalized). */
		steer: number;
		/** Display unit for speed. */
		speedUnit?: 'mph' | 'kmh';
	}

	let {
		speed = 0,
		gear = 'D',
		throttle = 0,
		brake = 0,
		steer = 0,
		speedUnit = 'mph',
	}: Props = $props();

	/** Convert CARLA's normalized steer [-1, 1] to a wheel-angle-ish degree
	 * value. Tesla wheels lock at ~540° (1.5 turns each way); we use 450°
	 * (1.25 turns) as a sane sim mapping so the indicator is readable. */
	const steerDegrees = $derived(Math.round(steer * 450));
	const steerDisplay = $derived(
		steerDegrees === 0
			? '0°'
			: `${steerDegrees > 0 ? '+' : ''}${steerDegrees}°`
	);
</script>

<div
	class="flex items-center justify-between h-full w-full px-6 sm:px-10"
	style="background: var(--color-tesla-bg);"
	data-testid="instrument-cluster"
>
	<!-- Left: throttle/brake strips flanking the speed -->
	<div class="flex items-center gap-4">
		<ThrottleBrakeBars {throttle} {brake} height="5.5rem" />
		<SpeedDisplay {speed} unit={speedUnit} />
	</div>

	<!-- Right: gear row + steering readout, stacked -->
	<div class="flex flex-col items-end gap-3">
		<GearColumn active={gear} orientation="row" />
		<div
			class="font-tesla flex items-center gap-2 text-xs uppercase tracking-[0.18em]"
			style="color: var(--color-tesla-text-secondary);"
			data-testid="steer-readout"
		>
			<span>steer</span>
			<span
				class="tabular-nums"
				style="color: var(--color-tesla-text); font-feature-settings: 'tnum';"
				data-testid="steer-degrees"
			>
				{steerDisplay}
			</span>
		</div>
	</div>
</div>
