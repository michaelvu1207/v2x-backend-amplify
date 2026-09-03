import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadRuntimeConfig, resetRuntimeConfigCache } from '$lib/runtime-config';

function jsonResponse(body: unknown, ok = true): Response {
	return { ok, json: async () => body } as Response;
}

const staticConfig = {
	apiBaseUrl: 'https://api.example.test',
	archiveVideoBaseUrl: 'https://drive.example.test/archive/',
	cloudflareDriveWsUrl: 'wss://static-drive.example.test',
	tailscaleDriveWsUrl: 'wss://static-tail.example.test'
};

beforeEach(() => {
	window.history.replaceState({}, '', '/');
	resetRuntimeConfigCache();
});

afterEach(() => {
	vi.unstubAllGlobals();
	resetRuntimeConfigCache();
});

describe('runtime config', () => {
	it('loads drive endpoints from config.json', async () => {
		const fetchMock = vi.fn().mockResolvedValue(jsonResponse(staticConfig));
		vi.stubGlobal('fetch', fetchMock);

		const config = await loadRuntimeConfig();

		expect(config.archiveVideoBaseUrl).toBe('https://drive.example.test/archive');
		expect(config.cloudflareDriveWsUrl).toBe('wss://static-drive.example.test');
		expect(config.tailscaleDriveWsUrl).toBe('wss://static-tail.example.test');
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringMatching(/^\/config\.json\?v=\d+$/),
			{ cache: 'no-store' }
		);
	});

	it('uses empty drive endpoints when config.json is unavailable', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

		const config = await loadRuntimeConfig();

		expect(config.cloudflareDriveWsUrl).toBe('');
		expect(config.tailscaleDriveWsUrl).toBe('');
	});

	it('keeps browser perception overrides independent of drive endpoints', async () => {
		window.history.replaceState(
			{},
			'',
			'/?perceptionStreamBaseUrl=https%3A%2F%2Fperception.example.test'
		);
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(staticConfig)));

		const config = await loadRuntimeConfig();

		expect(config.perceptionStreamBaseUrl).toBe('https://perception.example.test');
		expect(config.cloudflareDriveWsUrl).toBe('wss://static-drive.example.test');
	});

	it('reloads config.json after the cache is reset', async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce(jsonResponse(staticConfig))
			.mockResolvedValueOnce(jsonResponse({
				...staticConfig,
				cloudflareDriveWsUrl: 'wss://replacement-drive.example.test'
			}));
		vi.stubGlobal('fetch', fetchMock);

		await loadRuntimeConfig();
		resetRuntimeConfigCache();
		const config = await loadRuntimeConfig();

		expect(config.cloudflareDriveWsUrl).toBe('wss://replacement-drive.example.test');
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});
});
