import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import CenterStack from '$lib/components/dashboard/CenterStack.svelte';

describe('CenterStack', () => {
	it('mounts an empty warning area when no warnings are passed', () => {
		const { getByTestId } = render(CenterStack, {
			props: { warnings: [], now: 0 },
		});
		expect(getByTestId('center-stack')).toBeInTheDocument();
		expect(getByTestId('warning-stack')).toBeInTheDocument();
	});

	it('renders a warning passed in', () => {
		const { getByTestId } = render(CenterStack, {
			props: {
				warnings: [
					{
						id: 'eva1',
						message: 'Firetruck approaching',
						severity: 'critical',
						source: 'eva',
						lastUpdate: 1000,
					},
				],
				now: 1000,
			},
		});
		expect(getByTestId('warning-eva1')).toBeInTheDocument();
	});

	it('applies the now prop to the WarningStack for fade decisions', () => {
		const { queryByTestId } = render(CenterStack, {
			props: {
				warnings: [
					{
						id: 'stale',
						message: 'Old alert',
						severity: 'info',
						source: 'scenario',
						lastUpdate: 0,
					},
				],
				now: 5000,
			},
		});
		expect(queryByTestId('warning-stale')).toBeNull();
	});
});
