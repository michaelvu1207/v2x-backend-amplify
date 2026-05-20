<script lang="ts">
	import SpeedDisplay from './SpeedDisplay.svelte';
	import GearColumn, { type Gear } from './GearColumn.svelte';
	import SteeringBar from './SteeringBar.svelte';

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

	const clampedThrottle = $derived(Math.max(0, Math.min(1, throttle)));
	const clampedBrake = $derived(Math.max(0, Math.min(1, brake)));
</script>

<div
	class="relative flex h-full w-full font-tesla overflow-hidden items-center justify-center gap-6 sm:gap-10 px-6"
	style="
		background:
			radial-gradient(ellipse at 50% 0%, rgba(62, 130, 247, 0.06) 0%, transparent 55%);
	"
	data-testid="instrument-cluster"
>
	<!-- LEFT: vertical throttle bar -->
	<div class="flex flex-col items-center gap-1 shrink-0">
		<div
			class="relative rounded-full overflow-hidden"
			style="
				width: 7px;
				height: 4.5rem;
				background: linear-gradient(180deg, rgba(58, 63, 71, 0.6) 0%, rgba(20, 23, 28, 0.8) 100%);
				border: 1px solid rgba(255, 255, 255, 0.08);
				box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7);
			"
			role="meter"
			aria-label="Throttle"
			aria-valuenow={clampedThrottle}
			aria-valuemin="0"
			aria-valuemax="1"
			data-testid="throttle-bar"
			data-fill={clampedThrottle.toFixed(3)}
		>
			<div
				class="absolute bottom-0 left-0 right-0 transition-[height] duration-75 rounded-b-full rounded-t-full"
				style="
					height: {clampedThrottle * 100}%;
					background: linear-gradient(180deg, #5dffa1 0%, var(--color-tesla-active) 100%);
					box-shadow:
						0 0 8px var(--color-tesla-active),
						0 0 16px rgba(34, 197, 94, 0.55);
					opacity: {clampedThrottle > 0.005 ? 1 : 0};
				"
			></div>
		</div>
	</div>

	<!-- CENTER: steering bar above speed + gear -->
	<div class="flex flex-col items-center gap-2 shrink-0">
		<SteeringBar {steer} width="14rem" />
		<div class="flex items-baseline gap-3">
			<SpeedDisplay {speed} unit={speedUnit} />
			<GearColumn active={gear} orientation="row" />
		</div>
	</div>

	<!-- RIGHT: vertical brake bar -->
	<div class="flex flex-col items-center gap-1 shrink-0">
		<div
			class="relative rounded-full overflow-hidden"
			style="
				width: 7px;
				height: 4.5rem;
				background: linear-gradient(180deg, rgba(58, 63, 71, 0.6) 0%, rgba(20, 23, 28, 0.8) 100%);
				border: 1px solid rgba(255, 255, 255, 0.08);
				box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7);
			"
			role="meter"
			aria-label="Brake"
			aria-valuenow={clampedBrake}
			aria-valuemin="0"
			aria-valuemax="1"
			data-testid="brake-bar"
			data-fill={clampedBrake.toFixed(3)}
		>
			<div
				class="absolute bottom-0 left-0 right-0 transition-[height] duration-75 rounded-b-full rounded-t-full"
				style="
					height: {clampedBrake * 100}%;
					background: linear-gradient(180deg, #ff5e63 0%, var(--color-tesla-critical) 100%);
					box-shadow:
						0 0 8px var(--color-tesla-critical),
						0 0 16px rgba(232, 33, 39, 0.55);
					opacity: {clampedBrake > 0.005 ? 1 : 0};
				"
			></div>
		</div>
	</div>
</div>
