"""Tests for CARLA connection startup behavior."""

import pytest

from digital_twin_bridge.config import Config
from digital_twin_bridge.carla_connection import CarlaConnection
import digital_twin_bridge.carla_connection as carla_connection_module
from tests.conftest import MockClient, MockMap, MockWorld


@pytest.mark.unit
class TestCarlaConnectionMapSelection:
    def test_connect_loads_configured_map_when_available(self, monkeypatch):
        world = MockWorld()
        world._map = MockMap("Richmond_Field_Station_Richmond_CA")
        client = MockClient(world)
        client.available_maps = [
            "Richmond_Field_Station_Richmond_CA",
            "/Game/Carla/Maps/San_Ramon_P1_Roads",
        ]
        monkeypatch.setattr(
            carla_connection_module.carla,
            "Client",
            lambda host, port: client,
        )

        conn = CarlaConnection(Config(CARLA_MAP="San_Ramon"))
        conn.connect()

        assert client.loaded_maps == ["/Game/Carla/Maps/San_Ramon_P1_Roads"]
        assert conn.carla_map.name == "/Game/Carla/Maps/San_Ramon_P1_Roads"
        assert conn.world.get_settings().synchronous_mode is True

        conn.disconnect()

    def test_connect_keeps_current_map_when_requested_map_unavailable(self, monkeypatch):
        world = MockWorld()
        world._map = MockMap("Richmond_Field_Station_Richmond_CA")
        client = MockClient(world)
        client.available_maps = ["Richmond_Field_Station_Richmond_CA"]
        monkeypatch.setattr(
            carla_connection_module.carla,
            "Client",
            lambda host, port: client,
        )

        conn = CarlaConnection(Config(CARLA_MAP="San_Ramon"))
        conn.connect()

        assert client.loaded_maps == []
        assert conn.carla_map.name == "Richmond_Field_Station_Richmond_CA"
        assert conn.world.get_settings().synchronous_mode is True

        conn.disconnect()

    def test_switch_drive_map_accepts_only_public_map_choices(self, monkeypatch):
        world = MockWorld()
        world._map = MockMap("Richmond_Field_Station_Richmond_CA")
        client = MockClient(world)
        client.available_maps = [
            "/Game/Carla/Maps/Richmond_Field_Station_Richmond_CA",
            "/Game/Carla/Maps/San_Ramon_P1_Roads",
        ]
        monkeypatch.setattr(
            carla_connection_module.carla,
            "Client",
            lambda host, port: client,
        )

        conn = CarlaConnection(Config(CARLA_MAP="Richmond_Field_Station_Richmond_CA"))
        conn.connect()

        result = conn.switch_drive_map("san_ramon")

        assert result["changed"] is True
        assert result["current_map"] == "san_ramon"
        assert client.loaded_maps[-1] == "/Game/Carla/Maps/San_Ramon_P1_Roads"
        assert conn.world.get_settings().synchronous_mode is True
        with pytest.raises(ValueError, match="Unsupported drive map"):
            conn.switch_drive_map("Town10HD")

        conn.disconnect()
