<script lang="ts">
	let start = $state('');
	let end = $state('');
	let error = $state<string | null>(null);

	interface Props {
		onselect: (start: string, end: string) => void;
		disabled?: boolean;
	}
	let { onselect, disabled = false }: Props = $props();

	function quickSelect(minutes: number, label?: string) {
		const now = new Date();
		const endDate = new Date(now);
		const startDate = new Date(now.getTime() - minutes * 60 * 1000);
		start = toLocalDatetime(startDate);
		end = toLocalDatetime(endDate);
		validate();
	}

	function quickSelectYesterday(hour: number) {
		const yesterday = new Date();
		yesterday.setDate(yesterday.getDate() - 1);
		yesterday.setHours(hour, 0, 0, 0);
		const endDate = new Date(yesterday.getTime() + 60 * 60 * 1000);
		start = toLocalDatetime(yesterday);
		end = toLocalDatetime(endDate);
		validate();
	}

	function toLocalDatetime(d: Date): string {
		const pad = (n: number) => n.toString().padStart(2, '0');
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
	}

	function validate(): boolean {
		error = null;
		if (!start || !end) {
			error = 'Select both start and end times';
			return false;
		}
		const s = new Date(start);
		const e = new Date(end);
		if (e <= s) {
			error = 'End must be after start';
			return false;
		}
		if (e.getTime() - s.getTime() > 24 * 60 * 60 * 1000) {
			error = 'Range must be under 24 hours';
			return false;
		}
		if (e > new Date()) {
			error = 'Cannot select future times';
			return false;
		}
		return true;
	}

	function handleSubmit() {
		if (!validate()) return;
		const s = new Date(start).toISOString();
		const e = new Date(end).toISOString();
		onselect(s, e);
	}
</script>

<div class="flex flex-col gap-3">
	<h3 class="text-sm font-semibold text-gray-300 uppercase tracking-wider">Select Timeframe</h3>

	<div class="flex gap-2 flex-wrap">
		<button onclick={() => quickSelect(30)} class="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded-lg text-gray-300 transition-colors" {disabled}>
			Last 30 min
		</button>
		<button onclick={() => quickSelect(60)} class="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded-lg text-gray-300 transition-colors" {disabled}>
			Last hour
		</button>
		<button onclick={() => quickSelectYesterday(17)} class="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded-lg text-gray-300 transition-colors" {disabled}>
			Yesterday 5-6 PM
		</button>
	</div>

	<div class="grid grid-cols-2 gap-2">
		<label class="flex flex-col gap-1">
			<span class="text-xs text-gray-400">Start</span>
			<input type="datetime-local" bind:value={start} onchange={() => validate()} {disabled}
				class="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none" />
		</label>
		<label class="flex flex-col gap-1">
			<span class="text-xs text-gray-400">End</span>
			<input type="datetime-local" bind:value={end} onchange={() => validate()} {disabled}
				class="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none" />
		</label>
	</div>

	{#if error}
		<p class="text-xs text-red-400">{error}</p>
	{/if}

	<button onclick={handleSubmit} {disabled}
		class="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium text-white transition-colors">
		Reconstruct Scene
	</button>
</div>
