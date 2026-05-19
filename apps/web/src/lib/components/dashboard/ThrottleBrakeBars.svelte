<script lang="ts">
	interface Props {
		/** Throttle input 0-1. Bar fills from bottom up on the right. */
		throttle: number;
		/** Brake input 0-1. Bar fills from bottom up on the left. */
		brake: number;
		/** Height of the bars in CSS units (e.g. "6rem"). */
		height?: string;
	}

	let { throttle = 0, brake = 0, height = '5rem' }: Props = $props();

	const clampedThrottle = $derived(Math.max(0, Math.min(1, throttle)));
	const clampedBrake = $derived(Math.max(0, Math.min(1, brake)));
</script>

<div
	class="flex items-end gap-3 select-none"
	style="height: {height};"
	data-testid="throttle-brake-bars"
>
	<!-- Brake (left, red, bottom-up fill) -->
	<div
		class="relative rounded-full overflow-hidden"
		style="
			width: 4px;
			height: 100%;
			background: var(--color-tesla-divider);
			opacity: 0.5;
		"
		data-testid="brake-bar"
		data-fill={clampedBrake.toFixed(3)}
		role="meter"
		aria-label="Brake"
		aria-valuenow={clampedBrake}
		aria-valuemin="0"
		aria-valuemax="1"
	>
		<div
			class="absolute bottom-0 left-0 right-0 transition-[height] duration-100 ease-out"
			style="
				height: {clampedBrake * 100}%;
				background: var(--color-tesla-critical);
				box-shadow: 0 0 6px var(--color-tesla-critical);
				opacity: {clampedBrake > 0.01 ? 1 : 0};
			"
		></div>
	</div>

	<!-- Throttle (right, green, bottom-up fill) -->
	<div
		class="relative rounded-full overflow-hidden"
		style="
			width: 4px;
			height: 100%;
			background: var(--color-tesla-divider);
			opacity: 0.5;
		"
		data-testid="throttle-bar"
		data-fill={clampedThrottle.toFixed(3)}
		role="meter"
		aria-label="Throttle"
		aria-valuenow={clampedThrottle}
		aria-valuemin="0"
		aria-valuemax="1"
	>
		<div
			class="absolute bottom-0 left-0 right-0 transition-[height] duration-100 ease-out"
			style="
				height: {clampedThrottle * 100}%;
				background: var(--color-tesla-active);
				box-shadow: 0 0 6px var(--color-tesla-active);
				opacity: {clampedThrottle > 0.01 ? 1 : 0};
			"
		></div>
	</div>
</div>
