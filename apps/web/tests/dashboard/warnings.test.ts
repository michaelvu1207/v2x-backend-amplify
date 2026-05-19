import { describe, it, expect } from 'vitest';
import {
	buildDashboardWarnings,
	mapSignalType,
	classifyV2xSource,
	VERDICT_TTL_MS,
} from '$lib/components/dashboard/warnings';
import type { V2xAlert, V2xZone, XoscFinishedEvent } from '$lib/types';

describe('mapSignalType', () => {
	it('maps alert to critical', () => {
		expect(mapSignalType('alert')).toBe('critical');
	});
	it('maps warning to warning', () => {
		expect(mapSignalType('warning')).toBe('warning');
	});
	it('maps info (and anything else) to info', () => {
		expect(mapSignalType('info')).toBe('info');
		expect(mapSignalType('unknown')).toBe('info');
	});
});

describe('classifyV2xSource', () => {
	it('flags firetruck messages as eva', () => {
		expect(classifyV2xSource('Firetruck approaching from behind')).toBe('eva');
		expect(classifyV2xSource('firetruck')).toBe('eva');
	});
	it('flags emergency keyword as eva', () => {
		expect(classifyV2xSource('Emergency vehicle')).toBe('eva');
	});
	it('defaults to v2x for generic messages', () => {
		expect(classifyV2xSource('Construction zone ahead')).toBe('v2x');
		expect(classifyV2xSource('Speed limit reduced')).toBe('v2x');
	});
});

function mkAlert(overrides: Partial<V2xAlert> = {}): V2xAlert {
	return {
		id: 1,
		message: 'Test alert',
		signal_type: 'warning',
		distance: 10,
		...overrides,
	};
}

function mkZone(overrides: Partial<V2xZone> = {}): V2xZone {
	return {
		id: 'z1',
		name: 'Test Zone',
		message: 'Zone alert',
		signal_type: 'warning',
		polygon: [
			[0, 0],
			[1, 0],
			[1, 1],
		],
		color: '#fff',
		...overrides,
	};
}

describe('buildDashboardWarnings', () => {
	it('returns empty for empty inputs', () => {
		const out = buildDashboardWarnings({
			v2xAlerts: [],
			activeZoneAlerts: [],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 1000,
		});
		expect(out).toEqual([]);
	});

	it('maps a V2xAlert to a DashboardWarning with correct id prefix and severity', () => {
		const out = buildDashboardWarnings({
			v2xAlerts: [mkAlert({ id: 7, signal_type: 'alert', message: 'Firetruck approaching' })],
			activeZoneAlerts: [],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 1000,
		});
		expect(out).toHaveLength(1);
		expect(out[0].id).toBe('v2x-7');
		expect(out[0].severity).toBe('critical');
		expect(out[0].source).toBe('eva');
		expect(out[0].detail).toBe('10.0m');
	});

	it('uses _lastSeen for lastUpdate when present', () => {
		const alert = mkAlert({ id: 3 }) as V2xAlert & { _lastSeen?: number };
		alert._lastSeen = 500;
		const out = buildDashboardWarnings({
			v2xAlerts: [alert],
			activeZoneAlerts: [],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 1000,
		});
		expect(out[0].lastUpdate).toBe(500);
	});

	it('falls back to now when _lastSeen is missing', () => {
		const out = buildDashboardWarnings({
			v2xAlerts: [mkAlert({ id: 4 })],
			activeZoneAlerts: [],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 2000,
		});
		expect(out[0].lastUpdate).toBe(2000);
	});

	it('omits detail when distance is missing', () => {
		const out = buildDashboardWarnings({
			v2xAlerts: [
				mkAlert({ id: 1, distance: undefined as unknown as number }),
			],
			activeZoneAlerts: [],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 1000,
		});
		expect(out[0].detail).toBeUndefined();
	});

	it('maps an active zone alert', () => {
		const out = buildDashboardWarnings({
			v2xAlerts: [],
			activeZoneAlerts: [{ zone: mkZone({ id: 'school', signal_type: 'alert' }) }],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 1000,
		});
		expect(out).toHaveLength(1);
		expect(out[0].id).toBe('zone-school');
		expect(out[0].severity).toBe('critical');
		expect(out[0].source).toBe('v2x');
		expect(out[0].lastUpdate).toBe(1000);
	});

	it('includes the scenario verdict within TTL', () => {
		const verdict: XoscFinishedEvent = {
			file: 'firetruck.xosc',
			exit_code: 0,
			verdict: 'SUCCESS',
			duration_sec: 42.5,
		};
		const out = buildDashboardWarnings({
			v2xAlerts: [],
			activeZoneAlerts: [],
			xoscLastResult: verdict,
			xoscResultSetAt: 1000,
			now: 1500, // 500ms after set; within 15s TTL
		});
		expect(out).toHaveLength(1);
		expect(out[0].id).toBe('verdict-1000');
		expect(out[0].severity).toBe('info');
		expect(out[0].source).toBe('verdict');
		expect(out[0].message).toContain('completed');
		expect(out[0].message).toContain('firetruck.xosc');
		expect(out[0].detail).toBe('42.5s');
	});

	it('drops the scenario verdict past TTL', () => {
		const verdict: XoscFinishedEvent = {
			file: 'sample.xosc',
			exit_code: 1,
			verdict: 'FAILURE',
			duration_sec: 10,
		};
		const out = buildDashboardWarnings({
			v2xAlerts: [],
			activeZoneAlerts: [],
			xoscLastResult: verdict,
			xoscResultSetAt: 0,
			now: VERDICT_TTL_MS + 1000,
		});
		expect(out).toEqual([]);
	});

	it('marks FAILURE verdict as critical', () => {
		const verdict: XoscFinishedEvent = {
			file: null,
			exit_code: 1,
			verdict: 'FAILURE',
			duration_sec: 5,
		};
		const out = buildDashboardWarnings({
			v2xAlerts: [],
			activeZoneAlerts: [],
			xoscLastResult: verdict,
			xoscResultSetAt: 1000,
			now: 1100,
		});
		expect(out).toHaveLength(1);
		expect(out[0].severity).toBe('critical');
		expect(out[0].message).toContain('failed');
	});

	it('combines all sources into one ordered list (preserving insertion order)', () => {
		const verdict: XoscFinishedEvent = {
			file: 'a.xosc',
			exit_code: 0,
			verdict: 'SUCCESS',
			duration_sec: 12,
		};
		const out = buildDashboardWarnings({
			v2xAlerts: [mkAlert({ id: 1 }), mkAlert({ id: 2 })],
			activeZoneAlerts: [{ zone: mkZone({ id: 'z1' }) }],
			xoscLastResult: verdict,
			xoscResultSetAt: 100,
			now: 200,
		});
		expect(out).toHaveLength(4);
		expect(out.map((w) => w.id)).toEqual([
			'v2x-1',
			'v2x-2',
			'zone-z1',
			'verdict-100',
		]);
	});

	it('handles a non-firetruck v2x alert correctly (source = v2x)', () => {
		const out = buildDashboardWarnings({
			v2xAlerts: [mkAlert({ id: 9, message: 'Construction zone ahead' })],
			activeZoneAlerts: [],
			xoscLastResult: null,
			xoscResultSetAt: null,
			now: 0,
		});
		expect(out[0].source).toBe('v2x');
	});
});
