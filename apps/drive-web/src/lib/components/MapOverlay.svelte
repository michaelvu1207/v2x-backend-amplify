<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import type { TrackedObject } from '$lib/types';
	import { MAP_CENTER, DEFAULT_ZOOM, MAP_STYLE_URL, OBJECT_COLORS } from '$lib/constants';

	interface Props {
		objects: TrackedObject[];
		roadLines: number[][][];
		selectedId: string | null;
		onselect?: (objectId: string) => void;
	}

	let { objects, roadLines, selectedId, onselect }: Props = $props();

	let mapContainer: HTMLDivElement;
	let map: maplibregl.Map | null = null;
	let popup: maplibregl.Popup | null = null;
	let mapReady = $state(false);

	onMount(() => {
		map = new maplibregl.Map({
			container: mapContainer,
			style: MAP_STYLE_URL,
			center: [MAP_CENTER.lon, MAP_CENTER.lat],
			zoom: DEFAULT_ZOOM,
			attributionControl: false,
			antialias: true
		});

		map.addControl(
			new maplibregl.AttributionControl({ compact: true }),
			'bottom-left'
		);

		map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');

		popup = new maplibregl.Popup({
			closeButton: false,
			closeOnClick: false,
			offset: 12,
			className: 'dt-popup'
		});

		map.on('load', () => {
			if (!map) return;
			mapReady = true;

			// Road lines source and layer
			map.addSource('road-lines', {
				type: 'geojson',
				data: buildRoadGeoJSON(roadLines)
			});

			map.addLayer({
				id: 'road-lines-layer',
				type: 'line',
				source: 'road-lines',
				paint: {
					'line-color': '#6b7280',
					'line-width': 2,
					'line-opacity': 0.6
				}
			});

			// Objects source and layers
			map.addSource('objects', {
				type: 'geojson',
				data: buildObjectsGeoJSON(objects)
			});

			// Object circle layer
			map.addLayer({
				id: 'objects-circles',
				type: 'circle',
				source: 'objects',
				paint: {
					'circle-radius': [
						'case',
						['==', ['get', 'selected'], true],
						10,
						6
					],
					'circle-color': ['get', 'color'],
					'circle-opacity': 0.85,
					'circle-stroke-width': [
						'case',
						['==', ['get', 'selected'], true],
						3,
						1.5
					],
					'circle-stroke-color': [
						'case',
						['==', ['get', 'selected'], true],
						'#ffffff',
						'rgba(255,255,255,0.3)'
					]
				}
			});

			// Pulsing ring for selected object
			map.addLayer({
				id: 'objects-selected-ring',
				type: 'circle',
				source: 'objects',
				filter: ['==', ['get', 'selected'], true],
				paint: {
					'circle-radius': 16,
					'circle-color': 'transparent',
					'circle-stroke-width': 2,
					'circle-stroke-color': '#ffffff',
					'circle-stroke-opacity': 0.4
				}
			});

			// Click handler
			map.on('click', 'objects-circles', (e) => {
				if (e.features && e.features.length > 0) {
					const feature = e.features[0];
					const objectId = feature.properties?.object_id;
					if (objectId) {
						onselect?.(objectId);
					}
				}
			});

			// Hover handlers
			map.on('mouseenter', 'objects-circles', (e) => {
				if (!map || !popup) return;
				map.getCanvas().style.cursor = 'pointer';

				if (e.features && e.features.length > 0) {
					const feature = e.features[0];
					const coords = (feature.geometry as GeoJSON.Point).coordinates.slice() as [number, number];
					const props = feature.properties;

					if (props) {
						const typeLabel = (props.object_type || 'unknown').replace(/_/g, ' ');
						const confidence = props.confidence != null
							? `${Math.round(parseFloat(props.confidence) * 100)}%`
							: 'N/A';

						popup
							.setLngLat(coords)
							.setHTML(
								`<div class="text-xs">` +
								`<div class="font-semibold" style="color: ${props.color}">${props.object_id}</div>` +
								`<div class="text-gray-400 capitalize">${typeLabel}</div>` +
								`<div class="text-gray-500">Confidence: ${confidence}</div>` +
								`</div>`
							)
							.addTo(map);
					}
				}
			});

			map.on('mouseleave', 'objects-circles', () => {
				if (!map || !popup) return;
				map.getCanvas().style.cursor = '';
				popup.remove();
			});
		});
	});

	onDestroy(() => {
		if (popup) popup.remove();
		if (map) map.remove();
		map = null;
		popup = null;
	});

	// Reactively update object markers
	$effect(() => {
		if (!map || !mapReady) return;

		const source = map.getSource('objects') as maplibregl.GeoJSONSource | undefined;
		if (source) {
			source.setData(buildObjectsGeoJSON(objects));
		}
	});

	// Reactively update road lines
	$effect(() => {
		if (!map || !mapReady) return;

		const source = map.getSource('road-lines') as maplibregl.GeoJSONSource | undefined;
		if (source) {
			source.setData(buildRoadGeoJSON(roadLines));
		}
	});

	function buildObjectsGeoJSON(objs: TrackedObject[]): GeoJSON.FeatureCollection {
		return {
			type: 'FeatureCollection',
			features: objs.map((obj) => ({
				type: 'Feature',
				geometry: {
					type: 'Point',
					coordinates: [obj.lon, obj.lat]
				},
				properties: {
					object_id: obj.object_id,
					object_type: obj.object_type,
					confidence: obj.confidence,
					color: OBJECT_COLORS[obj.object_type] ?? OBJECT_COLORS.default,
					selected: obj.object_id === selectedId
				}
			}))
		};
	}

	function buildRoadGeoJSON(lines: number[][][]): GeoJSON.FeatureCollection {
		return {
			type: 'FeatureCollection',
			features: lines.map((coords) => ({
				type: 'Feature',
				geometry: {
					type: 'LineString',
					coordinates: coords
				},
				properties: {}
			}))
		};
	}
</script>

<div class="relative h-full w-full overflow-hidden rounded-lg border border-gray-700/50 bg-gray-900">
	<div bind:this={mapContainer} class="h-full w-full"></div>

	<!-- Map legend -->
	<div class="absolute bottom-8 left-2 z-10 rounded-lg border border-gray-700/50 bg-gray-900/90 px-3 py-2 backdrop-blur-sm">
		<p class="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Legend</p>
		<div class="flex flex-col gap-1">
			{#each Object.entries(OBJECT_COLORS).filter(([k]) => k !== 'default') as [type, color]}
				<div class="flex items-center gap-2">
					<span
						class="h-2.5 w-2.5 rounded-full"
						style="background-color: {color};"
					></span>
					<span class="text-[10px] capitalize text-gray-400">
						{type.replace(/_/g, ' ')}
					</span>
				</div>
			{/each}
			<div class="flex items-center gap-2">
				<span class="h-0.5 w-2.5 rounded bg-gray-500"></span>
				<span class="text-[10px] text-gray-400">Road</span>
			</div>
		</div>
	</div>
</div>
