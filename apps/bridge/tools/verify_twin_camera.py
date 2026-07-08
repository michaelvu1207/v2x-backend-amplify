#!/usr/bin/env python3
"""
Twin camera alignment harness.

Renders each twin camera in CARLA and cross-checks the pose conversion
against the perception calibration ground truth:

1. Saves a JPEG render per channel (blend these 50/50 with a real frame
   grab to eyeball road alignment).
2. For every calibration point (u,v -> True_X, True_Z from
   apps/perception/calibration/chN_calibration_errors.csv), converts the
   true ground point through the SAME chain the twin uses
   (local XZ -> GPS -> CARLA world) and reprojects it through the twin
   camera. Reports the pixel delta vs. the original (u,v) — large,
   systematic deltas mean the heading->yaw convention is wrong.

Run on the Path PC (needs the carla package + a running simulator):

    python tools/verify_twin_camera.py --host 127.0.0.1 --port 2000 \
        --out /tmp/twin-verify

Safe to run alongside the bridge: it only spawns temporary cameras and
destroys them on exit. Avoid running during an active drive session.
"""

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from digital_twin_bridge.geo_utils import gps_to_carla
from digital_twin_bridge.twin_camera_rig import (
    compute_twin_camera_transform,
    horizontal_fov_deg,
    load_cameras_config,
)

CALIBRATION_DIR = Path(__file__).resolve().parents[3] / "apps" / "perception" / "calibration"


def xz_to_gps(x, z, origin_lat, origin_lon, heading_deg):
    """Perception's local-XZ -> GPS conversion (mirror of xy_to_gps)."""
    heading = math.radians(heading_deg)
    easting = z * math.sin(heading) + x * math.cos(heading)
    northing = z * math.cos(heading) - x * math.sin(heading)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(origin_lat))
    return origin_lat + northing / meters_per_deg_lat, origin_lon + easting / meters_per_deg_lon


def project_world_point(carla_transform, world_location, fov_deg, width, height):
    """Project a CARLA world point through a pinhole camera at `carla_transform`.

    Returns (u, v, depth) or None when the point is behind the camera.
    """
    import numpy as np

    # World -> camera (UE axes): rows of the inverse transform matrix
    inv = np.array(carla_transform.get_inverse_matrix())
    p_world = np.array([world_location.x, world_location.y, world_location.z, 1.0])
    p_cam_ue = inv @ p_world  # UE camera frame: x forward, y right, z up

    # UE -> standard camera frame: x right, y down, z forward
    x_cam, y_cam, z_cam = p_cam_ue[1], -p_cam_ue[2], p_cam_ue[0]
    if z_cam <= 0.1:
        return None

    focal = (width / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
    u = width / 2.0 + focal * (x_cam / z_cam)
    v = height / 2.0 + focal * (y_cam / z_cam)
    return u, v, z_cam


def load_calibration_points(camera_id):
    path = CALIBRATION_DIR / f"{camera_id}_calibration_errors.csv"
    if not path.exists():
        return []
    points = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                points.append({
                    "u": float(row["u_pixel"]),
                    "v": float(row["v_pixel"]),
                    "x": float(row["True_X_m"]),
                    "z": float(row["True_Z_m"]),
                })
            except (KeyError, ValueError):
                continue
    return points


def wait_for_frame(world, queue, timeout=5.0):
    """Wait for one frame; tick manually only if nothing else is ticking."""
    deadline = time.time() + timeout
    settings = world.get_settings()
    while time.time() < deadline:
        if not queue:
            if settings.synchronous_mode:
                try:
                    world.tick(2.0)
                except RuntimeError:
                    pass  # another process (the bridge) owns the tick
            time.sleep(0.1)
            continue
        return queue.pop()
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--out", default="/tmp/twin-verify")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--cameras-json", default=None)
    args = parser.parse_args()

    import carla

    config = load_cameras_config(args.cameras_json)
    if config is None:
        print("ERROR: cameras config not found", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)

    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)
    world = client.get_world()
    carla_map = world.get_map()
    print(f"Connected. Map: {carla_map.name}")

    site = config["site"]
    bp_lib = world.get_blueprint_library()

    exit_code = 0
    for camera in config["cameras"]:
        camera_id = camera["id"]
        fov = horizontal_fov_deg(camera["intrinsics"])
        transform = compute_twin_camera_transform(carla_map, site, camera)
        print(f"\n=== {camera_id} ===")
        print(
            f"pose: loc=({transform.location.x:.2f}, {transform.location.y:.2f}, "
            f"{transform.location.z:.2f}) yaw={transform.rotation.yaw:.2f} "
            f"pitch={transform.rotation.pitch:.2f} fov={fov:.2f}"
        )

        # 1. Render a frame
        camera_bp = bp_lib.find("sensor.camera.rgb")
        camera_bp.set_attribute("image_size_x", str(args.width))
        camera_bp.set_attribute("image_size_y", str(args.height))
        camera_bp.set_attribute("fov", f"{fov:.2f}")
        frames = []
        actor = world.spawn_actor(camera_bp, transform)
        actor.listen(frames.append)
        image = wait_for_frame(world, frames)
        actor.stop()
        actor.destroy()
        if image is not None:
            out_path = os.path.join(args.out, f"twin_{camera_id}.jpg")
            from digital_twin_bridge.frame_encoder import encode_jpeg

            with open(out_path, "wb") as f:
                f.write(encode_jpeg(image, quality=90))
            print(f"render: {out_path}")
        else:
            print("render: NO FRAME (is the simulator ticking?)")
            exit_code = 1

        # 2. Reproject calibration ground truth through the twin camera
        points = load_calibration_points(camera_id)
        if not points:
            print("calibration: no CSV points found, skipping reprojection check")
            continue

        # The calibration CSV pixels are in the REAL camera resolution.
        real_w = camera["intrinsics"]["width"]
        real_h = camera["intrinsics"]["height"]
        scale_u = args.width / real_w
        scale_v = args.height / real_h

        errors = []
        for point in points:
            lat, lon = xz_to_gps(
                point["x"], point["z"], site["lat"], site["lon"], camera["heading_deg"]
            )
            world_loc = gps_to_carla(carla_map, lat, lon)
            projected = project_world_point(transform, world_loc, fov, args.width, args.height)
            if projected is None:
                print(f"  point ({point['u']:.0f},{point['v']:.0f}): behind camera!")
                errors.append(float("inf"))
                continue
            pu, pv, depth = projected
            du = pu - point["u"] * scale_u
            dv = pv - point["v"] * scale_v
            err = math.hypot(du, dv)
            errors.append(err)
            print(
                f"  point ({point['u']:.0f},{point['v']:.0f}) -> "
                f"({pu:.0f},{pv:.0f}) delta=({du:+.0f},{dv:+.0f})px "
                f"err={err:.0f}px depth={depth:.1f}m"
            )

        finite = [e for e in errors if math.isfinite(e)]
        if finite:
            mean_err = sum(finite) / len(finite)
            print(f"mean reprojection error: {mean_err:.0f}px over {len(finite)} points")
            # Rough gate: ground-plane + calibration noise justifies slack, but a
            # wrong yaw convention lands hundreds of px off or behind the camera.
            if mean_err > 200:
                print("WARNING: large systematic error — check heading->yaw convention")
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
