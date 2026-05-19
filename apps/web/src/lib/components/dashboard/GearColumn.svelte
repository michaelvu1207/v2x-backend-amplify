<script lang="ts">
	export type Gear = 'P' | 'R' | 'N' | 'D';

	interface Props {
		/** Active gear (P/R/N/D). Tesla-style — only one is highlighted. */
		active: Gear;
		/**
		 * Orientation. Defaults to `row` (Tesla S/X cluster style).
		 * `column` gives the Model 3-ish vertical stack.
		 */
		orientation?: 'row' | 'column';
	}

	let { active, orientation = 'row' }: Props = $props();

	const GEARS: Gear[] = ['P', 'R', 'N', 'D'];
</script>

<div
	class="font-tesla flex select-none {orientation === 'row'
		? 'flex-row gap-2 sm:gap-3 items-baseline'
		: 'flex-col gap-1 items-center'}"
	data-testid="gear-column"
	role="group"
	aria-label="Transmission gear"
>
	{#each GEARS as gear}
		{@const isActive = gear === active}
		<span
			class="font-medium leading-none tracking-wide transition-colors duration-200"
			class:is-active={isActive}
			style="
				font-size: 1.5rem;
				color: {isActive ? 'var(--color-tesla-text)' : 'var(--color-tesla-text-muted)'};
				opacity: {isActive ? 1 : 0.35};
			"
			data-testid="gear-{gear.toLowerCase()}"
			data-active={isActive}
		>
			{gear}
		</span>
	{/each}
</div>
