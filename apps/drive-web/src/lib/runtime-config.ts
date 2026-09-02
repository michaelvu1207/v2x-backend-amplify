interface DetectionRoutes {
	recent: string;
	byObject: string;
	byGeohash: string;
}

export interface RuntimeConfig {
	apiBaseUrl: string;
	detectionsApiBaseUrl: string;
	detectionRoutes: DetectionRoutes;
	stateBaseUrl: string;
	statePath: string;
	mapDataPath: string;
	demoVideosPath: string;
	videoCameraIds: string[];
	liveVideoUrlTemplate: string;
	perceptionStreamUrls: Record<string, string>;
	perceptionStreamBaseUrl: string;
	perceptionStreamPathTemplate: string;
	cloudflareDriveWsUrl: string;
	tailscaleDriveWsUrl: string;
}

const DEFAULT_CONFIG: RuntimeConfig = {
	apiBaseUrl: 'https://w0j9m7dgpg.execute-api.us-west-1.amazonaws.com',
	detectionsApiBaseUrl: 'https://w0j9m7dgpg.execute-api.us-west-1.amazonaws.com',
	detectionRoutes: {
		recent: '/detections/recent',
		byObject: '/detections/object/{object_id}',
		byGeohash: '/detections/geohash/{geohash}'
	},
	stateBaseUrl: 'https://w0j9m7dgpg.execute-api.us-west-1.amazonaws.com',
	statePath: '/state',
	mapDataPath: '/map-data',
	demoVideosPath: '/demo-videos',
	videoCameraIds: ['ch1', 'ch2', 'ch3', 'ch4'],
	liveVideoUrlTemplate: '',
	perceptionStreamUrls: {},
	perceptionStreamBaseUrl: '',
	perceptionStreamPathTemplate: '/streams/{camera_id}.mjpg',
	cloudflareDriveWsUrl: '',
	tailscaleDriveWsUrl: ''
};

let configPromise: Promise<RuntimeConfig> | null = null;


function withDefaultPath(path: string | undefined, fallback: string): string {
	if (!path) return fallback;
	return path.startsWith('/') ? path : `/${path}`;
}

function normalizeConfig(config: Partial<RuntimeConfig>): RuntimeConfig {
	const apiBaseUrl = (config.apiBaseUrl || DEFAULT_CONFIG.apiBaseUrl).replace(/\/+$/, '');
	const detectionsApiBaseUrl = (
		config.detectionsApiBaseUrl ||
		config.apiBaseUrl ||
		DEFAULT_CONFIG.detectionsApiBaseUrl
	).replace(/\/+$/, '');

	return {
		apiBaseUrl,
		detectionsApiBaseUrl,
		detectionRoutes: {
			recent: withDefaultPath(
				config.detectionRoutes?.recent,
				DEFAULT_CONFIG.detectionRoutes.recent
			),
			byObject: withDefaultPath(
				config.detectionRoutes?.byObject,
				DEFAULT_CONFIG.detectionRoutes.byObject
			),
			byGeohash: withDefaultPath(
				config.detectionRoutes?.byGeohash,
				DEFAULT_CONFIG.detectionRoutes.byGeohash
			)
		},
		stateBaseUrl: (
			config.stateBaseUrl ||
			config.apiBaseUrl ||
			DEFAULT_CONFIG.stateBaseUrl
		).replace(/\/+$/, ''),
		statePath: withDefaultPath(config.statePath, DEFAULT_CONFIG.statePath),
		mapDataPath: withDefaultPath(config.mapDataPath, DEFAULT_CONFIG.mapDataPath),
		demoVideosPath: withDefaultPath(config.demoVideosPath, DEFAULT_CONFIG.demoVideosPath),
		videoCameraIds: config.videoCameraIds || DEFAULT_CONFIG.videoCameraIds,
		liveVideoUrlTemplate: config.liveVideoUrlTemplate || DEFAULT_CONFIG.liveVideoUrlTemplate,
		perceptionStreamUrls: config.perceptionStreamUrls || DEFAULT_CONFIG.perceptionStreamUrls,
		perceptionStreamBaseUrl: (config.perceptionStreamBaseUrl || DEFAULT_CONFIG.perceptionStreamBaseUrl).replace(/\/+$/, ''),
		perceptionStreamPathTemplate:
			config.perceptionStreamPathTemplate || DEFAULT_CONFIG.perceptionStreamPathTemplate,
		cloudflareDriveWsUrl: config.cloudflareDriveWsUrl || DEFAULT_CONFIG.cloudflareDriveWsUrl,
		tailscaleDriveWsUrl: config.tailscaleDriveWsUrl || DEFAULT_CONFIG.tailscaleDriveWsUrl,
	};
}


function withBrowserOverrides(config: RuntimeConfig): RuntimeConfig {
	if (typeof window === 'undefined') return config;

	const params = new URLSearchParams(window.location.search);
	const perceptionStreamBaseUrl =
		params.get('perceptionStreamBaseUrl') || params.get('perceptionBaseUrl');
	const perceptionStreamPathTemplate = params.get('perceptionStreamPathTemplate');
	if (!perceptionStreamBaseUrl && !perceptionStreamPathTemplate) return config;

	return normalizeConfig({
		...config,
		perceptionStreamBaseUrl: perceptionStreamBaseUrl || config.perceptionStreamBaseUrl,
		perceptionStreamPathTemplate:
			perceptionStreamPathTemplate || config.perceptionStreamPathTemplate
	});
}


export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
	if (!configPromise) {
		const configUrl = `/config.json?v=${Date.now()}`;
		configPromise = fetch(configUrl, { cache: 'no-store' })
			.then(async (response) => {
				if (!response.ok) {
					return DEFAULT_CONFIG;
				}
				return withBrowserOverrides(
					normalizeConfig((await response.json()) as Partial<RuntimeConfig>)
				);
			})
			.catch(() => DEFAULT_CONFIG);
	}

	return configPromise;
}

/** Clear the memoized config so an explicit refresh can reload config.json. */
export function resetRuntimeConfigCache(): void {
	configPromise = null;
}

export function resolveLiveVideoUrl(template: string, cameraId: string): string {
	return template.trim().replace('{camera_id}', encodeURIComponent(cameraId));
}

export function buildAssetUrl(baseUrl: string, path: string): string {
	return `${baseUrl.replace(/\/+$/, '')}${withDefaultPath(path, '/')}`;
}
