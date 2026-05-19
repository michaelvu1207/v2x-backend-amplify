import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import ThrottleBrakeBars from '$lib/components/dashboard/ThrottleBrakeBars.svelte';

describe('ThrottleBrakeBars', () => {
	it('renders both bars at zero fill when inputs are 0', () => {
		const { getByTestId } = render(ThrottleBrakeBars, {
			props: { throttle: 0, brake: 0 },
		});
		expect(getByTestId('throttle-bar').dataset.fill).toBe('0.000');
		expect(getByTestId('brake-bar').dataset.fill).toBe('0.000');
	});

	it('reflects throttle 0.5 as 0.500 fill', () => {
		const { getByTestId } = render(ThrottleBrakeBars, {
			props: { throttle: 0.5, brake: 0 },
		});
		expect(getByTestId('throttle-bar').dataset.fill).toBe('0.500');
	});

	it('clamps throttle above 1', () => {
		const { getByTestId } = render(ThrottleBrakeBars, {
			props: { throttle: 1.5, brake: 0 },
		});
		expect(getByTestId('throttle-bar').dataset.fill).toBe('1.000');
	});

	it('clamps brake below 0', () => {
		const { getByTestId } = render(ThrottleBrakeBars, {
			props: { throttle: 0, brake: -0.2 },
		});
		expect(getByTestId('brake-bar').dataset.fill).toBe('0.000');
	});

	it('reflects independent throttle and brake values', () => {
		const { getByTestId } = render(ThrottleBrakeBars, {
			props: { throttle: 0.8, brake: 0.3 },
		});
		expect(getByTestId('throttle-bar').dataset.fill).toBe('0.800');
		expect(getByTestId('brake-bar').dataset.fill).toBe('0.300');
	});

	it('exposes ARIA meter roles', () => {
		const { getByTestId } = render(ThrottleBrakeBars, {
			props: { throttle: 0.5, brake: 0.2 },
		});
		expect(getByTestId('throttle-bar').getAttribute('role')).toBe('meter');
		expect(getByTestId('brake-bar').getAttribute('role')).toBe('meter');
		expect(getByTestId('throttle-bar').getAttribute('aria-valuenow')).toBe('0.5');
		expect(getByTestId('brake-bar').getAttribute('aria-valuenow')).toBe('0.2');
	});
});
