# Autopilot Actor Geofence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Add Actor panel spawn a selected vehicle, such as a firefighter/firetruck, as a CARLA Traffic Manager autopilot actor with a custom moving geofence radius and a persistent warning while the ego vehicle is inside that radius.

**Architecture:** Keep the existing static `spawn_object` flow for parked vehicles and props. Add a separate `spawn_dynamic_actor` WebSocket flow that spawns vehicle blueprints through CARLA Traffic Manager, tracks their live position/radius in backend session state, emits them on telemetry, and lets the frontend render moving geofence circles from live actor positions. Dynamic actor geofences are session-scoped and should not be stored as static V2X polygon zones because their geometry follows the actor.

**Tech Stack:** Python CARLA 0.9.16 bridge, WebSocket JSON messages, pytest, SvelteKit/Svelte 5, Svelte stores, MapLibre GL, Node `node:test`.

---

## Current Code Map

- `apps/bridge/digital_twin_bridge/drive_server.py`: owns session lifecycle, static object placement, Traffic Manager traffic spawning, telemetry, and WebSocket message routing.
- `apps/bridge/tests/conftest.py`: mocked CARLA world, actors, blueprints, and client used by bridge unit tests.
- `apps/bridge/tests/test_drive_server.py`: session and message routing tests.
- `apps/web/src/lib/types.ts`: shared drive UI message and telemetry types.
- `apps/web/src/lib/stores/driveSocket.ts`: WebSocket connection, message handling, and actions sent by the drive page.
- `apps/web/src/lib/stores/v2xZones.ts`: static drawn zone storage and proximity alerts.
- `apps/web/src/lib/components/DriveMiniMap.svelte`: MapLibre rendering for roads, ego vehicle, nearby actors, and drawn geofences.
- `apps/web/src/lib/components/V2xToast.svelte`: server V2X alerts and drawn zone notifications.
- `apps/web/src/routes/drive/+page.svelte`: drive page state, Add Actor panel, session control, telemetry-driven proximity checks.

## Behavioral Contract

- Static spawn stays unchanged: props and parked vehicles continue to use `spawn_object`.
- Autopilot spawn is available only for `SpawnableObject.category === 'vehicle'`.
- The default dynamic actor radius is `35` meters.
- Radius is clamped to `5` through `250` meters in the frontend and backend.
- The dynamic actor alert is persistent while the ego vehicle is inside the radius and disappears immediately after exit.
- The moving geofence is drawn on the map as a red circle around the actor's current CARLA position.
- Dynamic actor geofences are not saved in scenario files and are cleared when the drive session ends.

---

### Task 1: Backend Test Harness For Traffic Manager Actors

**Files:**
- Modify: `apps/bridge/tests/conftest.py`
- Test: `apps/bridge/tests/test_drive_server.py`

- [ ] **Step 1: Extend `MockActor` with autopilot tracking**

In `apps/bridge/tests/conftest.py`, replace the current `MockActor.__init__` body and add `set_autopilot` after `set_transform`:

```python
def __init__(self, actor_id: int, type_id: str = "vehicle.tesla.model3"):
    self.id = actor_id
    self.type_id = type_id
    self._transform = MockTransform()
    self._control = MockVehicleControl()
    self._velocity = MockLocation(x=0, y=0, z=0)
    self._destroyed = False
    self.autopilot_enabled = False
    self.traffic_manager_port: Optional[int] = None
    self.control_history: list[MockVehicleControl] = []
```

```python
def set_autopilot(self, enabled: bool, tm_port: Optional[int] = None) -> None:
    self.autopilot_enabled = enabled
    self.traffic_manager_port = tm_port
```

- [ ] **Step 2: Replace `MockBlueprint` with attribute support**

In `apps/bridge/tests/conftest.py`, replace the current `MockBlueprint` class with:

```python
class MockBlueprintAttribute:
    def __init__(self, value: str, recommended_values: Optional[list[str]] = None):
        self.value = value
        self.recommended_values = recommended_values or [value]

    def __int__(self) -> int:
        return int(self.value)

    def __str__(self) -> str:
        return self.value


class MockBlueprint:
    def __init__(self, bp_id: str, attributes: Optional[dict[str, MockBlueprintAttribute]] = None):
        self.id = bp_id
        self._attributes = attributes or {}
        if bp_id.startswith("vehicle."):
            self._attributes.setdefault("number_of_wheels", MockBlueprintAttribute("4"))
            self._attributes.setdefault("color", MockBlueprintAttribute("255,255,255", ["255,255,255", "180,0,0"]))

    def has_attribute(self, key: str) -> bool:
        return key in self._attributes

    def get_attribute(self, key: str) -> MockBlueprintAttribute:
        return self._attributes[key]

    def set_attribute(self, key: str, value: str) -> None:
        self._attributes[key] = MockBlueprintAttribute(value)
```

- [ ] **Step 3: Add a firetruck vehicle blueprint**

In `MockBlueprintLibrary.__init__`, change the `_blueprints` dictionary to include the firetruck:

```python
self._blueprints = {
    "vehicle.tesla.model3": MockBlueprint("vehicle.tesla.model3"),
    "vehicle.carlamotors.firetruck": MockBlueprint("vehicle.carlamotors.firetruck"),
    "static.prop.trafficcone01": MockBlueprint("static.prop.trafficcone01"),
    "static.prop.trafficwarning": MockBlueprint("static.prop.trafficwarning"),
    "sensor.camera.rgb": MockBlueprint("sensor.camera.rgb"),
}
```

- [ ] **Step 4: Add a mock Traffic Manager**

In `apps/bridge/tests/conftest.py`, add this class above `MockClient`:

```python
class MockTrafficManager:
    def __init__(self, port: int = 8000):
        self._port = port
        self.synchronous_mode = False
        self.speed_difference = 0.0
        self.distance_to_leading_vehicle = 2.0
        self.ignore_lights: dict[int, float] = {}
        self.ignore_signs: dict[int, float] = {}

    def get_port(self) -> int:
        return self._port

    def set_synchronous_mode(self, enabled: bool) -> None:
        self.synchronous_mode = enabled

    def global_percentage_speed_difference(self, value: float) -> None:
        self.speed_difference = value

    def set_global_distance_to_leading_vehicle(self, value: float) -> None:
        self.distance_to_leading_vehicle = value

    def ignore_lights_percentage(self, actor: MockActor, value: float) -> None:
        self.ignore_lights[actor.id] = value

    def ignore_signs_percentage(self, actor: MockActor, value: float) -> None:
        self.ignore_signs[actor.id] = value
```

- [ ] **Step 5: Add `get_trafficmanager` to `MockClient`**

In `MockClient.__init__`, add:

```python
self._traffic_manager = MockTrafficManager()
```

Then add this method:

```python
def get_trafficmanager(self) -> MockTrafficManager:
    return self._traffic_manager
```

- [ ] **Step 6: Write failing backend tests**

Append this test class to `apps/bridge/tests/test_drive_server.py`:

```python
@pytest.mark.unit
class TestDynamicActorGeofences:
    @pytest.mark.asyncio
    async def test_spawn_dynamic_actor_sets_autopilot_and_emits_telemetry(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")

        result = session.spawn_dynamic_actor(
            blueprint_id="vehicle.carlamotors.firetruck",
            geofence_radius=42.0,
            message="Firefighter response vehicle active",
        )

        assert result["type"] == "dynamic_actor_spawned"
        actor_id = result["actor"]["actor_id"]
        actor = mock_world.get_actor(actor_id)
        assert actor is not None
        assert actor.type_id == "vehicle.carlamotors.firetruck"
        assert actor.autopilot_enabled is True
        assert actor.traffic_manager_port == 8000
        assert result["actor"]["geofence_radius"] == 42.0

        telemetry = session.apply_control(steer=0.0, throttle=0.0, brake=0.0)
        assert telemetry["dynamic_actors"][0]["actor_id"] == actor_id
        assert telemetry["dynamic_actors"][0]["message"] == "Firefighter response vehicle active"
        assert telemetry["nearby_actors"][0]["type"] == "dynamic"

    @pytest.mark.asyncio
    async def test_dynamic_actor_radius_is_clamped(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")

        small = session.spawn_dynamic_actor("vehicle.tesla.model3", geofence_radius=1.0)
        large = session.spawn_dynamic_actor("vehicle.tesla.model3", geofence_radius=999.0)

        assert small["actor"]["geofence_radius"] == 5.0
        assert large["actor"]["geofence_radius"] == 250.0

    @pytest.mark.asyncio
    async def test_despawn_dynamic_actor_disables_autopilot_and_removes_snapshot(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import DriveSession

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await session.start("2026-03-22T17:00:00Z", "2026-03-22T17:30:00Z")
        spawned = session.spawn_dynamic_actor("vehicle.carlamotors.firetruck", geofence_radius=35.0)
        actor_id = spawned["actor"]["actor_id"]
        actor = mock_world.get_actor(actor_id)

        result = session.despawn_dynamic_actor(actor_id)

        assert result == {"type": "dynamic_actor_despawned", "actor_id": actor_id, "count": 0}
        assert actor.autopilot_enabled is False
        assert actor.is_destroyed is True
        assert session.get_dynamic_actors_snapshot() == []

    @pytest.mark.asyncio
    async def test_handle_spawn_dynamic_actor_message(self, mock_world, fake_v2x_api):
        from digital_twin_bridge.drive_server import DriveSession, handle_message

        session = DriveSession(
            world=mock_world,
            carla_map=mock_world.get_map(),
            api_fetcher=fake_v2x_api.get_detections_range,
        )
        await handle_message(session, {
            "type": "start_session",
            "start": "2026-03-22T17:00:00Z",
            "end": "2026-03-22T17:30:00Z",
        })

        response = await handle_message(session, {
            "type": "spawn_dynamic_actor",
            "blueprint": "vehicle.carlamotors.firetruck",
            "geofence_radius": 45,
            "message": "Firefighter route active",
        })

        assert response["type"] == "dynamic_actor_spawned"
        assert response["actor"]["blueprint"] == "vehicle.carlamotors.firetruck"
        assert response["actor"]["geofence_radius"] == 45.0
        assert response["actor"]["message"] == "Firefighter route active"
```

- [ ] **Step 7: Run the focused tests and confirm they fail**

Run:

```bash
cd apps/bridge
pytest tests/test_drive_server.py -k dynamic_actor -v
```

Expected: fails because `DriveSession.spawn_dynamic_actor`, `despawn_dynamic_actor`, `get_dynamic_actors_snapshot`, and WebSocket routing do not exist yet.

- [ ] **Step 8: Commit the failing tests**

```bash
git add apps/bridge/tests/conftest.py apps/bridge/tests/test_drive_server.py
git commit -m "test: cover dynamic autopilot actor geofences"
```

---

### Task 2: Backend Dynamic Actor Session Support

**Files:**
- Modify: `apps/bridge/digital_twin_bridge/drive_server.py`
- Test: `apps/bridge/tests/test_drive_server.py`

- [ ] **Step 1: Add dynamic actor module tracking and metadata**

Near `_traffic_actor_ids`, add:

```python
# Dynamic actors are individually spawned from the Add Actor panel and carry
# session-scoped moving geofences.
_dynamic_actor_ids: set[int] = set()
```

Below the traffic constants, add:

```python
@dataclass
class DynamicActorMeta:
    actor_id: int
    blueprint: str
    name: str
    geofence_radius: float
    message: str
```

- [ ] **Step 2: Add a blueprint display helper**

Below `get_spawnable_objects`, add:

```python
def display_name_from_blueprint(blueprint_id: str) -> str:
    parts = blueprint_id.split(".")
    if len(parts) >= 3:
        make = parts[1].title()
        model = parts[2].replace("_", " ").title()
        return f"{make} {model}"
    return blueprint_id
```

- [ ] **Step 3: Initialize session dynamic actor state**

In `DriveSession.__init__`, after `self._placed_objects`, add:

```python
self._dynamic_actors: dict[int, DynamicActorMeta] = {}
```

- [ ] **Step 4: Add Traffic Manager helper**

Add this method inside `DriveSession`, directly above `spawn_traffic`:

```python
def _get_traffic_manager(self):
    """Return a CARLA Traffic Manager and its port.

    Unit tests run without the CARLA Python package, so this follows the
    existing mock fallback pattern used elsewhere in this file.
    """
    try:
        import carla
        client = carla.Client("localhost", 2000)
    except ImportError:
        from tests.conftest import MockClient
        client = MockClient(self._world)

    client.set_timeout(10.0)
    tm = client.get_trafficmanager()
    tm.set_synchronous_mode(True)
    return tm, tm.get_port()
```

- [ ] **Step 5: Add CARLA transform helper for tests and production**

Add this method inside `DriveSession`, directly above `spawn_dynamic_actor` from the next step:

```python
def _build_transform(self, location, rotation):
    try:
        import carla
        return carla.Transform(location, rotation)
    except ImportError:
        from tests.conftest import MockTransform
        return MockTransform(location, rotation)
```

- [ ] **Step 6: Implement dynamic actor spawn and serialization**

Add these methods inside `DriveSession`, directly above `spawn_traffic`:

```python
def spawn_dynamic_actor(
    self,
    blueprint_id: str,
    geofence_radius: float = 35.0,
    message: str = "",
) -> dict:
    """Spawn one selected vehicle as an autopilot actor with a moving geofence."""
    if not self._active or self.vehicle is None:
        raise RuntimeError("No active session")
    if not blueprint_id.startswith("vehicle."):
        raise ValueError("Dynamic actors must use vehicle blueprints")

    import random

    bp_lib = self._world.get_blueprint_library()
    bp = bp_lib.find(blueprint_id)
    if bp is None:
        raise ValueError(f"Blueprint not found: {blueprint_id}")

    if bp.has_attribute("number_of_wheels") and int(bp.get_attribute("number_of_wheels")) < 4:
        raise ValueError("Dynamic actors must be four-wheeled vehicles")

    radius = max(5.0, min(250.0, float(geofence_radius)))
    actor_message = (message or f"{display_name_from_blueprint(blueprint_id)} geofence active").strip()

    tm, tm_port = self._get_traffic_manager()

    if bp.has_attribute("color"):
        colors = bp.get_attribute("color").recommended_values
        if colors:
            bp.set_attribute("color", random.choice(colors))
    bp.set_attribute("role_name", "dynamic_geofence")

    spawn_points = self._filter_spawn_points_near_placed(self._map.get_spawn_points(), radius=12.0)
    random.shuffle(spawn_points)
    if not spawn_points:
        raise RuntimeError("No safe spawn points available for dynamic actor")

    actor = None
    for spawn_point in spawn_points:
        actor = self._world.try_spawn_actor(bp, spawn_point)
        if actor is not None:
            break
    if actor is None:
        raise RuntimeError(f"Failed to spawn {blueprint_id} for autopilot")

    actor.set_autopilot(True, tm_port)
    try:
        tm.ignore_lights_percentage(actor, 0.0)
        tm.ignore_signs_percentage(actor, 0.0)
    except Exception:
        pass

    meta = DynamicActorMeta(
        actor_id=actor.id,
        blueprint=blueprint_id,
        name=display_name_from_blueprint(blueprint_id),
        geofence_radius=radius,
        message=actor_message,
    )
    self._dynamic_actors[actor.id] = meta
    _dynamic_actor_ids.add(actor.id)

    logger.info(
        "Spawned dynamic actor %s (id=%d) geofence=%.1fm",
        blueprint_id,
        actor.id,
        radius,
    )

    return {
        "type": "dynamic_actor_spawned",
        "actor": self._serialize_dynamic_actor(actor, meta),
        "count": len(self._dynamic_actors),
    }

def _serialize_dynamic_actor(self, actor, meta: DynamicActorMeta) -> dict:
    transform = actor.get_transform()
    return {
        "actor_id": meta.actor_id,
        "blueprint": meta.blueprint,
        "name": meta.name,
        "pos": [
            round(transform.location.x, 2),
            round(transform.location.y, 2),
            round(transform.location.z, 2),
        ],
        "yaw": round(transform.rotation.yaw, 1),
        "geofence_radius": meta.geofence_radius,
        "message": meta.message,
        "autopilot": True,
    }

def get_dynamic_actors_snapshot(self) -> list[dict]:
    """Return live dynamic actor positions and remove actors no longer in the world."""
    snapshot: list[dict] = []
    stale_ids: list[int] = []
    for actor_id, meta in self._dynamic_actors.items():
        actor = self._world.get_actor(actor_id)
        if actor is None or getattr(actor, "is_destroyed", False):
            stale_ids.append(actor_id)
            continue
        snapshot.append(self._serialize_dynamic_actor(actor, meta))

    for actor_id in stale_ids:
        self._dynamic_actors.pop(actor_id, None)
        _dynamic_actor_ids.discard(actor_id)

    return snapshot

def _destroy_dynamic_actor(self, actor_id: int) -> bool:
    actor = self._world.get_actor(actor_id)
    destroyed = False
    if actor is not None:
        try:
            actor.set_autopilot(False)
        except Exception:
            pass
        try:
            actor.destroy()
            destroyed = True
        except Exception as e:
            logger.debug("Failed to destroy dynamic actor %d: %s", actor_id, e)

    self._dynamic_actors.pop(actor_id, None)
    _dynamic_actor_ids.discard(actor_id)
    return destroyed

def despawn_dynamic_actor(self, actor_id: int) -> dict:
    """Remove one Add Actor autopilot vehicle."""
    if not self._active:
        raise RuntimeError("No active session")
    actor_id = int(actor_id)
    if actor_id not in self._dynamic_actors:
        return {"type": "dynamic_actor_missing", "actor_id": actor_id, "count": len(self._dynamic_actors)}

    self._destroy_dynamic_actor(actor_id)
    return {"type": "dynamic_actor_despawned", "actor_id": actor_id, "count": len(self._dynamic_actors)}

def despawn_dynamic_actors(self) -> dict:
    """Remove all Add Actor autopilot vehicles."""
    if not self._active:
        raise RuntimeError("No active session")
    count = 0
    for actor_id in list(self._dynamic_actors):
        if self._destroy_dynamic_actor(actor_id):
            count += 1
    return {"type": "dynamic_actors_despawned", "count": count}
```

- [ ] **Step 7: Emit dynamic actor telemetry**

In `apply_control`, add the `dynamic_actors` field next to `nearby_actors`:

```python
"nearby_actors": self.get_nearby_actors(),
"dynamic_actors": self.get_dynamic_actors_snapshot(),
```

- [ ] **Step 8: Classify dynamic actors on the mini-map telemetry list**

In `get_nearby_actors`, replace the `"type"` expression with:

```python
"type": (
    "dynamic" if a.id in _dynamic_actor_ids
    else "traffic" if a.id in _traffic_actor_ids
    else "other"
),
```

- [ ] **Step 9: Clean up dynamic actors at session end**

In `_force_cleanup`, after the vehicle cleanup block and before user-placed object cleanup, add:

```python
# Dynamic Add Actor autopilot vehicles
for actor_id in list(self._dynamic_actors):
    self._destroy_dynamic_actor(actor_id)
self._dynamic_actors.clear()
```

- [ ] **Step 10: Route dynamic actor WebSocket messages**

In `handle_message`, after the `spawn_object` branch, add:

```python
elif msg_type == "spawn_dynamic_actor":
    return session.spawn_dynamic_actor(
        blueprint_id=msg["blueprint"],
        geofence_radius=float(msg.get("geofence_radius", 35.0)),
        message=str(msg.get("message", "")),
    )
elif msg_type == "despawn_dynamic_actor":
    return session.despawn_dynamic_actor(int(msg["actor_id"]))
elif msg_type == "despawn_dynamic_actors":
    return session.despawn_dynamic_actors()
```

- [ ] **Step 11: Run backend tests**

Run:

```bash
cd apps/bridge
pytest tests/test_drive_server.py -k dynamic_actor -v
```

Expected: all dynamic actor tests pass.

- [ ] **Step 12: Run the broader bridge test file**

Run:

```bash
cd apps/bridge
pytest tests/test_drive_server.py -v
```

Expected: the full drive server test file passes.

- [ ] **Step 13: Commit backend implementation**

```bash
git add apps/bridge/digital_twin_bridge/drive_server.py apps/bridge/tests/conftest.py apps/bridge/tests/test_drive_server.py
git commit -m "feat: spawn dynamic autopilot actors with geofences"
```

---

### Task 3: Frontend Dynamic Actor Types And Socket Actions

**Files:**
- Modify: `apps/web/src/lib/types.ts`
- Modify: `apps/web/src/lib/stores/driveSocket.ts`

- [ ] **Step 1: Add dynamic actor types**

In `apps/web/src/lib/types.ts`, replace `NearbyActor.type` with:

```ts
type: 'traffic' | 'dynamic' | 'other';
```

After `NearbyActor`, add:

```ts
export interface DynamicActor {
	actor_id: number;
	blueprint: string;
	name: string;
	pos: [number, number, number];
	yaw: number;
	geofence_radius: number;
	message: string;
	autopilot: boolean;
}

export interface ActorGeofenceAlert {
	actor: DynamicActor;
	distance: number;
}
```

In `VehicleTelemetry`, add:

```ts
dynamic_actors?: DynamicActor[];
```

- [ ] **Step 2: Import the new type in the socket store**

In `apps/web/src/lib/stores/driveSocket.ts`, add `DynamicActor` to the type import:

```ts
import type { DriveSessionState, VehicleTelemetry, CameraView, DriveMessage, VehicleOption, SpawnableObject, PlacedObject, ScenarioInfo, V2xSignal, V2xAlert, V2xZone, TrajectoryInfo, TrajectoryStatus, DynamicActor } from '$lib/types';
```

- [ ] **Step 3: Add a dynamic actors store**

Below `trajectoryStatus`, add:

```ts
export const dynamicActors = writable<DynamicActor[]>([]);
```

- [ ] **Step 4: Keep dynamic actor state in sync with server messages**

In `handleServerMessage`, inside the `telemetry` case after `telemetry.set(...)`, add:

```ts
dynamicActors.set((msg.dynamic_actors as DynamicActor[]) ?? []);
```

Add these cases before the `error` case:

```ts
case 'dynamic_actor_spawned':
	dynamicActors.update(list => {
		const actor = msg.actor as DynamicActor;
		return [...list.filter(a => a.actor_id !== actor.actor_id), actor];
	});
	break;

case 'dynamic_actor_despawned':
	dynamicActors.update(list => list.filter(a => a.actor_id !== (msg.actor_id as number)));
	break;

case 'dynamic_actors_despawned':
	dynamicActors.set([]);
	break;
```

In the `session_ended` case, add:

```ts
dynamicActors.set([]);
```

In `disconnect()`, add:

```ts
dynamicActors.set([]);
```

- [ ] **Step 5: Add socket actions**

Below `spawnObject`, add:

```ts
export function spawnDynamicActor(
	blueprint: string,
	geofenceRadius: number = 35,
	message: string = ''
): void {
	const radius = Math.max(5, Math.min(250, Number.isFinite(geofenceRadius) ? geofenceRadius : 35));
	send({ type: 'spawn_dynamic_actor', blueprint, geofence_radius: radius, message });
}

export function despawnDynamicActor(actorId: number): void {
	send({ type: 'despawn_dynamic_actor', actor_id: actorId });
}

export function despawnDynamicActors(): void {
	send({ type: 'despawn_dynamic_actors' });
}
```

- [ ] **Step 6: Run frontend type/build checks**

Run:

```bash
cd apps/web
npm run build
```

Expected: build succeeds. Existing `npm run check` diagnostics unrelated to these files can still be handled in a separate cleanup pass.

- [ ] **Step 7: Commit socket/type changes**

```bash
git add apps/web/src/lib/types.ts apps/web/src/lib/stores/driveSocket.ts
git commit -m "feat: track dynamic actors in drive socket state"
```

---

### Task 4: Frontend Actor Geofence Rules And Proximity Store

**Files:**
- Create: `apps/web/src/lib/geo.ts`
- Create: `apps/web/src/lib/actorGeofenceRules.ts`
- Create: `apps/web/src/lib/stores/actorGeofences.ts`
- Create: `apps/web/scripts/actorGeofenceRules.test.mjs`
- Modify: `apps/web/src/lib/stores/v2xZones.ts`

- [ ] **Step 1: Extract reusable CARLA to GPS conversion**

Create `apps/web/src/lib/geo.ts`:

```ts
export function carlaToGps(
	x: number,
	y: number,
	originLat: number,
	originLon: number
): [number, number] {
	const METERS_PER_DEGREE = 111320;
	const lat = originLat - y / METERS_PER_DEGREE;
	const lon =
		originLon + x / (METERS_PER_DEGREE * Math.cos((originLat * Math.PI) / 180));
	return [lon, lat];
}
```

- [ ] **Step 2: Re-export the conversion from the existing zone store**

In `apps/web/src/lib/stores/v2xZones.ts`, replace the current `carlaToGps` function with:

```ts
export { carlaToGps } from '$lib/geo';
```

- [ ] **Step 3: Write actor geofence rule tests**

Create `apps/web/scripts/actorGeofenceRules.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';

import {
	buildActorGeofencePolygon,
	getActorGeofenceAlert,
} from '../src/lib/actorGeofenceRules.ts';

const actor = {
	actor_id: 42,
	blueprint: 'vehicle.carlamotors.firetruck',
	name: 'Carlamotors Firetruck',
	pos: [100, 200, 0],
	yaw: 90,
	geofence_radius: 35,
	message: 'Firefighter response vehicle active',
	autopilot: true,
};

test('buildActorGeofencePolygon returns a closed circle polygon in lon/lat order', () => {
	const polygon = buildActorGeofencePolygon(actor, 37.915, -122.335, 12);

	assert.equal(polygon.length, 13);
	assert.deepEqual(polygon[0], polygon[polygon.length - 1]);
	assert.equal(typeof polygon[0][0], 'number');
	assert.equal(typeof polygon[0][1], 'number');
});

test('getActorGeofenceAlert returns persistent alert data inside radius', () => {
	const alert = getActorGeofenceAlert(actor, [120, 205, 0]);

	assert.equal(alert?.actor.actor_id, 42);
	assert.equal(alert?.distance, 21);
});

test('getActorGeofenceAlert returns null outside radius', () => {
	const alert = getActorGeofenceAlert(actor, [200, 200, 0]);

	assert.equal(alert, null);
});
```

- [ ] **Step 4: Run actor geofence rule tests and confirm they fail**

Run:

```bash
cd apps/web
node --test --experimental-strip-types scripts/actorGeofenceRules.test.mjs
```

Expected: fails because `actorGeofenceRules.ts` does not exist.

- [ ] **Step 5: Implement actor geofence pure rules**

Create `apps/web/src/lib/actorGeofenceRules.ts`:

```ts
import type { ActorGeofenceAlert, DynamicActor } from './types';
import { carlaToGps } from './geo';

export const DYNAMIC_GEOFENCE_COLOR = '#ef4444';

export function buildActorGeofencePolygon(
	actor: DynamicActor,
	originLat: number,
	originLon: number,
	segments = 48
): [number, number][] {
	const radius = Math.max(1, actor.geofence_radius);
	const points: [number, number][] = [];

	for (let i = 0; i <= segments; i += 1) {
		const angle = (i / segments) * Math.PI * 2;
		const x = actor.pos[0] + Math.cos(angle) * radius;
		const y = actor.pos[1] + Math.sin(angle) * radius;
		points.push(carlaToGps(x, y, originLat, originLon));
	}

	return points;
}

export function getActorGeofenceAlert(
	actor: DynamicActor,
	egoPos: [number, number, number]
): ActorGeofenceAlert | null {
	const dx = actor.pos[0] - egoPos[0];
	const dy = actor.pos[1] - egoPos[1];
	const distance = Math.sqrt(dx * dx + dy * dy);

	if (distance > actor.geofence_radius) {
		return null;
	}

	return {
		actor,
		distance: Math.round(distance),
	};
}
```

- [ ] **Step 6: Implement actor geofence proximity store**

Create `apps/web/src/lib/stores/actorGeofences.ts`:

```ts
import { writable } from 'svelte/store';
import type { ActorGeofenceAlert, DynamicActor } from '$lib/types';
import { getActorGeofenceAlert } from '$lib/actorGeofenceRules';

export const activeActorGeofenceAlerts = writable<ActorGeofenceAlert[]>([]);

export function checkActorGeofenceProximity(
	egoPos: [number, number, number],
	actors: DynamicActor[]
): void {
	const active = actors
		.map((actor) => getActorGeofenceAlert(actor, egoPos))
		.filter((alert): alert is ActorGeofenceAlert => alert !== null);

	activeActorGeofenceAlerts.set(active);
}

export function resetActorGeofenceProximity(): void {
	activeActorGeofenceAlerts.set([]);
}
```

- [ ] **Step 7: Run rule tests**

Run:

```bash
cd apps/web
node --test --experimental-strip-types scripts/actorGeofenceRules.test.mjs scripts/zoneRules.test.mjs
```

Expected: all tests pass.

- [ ] **Step 8: Commit geofence rules/store**

```bash
git add apps/web/src/lib/geo.ts apps/web/src/lib/actorGeofenceRules.ts apps/web/src/lib/stores/actorGeofences.ts apps/web/src/lib/stores/v2xZones.ts apps/web/scripts/actorGeofenceRules.test.mjs
git commit -m "feat: add moving actor geofence rules"
```

---

### Task 5: Render Moving Geofences And Alerts

**Files:**
- Modify: `apps/web/src/lib/components/DriveMiniMap.svelte`
- Modify: `apps/web/src/lib/components/V2xToast.svelte`

- [ ] **Step 1: Import dynamic actor stores and rules into the mini-map**

In `DriveMiniMap.svelte`, change the drive socket import to:

```ts
import { telemetry, dynamicActors } from '$lib/stores/driveSocket';
```

Add:

```ts
import { buildActorGeofencePolygon, DYNAMIC_GEOFENCE_COLOR } from '$lib/actorGeofenceRules';
import type { DynamicActor, V2xZone } from '$lib/types';
```

Then remove `V2xZone` from the existing type-only import to avoid a duplicate import.

- [ ] **Step 2: Add a moving geofence source and layers**

Inside `map.on('load', ...)`, after the static `v2x-zones` layers and before `nearby-actors`, add:

```ts
map.addSource('dynamic-actor-geofences', {
	type: 'geojson',
	data: buildDynamicActorGeofenceGeoJSON($dynamicActors),
});
map.addLayer({
	id: 'dynamic-actor-geofences-fill',
	type: 'fill',
	source: 'dynamic-actor-geofences',
	paint: {
		'fill-color': ['get', 'color'],
		'fill-opacity': 0.18,
	},
});
map.addLayer({
	id: 'dynamic-actor-geofences-outline',
	type: 'line',
	source: 'dynamic-actor-geofences',
	paint: {
		'line-color': ['get', 'color'],
		'line-width': 2,
		'line-opacity': 0.85,
	},
});
```

- [ ] **Step 3: Add the moving geofence GeoJSON builder**

Below `buildZonesGeoJSON`, add:

```ts
function buildDynamicActorGeofenceGeoJSON(actors: DynamicActor[]): GeoJSON.FeatureCollection {
	return {
		type: 'FeatureCollection',
		features: actors.map((actor) => ({
			type: 'Feature' as const,
			geometry: {
				type: 'Polygon' as const,
				coordinates: [buildActorGeofencePolygon(actor, originLat, originLon)],
			},
			properties: {
				id: actor.actor_id,
				name: actor.name,
				color: DYNAMIC_GEOFENCE_COLOR,
				radius: actor.geofence_radius,
			},
		})),
	};
}
```

- [ ] **Step 4: Color dynamic actors differently from generic traffic**

In the `nearby-actors-layer` paint expression, replace the current `circle-color` expression with:

```ts
'circle-color': [
	'match', ['get', 'type'],
	'dynamic', '#ef4444',
	'traffic', '#f59e0b',
	'#94a3b8',
],
```

- [ ] **Step 5: Update moving geofences on telemetry**

In the telemetry `$effect`, after updating nearby actors, add:

```ts
const dynamicGeofenceSource = map.getSource('dynamic-actor-geofences') as maplibregl.GeoJSONSource | undefined;
if (dynamicGeofenceSource) {
	dynamicGeofenceSource.setData(buildDynamicActorGeofenceGeoJSON($dynamicActors));
}
```

Also add a separate `$effect` after the static zone overlay effect:

```ts
$effect(() => {
	const actors = $dynamicActors;
	if (!map || !mapReady) return;
	const source = map.getSource('dynamic-actor-geofences') as maplibregl.GeoJSONSource | undefined;
	if (source) {
		source.setData(buildDynamicActorGeofenceGeoJSON(actors));
	}
});
```

- [ ] **Step 6: Update the map badge**

Replace the existing zone badge condition and text with:

```svelte
{#if drawableZoneCount + $dynamicActors.length > 0}
	<div class="absolute bottom-1 right-1 rounded bg-gray-900/80 px-1.5 py-0.5 text-[9px] font-medium text-gray-400">
		{drawableZoneCount} static / {$dynamicActors.length} moving
	</div>
{/if}
```

- [ ] **Step 7: Import dynamic actor alerts into the toast**

In `V2xToast.svelte`, add:

```ts
import { activeActorGeofenceAlerts } from '$lib/stores/actorGeofences';
```

- [ ] **Step 8: Add dynamic geofence toast rendering**

Change the top-level condition to:

```svelte
{#if $v2xAlerts.length > 0 || $activeZoneAlerts.length > 0 || $zoneEntryNotifications.length > 0 || $activeActorGeofenceAlerts.length > 0}
```

After the persistent static geofence alert block, add:

```svelte
<!-- Persistent moving actor geofence alerts -->
{#each $activeActorGeofenceAlerts as entry (entry.actor.actor_id)}
	<div class="rounded-lg border-l-4 border-red-400 bg-red-600/90 px-3 py-2 shadow-lg backdrop-blur-sm animate-slide-in">
		<div class="flex items-start gap-2">
			<span class="text-lg leading-none">🚫</span>
			<div class="flex-1 min-w-0">
				<p class="text-[10px] font-bold text-white/70 uppercase tracking-wide">MOVING GEOFENCE</p>
				<p class="text-sm font-medium text-white leading-tight">{entry.actor.message || entry.actor.name}</p>
				<p class="text-[10px] text-white/50 mt-0.5">{entry.distance}m from actor center</p>
			</div>
		</div>
	</div>
{/each}
```

- [ ] **Step 9: Run frontend build**

Run:

```bash
cd apps/web
npm run build
```

Expected: build succeeds.

- [ ] **Step 10: Commit rendering changes**

```bash
git add apps/web/src/lib/components/DriveMiniMap.svelte apps/web/src/lib/components/V2xToast.svelte
git commit -m "feat: render moving actor geofences"
```

---

### Task 6: Add Actor Panel Autopilot Mode

**Files:**
- Modify: `apps/web/src/routes/drive/+page.svelte`

- [ ] **Step 1: Import dynamic actor actions and stores**

In the import from `$lib/stores/driveSocket`, add:

```ts
spawnDynamicActor,
despawnDynamicActor,
dynamicActors,
```

Add:

```ts
import { checkActorGeofenceProximity, resetActorGeofenceProximity } from '$lib/stores/actorGeofences';
import type { SpawnableObject } from '$lib/types';
```

- [ ] **Step 2: Add Add Actor panel state**

Near the existing object placer state, add:

```ts
let actorSpawnMode = $state<'static' | 'autopilot'>('static');
let geofenceRadiusM = $state(35);
let dynamicActorMessage = $state('Moving emergency vehicle geofence active');
let activeDynamicActors = $derived($dynamicActors);
```

- [ ] **Step 3: Add spawn helpers**

Near `handleNewScenario`, add:

```ts
function clampGeofenceRadius(value: number): number {
	return Math.max(5, Math.min(250, Number.isFinite(value) ? value : 35));
}

function spawnFromActorPanel(obj: SpawnableObject): void {
	if (actorSpawnMode === 'static') {
		spawnObject(obj.id);
		return;
	}

	if (obj.category !== 'vehicle') {
		lastError.set('Autopilot actors must be vehicles');
		return;
	}

	const message = dynamicActorMessage.trim() || `${obj.name} moving geofence active`;
	spawnDynamicActor(obj.id, clampGeofenceRadius(geofenceRadiusM), message);
}
```

- [ ] **Step 4: Check moving actor geofence proximity on telemetry**

In the existing V2X zone proximity `$effect`, after `checkZoneProximity(...)`, add:

```ts
checkActorGeofenceProximity(t.pos, $dynamicActors);
```

In `handleEndSession`, after `resetZoneProximity();`, add:

```ts
resetActorGeofenceProximity();
```

In `cleanupSession`, add:

```ts
resetActorGeofenceProximity();
```

- [ ] **Step 5: Add mode controls to the Object Placer panel**

In the Object Placer panel, after the header div that contains the search/Undo/close controls and before the scrollable list, add:

```svelte
<div class="border-b border-gray-700 p-2 space-y-2">
	<div class="grid grid-cols-2 gap-1 rounded bg-gray-800 p-0.5">
		<button
			class="rounded px-2 py-1 text-[11px] font-medium {actorSpawnMode === 'static' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}"
			onclick={() => { actorSpawnMode = 'static'; }}
		>
			Static
		</button>
		<button
			class="rounded px-2 py-1 text-[11px] font-medium {actorSpawnMode === 'autopilot' ? 'bg-red-600 text-white' : 'text-gray-400 hover:text-white'}"
			onclick={() => { actorSpawnMode = 'autopilot'; }}
		>
			Autopilot
		</button>
	</div>

	{#if actorSpawnMode === 'autopilot'}
		<label class="block text-[10px] font-medium uppercase tracking-wide text-gray-500">
			Radius
			<input
				type="number"
				min="5"
				max="250"
				step="5"
				bind:value={geofenceRadiusM}
				class="mt-1 w-full rounded border border-gray-600 bg-gray-800 px-2 py-1 text-xs text-white focus:border-red-500 focus:outline-none"
			/>
		</label>
		<label class="block text-[10px] font-medium uppercase tracking-wide text-gray-500">
			Message
			<input
				type="text"
				bind:value={dynamicActorMessage}
				class="mt-1 w-full rounded border border-gray-600 bg-gray-800 px-2 py-1 text-xs text-white placeholder-gray-500 focus:border-red-500 focus:outline-none"
			/>
		</label>
	{/if}
</div>
```

- [ ] **Step 6: Route object buttons through the new helper**

Replace the object list button click handler:

```svelte
onclick={() => { spawnObject(obj.id); }}
```

with:

```svelte
onclick={() => { spawnFromActorPanel(obj); }}
```

Add disabled styling for props in autopilot mode by replacing the button class with:

```svelte
class="w-full px-3 py-1.5 text-left text-xs transition-colors flex items-center gap-2 {actorSpawnMode === 'autopilot' && obj.category !== 'vehicle' ? 'opacity-40 cursor-not-allowed' : 'hover:bg-gray-800'}"
```

Add the `disabled` attribute:

```svelte
disabled={actorSpawnMode === 'autopilot' && obj.category !== 'vehicle'}
```

- [ ] **Step 7: Show active dynamic actors in the panel**

Above the save scenario footer, add:

```svelte
{#if activeDynamicActors.length > 0}
	<div class="border-t border-gray-700 p-2 space-y-1">
		<p class="text-[10px] font-medium uppercase tracking-wide text-gray-500">Moving actors</p>
		{#each activeDynamicActors as actor (actor.actor_id)}
			<div class="flex items-center gap-2 text-xs">
				<span class="h-1.5 w-1.5 rounded-full bg-red-400"></span>
				<span class="min-w-0 flex-1 truncate text-gray-200">{actor.name}</span>
				<span class="text-[10px] text-gray-500">{actor.geofence_radius}m</span>
				<button
					class="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-300 hover:bg-gray-700 hover:text-white"
					onclick={() => despawnDynamicActor(actor.actor_id)}
				>
					Remove
				</button>
			</div>
		{/each}
	</div>
{/if}
```

- [ ] **Step 8: Run frontend build**

Run:

```bash
cd apps/web
npm run build
```

Expected: build succeeds and the Add Actor panel compiles.

- [ ] **Step 9: Commit Add Actor panel changes**

```bash
git add apps/web/src/routes/drive/+page.svelte
git commit -m "feat: add autopilot geofence mode to actor panel"
```

---

### Task 7: End-To-End Verification On Local Frontend And Path PC Bridge

**Files:**
- No new files.

- [ ] **Step 1: Run all focused automated checks**

Run:

```bash
cd apps/bridge
pytest tests/test_drive_server.py -v
```

Expected: drive server tests pass.

Run:

```bash
cd apps/web
node --test --experimental-strip-types scripts/actorGeofenceRules.test.mjs scripts/zoneRules.test.mjs
npm run build
```

Expected: Node tests and build pass.

- [ ] **Step 2: Start or confirm local web dev server**

Run:

```bash
cd apps/web
npm run dev -- --host 0.0.0.0
```

Expected: Vite serves `/drive` on `http://localhost:5173/drive`.

- [ ] **Step 3: Deploy backend code to the Path PC checkout**

After the branch containing this work is available to the Path PC checkout, run:

```bash
sshpass -p 'path123' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null path@100.72.252.40 \
  "cd /home/path/V2XCarla/v2x-backend && git pull --ff-only"
```

Expected: Path PC checkout updates to the commit with `spawn_dynamic_actor`.

- [ ] **Step 4: Restart the Path PC bridge without changing the CARLA container**

Run:

```bash
sshpass -p 'path123' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null path@100.72.252.40 \
  "pkill -f 'digital_twin_bridge.drive_main' || true; cd /home/path/V2XCarla/v2x-backend && nohup ./scripts/launch-drive.sh > /tmp/launch-drive.log 2>&1 &"
```

Expected: the bridge listens on `0.0.0.0:8765`; the existing CARLA container remains the active simulator.

- [ ] **Step 5: Verify the bridge is listening**

Run:

```bash
sshpass -p 'path123' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null path@100.72.252.40 \
  "ss -ltnp | egrep ':(2000|8765)\\b' || true"
```

Expected: CARLA listens on `2000` and the drive bridge listens on `8765`.

- [ ] **Step 6: Verify the WebSocket message path**

Use the configured Cloudflare or Tailscale WebSocket URL from `apps/web/src/lib/constants.ts` and send:

```json
{"type":"list_objects"}
```

Expected: the response has `"type":"object_list"` and includes vehicle objects. A firetruck appears when CARLA exposes `vehicle.carlamotors.firetruck`; otherwise choose another vehicle blueprint from the same list.

- [ ] **Step 7: Manual drive UI acceptance test**

In `http://localhost:5173/drive`:

1. Start a driving session.
2. Open Add Actor.
3. Switch mode to `Autopilot`.
4. Search `fire` and select the firetruck when available, or select a different vehicle.
5. Set radius to `45`.
6. Spawn the actor.
7. Confirm the actor moves under Traffic Manager control.
8. Confirm the mini-map shows a red moving geofence circle around the actor.
9. Drive the ego vehicle into the circle and confirm the `MOVING GEOFENCE` toast stays visible.
10. Drive the ego vehicle out of the circle and confirm the toast disappears.
11. Click `Remove` for the moving actor and confirm the actor/geofence disappears.

- [ ] **Step 8: Commit verification adjustments**

If the acceptance test reveals a code fix, commit the fix with:

```bash
git add apps/bridge apps/web
git commit -m "fix: stabilize dynamic actor geofence flow"
```

If no code changes are needed, do not create an empty commit.

---

## Rollout Notes

- This feature changes both frontend and bridge backend. The local web UI can render the new controls immediately, but dynamic actor spawning will fail until the Path PC bridge runs the backend code containing `spawn_dynamic_actor`.
- Do not switch CARLA containers as part of this feature. Restart only the drive bridge after backend code is updated.
- The quick Cloudflare tunnel continues to forward WebSocket traffic to `localhost:8765`; it does not need to know about dynamic actors because the message contract stays JSON over the existing WebSocket.
- Scenario save/load should keep saving static objects and static V2X zones only. Moving actor geofences are live session controls, not scenario geometry.

## Self-Review

- Spec coverage: the plan adds Add Actor panel controls, custom radius, a firefighter/firetruck-capable vehicle path, Traffic Manager autopilot, moving map geofence rendering, persistent warnings, cleanup, and Path PC bridge verification.
- Placeholder scan: the plan uses exact paths, method names, message names, code snippets, commands, and expected results.
- Type consistency: backend uses `geofence_radius`; frontend `DynamicActor` uses `geofence_radius`; WebSocket actions send `geofence_radius`; telemetry returns `dynamic_actors`.
