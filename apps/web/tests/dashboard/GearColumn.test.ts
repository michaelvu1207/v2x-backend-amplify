import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import GearColumn from '$lib/components/dashboard/GearColumn.svelte';

describe('GearColumn', () => {
	it('renders all four gear letters', () => {
		const { getByTestId } = render(GearColumn, { props: { active: 'D' } });
		expect(getByTestId('gear-p')).toBeInTheDocument();
		expect(getByTestId('gear-r')).toBeInTheDocument();
		expect(getByTestId('gear-n')).toBeInTheDocument();
		expect(getByTestId('gear-d')).toBeInTheDocument();
	});

	it('marks the active gear with data-active="true" and others false', () => {
		const { getByTestId } = render(GearColumn, { props: { active: 'D' } });
		expect(getByTestId('gear-d').dataset.active).toBe('true');
		expect(getByTestId('gear-p').dataset.active).toBe('false');
		expect(getByTestId('gear-r').dataset.active).toBe('false');
		expect(getByTestId('gear-n').dataset.active).toBe('false');
	});

	it('marks R when reverse', () => {
		const { getByTestId } = render(GearColumn, { props: { active: 'R' } });
		expect(getByTestId('gear-r').dataset.active).toBe('true');
		expect(getByTestId('gear-d').dataset.active).toBe('false');
	});

	it('marks N when neutral', () => {
		const { getByTestId } = render(GearColumn, { props: { active: 'N' } });
		expect(getByTestId('gear-n').dataset.active).toBe('true');
	});

	it('marks P when parked', () => {
		const { getByTestId } = render(GearColumn, { props: { active: 'P' } });
		expect(getByTestId('gear-p').dataset.active).toBe('true');
	});

	it('defaults to row orientation', () => {
		const { getByTestId } = render(GearColumn, { props: { active: 'D' } });
		expect(getByTestId('gear-column').className).toContain('flex-row');
	});

	it('supports column orientation', () => {
		const { getByTestId } = render(GearColumn, {
			props: { active: 'D', orientation: 'column' },
		});
		expect(getByTestId('gear-column').className).toContain('flex-col');
	});
});
