"""
Spawns and destroys CARLA actors for V2X-detected objects.

Mirrors the logic from ``v2x_map_streamlit.py:spawn_v2x_detections()`` —
each V2X detection gets a visible prop (traffic cone, warning sign, etc.)
placed at its GPS position in the CARLA world so the cameras have
something to photograph.
"""

import logging
from typing import Optional

import carla

from digital_twin_bridge.object_registry import ObjectRegistry, TrackedObject
from digital_twin_bridge.geo_utils import gps_to_carla

logger = logging.getLogger(__name__)

# V2X object type → CARLA blueprint mapping (matches v2x_map_streamlit.py)
V2X_TYPE_TO_BLUEPRINT = {
    "traffic_cone": "static.prop.trafficcone01",
}
V2X_FALLBACK_BLUEPRINT = "static.prop.trafficwarning"


class PropSpawner:
    """Manages CARLA actor lifecycle for V2X-detected objects.

    Call :meth:`sync` after each V2X poll to spawn actors for new objects
    and update locations for moved objects.  Call :meth:`destroy_actor`
    or :meth:`destroy_all` for cleanup.
    """

    def __init__(self, world: carla.World, carla_map: carla.Map) -> None:
        self._world = world
        self._carla_map = carla_map
        self._bp_lib = world.get_blueprint_library()

    def _resolve_blueprint(self, object_type: str) -> Optional[carla.ActorBlueprint]:
        """Find the CARLA blueprint for a V2X object type."""
        bp_name = V2X_TYPE_TO_BLUEPRINT.get(object_type, V2X_FALLBACK_BLUEPRINT)
        bp_results = self._bp_lib.filter(bp_name)
        if len(bp_results) == 0:
            bp_results = self._bp_lib.filter(V2X_FALLBACK_BLUEPRINT)
        if len(bp_results) == 0:
            return None
        return bp_results[0]

    def spawn_for_object(self, obj: TrackedObject) -> Optional[int]:
        """Spawn a CARLA actor for a tracked object.

        Sets ``obj.carla_actor_id`` and ``obj.carla_location`` on success.

        Returns:
            The CARLA actor ID, or ``None`` if spawning failed.
        """
        bp = self._resolve_blueprint(obj.object_type)
        if bp is None:
            logger.warning(
                "No blueprint found for object type '%s' (object %s).",
                obj.object_type,
                obj.object_id,
            )
            return None

        location = gps_to_carla(self._carla_map, obj.lat, obj.lon)

        # Raycast down from above to find exact mesh surface
        probe = carla.Location(x=location.x, y=location.y, z=location.z + 5.0)
        ground = self._world.ground_projection(probe, search_distance=20.0)
        if ground is not None:
            location = carla.Location(x=location.x, y=location.y, z=ground.location.z + 0.02)

        transform = carla.Transform(location, carla.Rotation())
        actor = self._world.try_spawn_actor(bp, transform)
        if actor is not None:
            obj.carla_actor_id = actor.id
            obj.carla_location = location  # Use computed location (actor.get_location() is stale before tick)
            logger.info(
                "Spawned %s for object %s (actor_id=%d) at (%.1f, %.1f, %.1f).",
                bp.id,
                obj.object_id,
                actor.id,
                location.x,
                location.y,
                location.z,
            )
            return actor.id
        else:
            logger.warning(
                "Failed to spawn actor for object %s at (%.1f, %.1f, %.1f).",
                obj.object_id,
                location.x,
                location.y,
                location.z,
            )
            return None

    def sync(self, registry: ObjectRegistry) -> int:
        """Spawn actors for any tracked objects that don't have one yet.

        Returns:
            The number of actors newly spawned.
        """
        spawned = 0
        for obj in registry.get_all():
            if obj.carla_actor_id is not None:
                # Already has an actor — refresh its location from CARLA
                actor = self._world.get_actor(obj.carla_actor_id)
                if actor is not None:
                    obj.carla_location = actor.get_location()
                else:
                    # Actor was destroyed externally; clear it so we re-spawn
                    logger.warning(
                        "Actor %d for object %s no longer exists; will re-spawn.",
                        obj.carla_actor_id,
                        obj.object_id,
                    )
                    obj.carla_actor_id = None

            if obj.carla_actor_id is None:
                if self.spawn_for_object(obj) is not None:
                    spawned += 1

        return spawned

    def destroy_actor(self, obj: TrackedObject) -> bool:
        """Destroy the CARLA actor associated with a tracked object."""
        if obj.carla_actor_id is None:
            return False
        actor = self._world.get_actor(obj.carla_actor_id)
        if actor is not None:
            actor.destroy()
            logger.debug(
                "Destroyed actor %d for object %s.",
                obj.carla_actor_id,
                obj.object_id,
            )
        obj.carla_actor_id = None
        return True

    def destroy_stale(self, stale_objects: list[TrackedObject]) -> int:
        """Destroy CARLA actors for a list of stale objects."""
        destroyed = 0
        for obj in stale_objects:
            if self.destroy_actor(obj):
                destroyed += 1
        if destroyed:
            logger.info("Destroyed %d stale CARLA actors.", destroyed)
        return destroyed

    def destroy_all(self, registry: ObjectRegistry) -> int:
        """Destroy all CARLA actors for currently tracked objects."""
        destroyed = 0
        for obj in registry.get_all():
            if self.destroy_actor(obj):
                destroyed += 1
        logger.info("Destroyed %d CARLA actors (full cleanup).", destroyed)
        return destroyed
