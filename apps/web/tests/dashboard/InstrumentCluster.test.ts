import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import InstrumentCluster from '$lib/components/dashboard/InstrumentCluster.svelte';

describe('InstrumentCluster', () => {
	it('mounts and renders all child sub-components', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 50, gear: 'D', throttle: 0.3, brake: 0, steer: 0 },
		});
		expect(getByTestId('instrument-cluster')).toBeInTheDocument();
		expect(getByTestId('speed-display')).toBeInTheDocument();
		expect(getByTestId('gear-column')).toBeInTheDocument();
		expect(getByTestId('throttle-brake-bars')).toBeInTheDocument();
		expect(getByTestId('steer-readout')).toBeInTheDocument();
	});

	it('passes speed through to SpeedDisplay (50 km/h ≈ 31 mph)', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 50, gear: 'D', throttle: 0, brake: 0, steer: 0 },
		});
		expect(getByTestId('speed-value').textContent).toBe('31');
	});

	it('marks the active gear', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 0, gear: 'R', throttle: 0, brake: 0.5, steer: 0 },
		});
		expect(getByTestId('gear-r').dataset.active).toBe('true');
		expect(getByTestId('gear-d').dataset.active).toBe('false');
	});

	it('converts CARLA steer (-1..1) to degree readout', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 0, gear: 'D', throttle: 0, brake: 0, steer: 0.2 },
		});
		// 0.2 * 450 = 90
		expect(getByTestId('steer-degrees').textContent).toBe('+90°');
	});

	it('displays negative steer with no extra sign besides the minus', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 0, gear: 'D', throttle: 0, brake: 0, steer: -0.1 },
		});
		expect(getByTestId('steer-degrees').textContent).toBe('-45°');
	});

	it('shows 0° when steer is exactly 0', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 0, gear: 'D', throttle: 0, brake: 0, steer: 0 },
		});
		expect(getByTestId('steer-degrees').textContent).toBe('0°');
	});

	it('passes throttle/brake through to bars', () => {
		const { getByTestId } = render(InstrumentCluster, {
			props: { speed: 0, gear: 'D', throttle: 0.7, brake: 0.4, steer: 0 },
		});
		expect(getByTestId('throttle-bar').dataset.fill).toBe('0.700');
		expect(getByTestId('brake-bar').dataset.fill).toBe('0.400');
	});
});
