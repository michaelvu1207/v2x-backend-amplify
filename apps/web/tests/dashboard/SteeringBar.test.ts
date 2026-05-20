import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import SteeringBar from '$lib/components/dashboard/SteeringBar.svelte';

describe('SteeringBar', () => {
	it('centers the dot at 50% when steer is 0', () => {
		const { getByTestId } = render(SteeringBar, { props: { steer: 0 } });
		expect(getByTestId('steering-dot').dataset.pct).toBe('50.0');
	});

	it('moves the dot to 0% on full left', () => {
		const { getByTestId } = render(SteeringBar, { props: { steer: -1 } });
		expect(getByTestId('steering-dot').dataset.pct).toBe('0.0');
	});

	it('moves the dot to 100% on full right', () => {
		const { getByTestId } = render(SteeringBar, { props: { steer: 1 } });
		expect(getByTestId('steering-dot').dataset.pct).toBe('100.0');
	});

	it('clamps steer above +1', () => {
		const { getByTestId } = render(SteeringBar, { props: { steer: 2 } });
		expect(getByTestId('steering-dot').dataset.pct).toBe('100.0');
	});

	it('clamps steer below -1', () => {
		const { getByTestId } = render(SteeringBar, { props: { steer: -2 } });
		expect(getByTestId('steering-dot').dataset.pct).toBe('0.0');
	});

	it('maps half steer (+0.5) to 75%', () => {
		const { getByTestId } = render(SteeringBar, { props: { steer: 0.5 } });
		expect(getByTestId('steering-dot').dataset.pct).toBe('75.0');
	});
});
