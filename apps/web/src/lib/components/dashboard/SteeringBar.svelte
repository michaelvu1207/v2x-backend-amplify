<script lang="ts">
	interface Props {
		/** Steer in [-1, 1] (CARLA normalized). -1 = full left, +1 = full right. */
		steer: number;
		/** Bar width in CSS units (e.g. "16rem"). */
		width?: string;
	}

	let { steer = 0, width = '14rem' }: Props = $props();

	const clamped = $derived(Math.max(-1, Math.min(1, steer)));
	/** 0% = full left, 50% = center, 100% = full right. */
	const dotPct = $derived(((clamped + 1) / 2) * 100);
</script>

<div
	class="relative select-none"
	style="width: {width};"
	data-testid="steering-bar"
	role="meter"
	aria-label="Steering input"
	aria-valuenow={clamped}
	aria-valuemin="-1"
	aria-valuemax="1"
>
	<!-- Track -->
	<div
		class="relative rounded-full"
		style="
			height: 6px;
			background: linear-gradient(180deg, rgba(58, 63, 71, 0.6) 0%, rgba(20, 23, 28, 0.8) 100%);
			border: 1px solid rgba(255, 255, 255, 0.08);
			box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7);
		"
	>
		<!-- Center tick -->
		<div
			class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
			style="width: 1px; height: 10px; background: rgba(255, 255, 255, 0.22);"
			aria-hidden="true"
		></div>

		<!-- Moving dot -->
		<div
			class="absolute top-1/2 -translate-y-1/2 rounded-full transition-[left] duration-100 ease-out"
			style="
				left: calc({dotPct}% - 6px);
				width: 12px;
				height: 12px;
				background: var(--color-tesla-text);
				box-shadow:
					0 0 6px rgba(255, 255, 255, 0.55),
					0 0 12px rgba(62, 130, 247, 0.35);
			"
			data-testid="steering-dot"
			data-pct={dotPct.toFixed(1)}
		></div>
	</div>
</div>
