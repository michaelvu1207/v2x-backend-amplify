<script lang="ts">
	import SpeedDisplay from './SpeedDisplay.svelte';
	import GearColumn, { type Gear } from './GearColumn.svelte';
	import ThrottleBrakeBars from './ThrottleBrakeBars.svelte';

	interface Props {
		speed: number;
		gear: Gear;
		throttle: number;
		brake: number;
		steer: number;
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

	const steerDegrees = $derived(Math.round(steer * 450));
	const steerDisplay = $derived(
		steerDegrees === 0
			? '0°'
			: `${steerDegrees > 0 ? '+' : ''}${steerDegrees}°`
	);
</script>

<div
	class="relative flex h-full w-full font-tesla overflow-hidden items-center justify-between px-4 sm:px-6 gap-3"
	style="
		background:
			radial-gradient(ellipse at 30% 0%, rgba(62, 130, 247, 0.06) 0%, transparent 55%),
			linear-gradient(180deg, #0a0a0c 0%, #14171c 100%);
	"
	data-testid="instrument-cluster"
>
	<!-- Top recessed-screen highlight -->
	<div
		class="absolute top-0 left-0 right-0 h-px pointer-events-none"
		style="background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.18) 50%, transparent 100%);"
		aria-hidden="true"
	></div>

	<!-- LEFT: brake bar + speed + throttle bar -->
	<div class="flex items-center gap-3">
		<ThrottleBrakeBars {throttle} {brake} height="3.5rem" />
		<SpeedDisplay {speed} unit={speedUnit} />
	</div>

	<!-- RIGHT: gear + steer -->
	<div class="flex flex-col items-end gap-1.5">
		<GearColumn active={gear} orientation="row" />
		<div
			class="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] font-medium"
			style="color: var(--color-tesla-text-secondary);"
			data-testid="steer-readout"
		>
			<svg
				width="13"
				height="13"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				style="transform: rotate({steerDegrees * 0.4}deg); transition: transform 80ms linear;"
				aria-hidden="true"
			>
				<circle cx="12" cy="12" r="9" />
				<line x1="12" y1="3" x2="12" y2="6" />
				<line x1="3" y1="12" x2="6" y2="12" />
				<line x1="21" y1="12" x2="18" y2="12" />
				<line x1="12" y1="21" x2="12" y2="18" />
			</svg>
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
