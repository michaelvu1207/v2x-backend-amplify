<script lang="ts">
	import WarningStack, {
		type DashboardWarning,
	} from './WarningStack.svelte';

	interface Props {
		warnings?: DashboardWarning[];
		/** Override `now` for tests. */
		now?: number;
	}

	let { warnings = [], now = Date.now() }: Props = $props();
</script>

<div
	class="relative w-full h-full overflow-hidden"
	data-testid="center-stack"
>
	<WarningStack {warnings} {now} />
</div>
