<script lang="ts">
	interface Props {
		/** Speed in km/h (matches the bridge's telemetry shape). */
		speed: number;
		/** Display unit. Defaults to mph (Tesla US convention). */
		unit?: 'mph' | 'kmh';
	}

	let { speed = 0, unit = 'mph' }: Props = $props();

	const displayed = $derived(
		unit === 'mph' ? Math.round(speed * 0.6213711922) : Math.round(speed)
	);
	const label = $derived(unit === 'mph' ? 'MPH' : 'KM/H');
</script>

<div
	class="flex flex-col items-center justify-center select-none"
	data-testid="speed-display"
>
	<span
		class="font-tesla font-medium leading-none tracking-tight text-white tabular-nums"
		style="font-size: clamp(3rem, 9vw, 6rem); font-feature-settings: 'tnum';"
		data-testid="speed-value"
	>
		{displayed}
	</span>
	<span
		class="font-tesla mt-1 text-xs uppercase tracking-[0.18em]"
		style="color: var(--color-tesla-text-secondary);"
		data-testid="speed-unit"
	>
		{label}
	</span>
</div>
