"""
Local conftest for dashboard tests.

Extends the shared mocks (in tests/conftest.py) with the bits the
dashboard tests need — without modifying the shared infrastructure,
so these tests stay easy to delete later.

Specifically:
- MockWorld.spawn_actor / try_spawn_actor accept the `attachment_type`
  kwarg used by real CARLA when attaching child actors.
- MockActor gains stop() and listen() no-ops (sensor lifecycle methods).

All patching is reverted after each test.
"""

import pytest

from tests.conftest import MockWorld, MockActor


@pytest.fixture(autouse=True)
def _extend_carla_mocks_for_camera_sensor():
    original_spawn = MockWorld.spawn_actor
    original_try_spawn = MockWorld.try_spawn_actor
    had_stop = hasattr(MockActor, "stop")
    had_listen = hasattr(MockActor, "listen")

    def patched_spawn(self, blueprint, transform, attach_to=None, attachment_type=None):
        return original_spawn(self, blueprint, transform, attach_to=attach_to)

    def patched_try_spawn(self, blueprint, transform, attach_to=None, attachment_type=None):
        return original_try_spawn(self, blueprint, transform, attach_to=attach_to)

    MockWorld.spawn_actor = patched_spawn
    MockWorld.try_spawn_actor = patched_try_spawn

    if not had_stop:
        MockActor.stop = lambda self: None
    if not had_listen:
        MockActor.listen = lambda self, callback: None

    yield

    MockWorld.spawn_actor = original_spawn
    MockWorld.try_spawn_actor = original_try_spawn
    if not had_stop:
        delattr(MockActor, "stop")
    if not had_listen:
        delattr(MockActor, "listen")
