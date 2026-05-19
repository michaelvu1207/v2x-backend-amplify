import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import SpeedDisplay from '$lib/components/dashboard/SpeedDisplay.svelte';

describe('SpeedDisplay', () => {
	it('renders mph by default and rounds correctly', () => {
		// 75 km/h ≈ 46.6 mph → rounds to 47
		const { getByTestId } = render(SpeedDisplay, { props: { speed: 75 } });
		expect(getByTestId('speed-value').textContent).toBe('47');
		expect(getByTestId('speed-unit').textContent).toBe('MPH');
	});

	it('renders km/h when unit prop is kmh', () => {
		const { getByTestId } = render(SpeedDisplay, { props: { speed: 75, unit: 'kmh' } });
		expect(getByTestId('speed-value').textContent).toBe('75');
		expect(getByTestId('speed-unit').textContent).toBe('KM/H');
	});

	it('renders 0 when stationary', () => {
		const { getByTestId } = render(SpeedDisplay, { props: { speed: 0 } });
		expect(getByTestId('speed-value').textContent).toBe('0');
	});

	it('rounds 0.4 km/h to 0 mph (sub-conversion threshold)', () => {
		const { getByTestId } = render(SpeedDisplay, { props: { speed: 0.4 } });
		expect(getByTestId('speed-value').textContent).toBe('0');
	});

	it('handles large speeds (160 km/h ≈ 99 mph)', () => {
		const { getByTestId } = render(SpeedDisplay, { props: { speed: 160 } });
		expect(getByTestId('speed-value').textContent).toBe('99');
	});
});
