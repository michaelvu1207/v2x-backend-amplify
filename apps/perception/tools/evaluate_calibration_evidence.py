#!/usr/bin/env python3
"""Fail-closed evaluator for independently held-out camera calibration evidence.

The tool never fits or writes camera configuration.  It validates immutable source
frames and a candidate projection report, rejects feature/group split leakage, and
computes fixed pixel, metric, covariance-coverage, and cross-camera gates.  Locked
locked-test results are excluded unless ``--reveal-locked-test`` is explicit; the
output then carries a durable burn record keyed by both input hashes.  The locked
manifest itself must be access-controlled separately from this evaluator.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import itertools
import json
import math
import os
import random
import statistics
import struct
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any


SCHEMA_VERSION = 1
REFERENCE_WIDTH = 2560.0
LOCKED_SPLIT = "locked_test"
ALLOWED_SPLITS = {"train", "validation", LOCKED_SPLIT}
ALLOWED_RANGES = {"near", "mid", "far"}
REQUIRED_CATEGORIES = {"road_edge", "lane_marking", "stable_landmark"}
REQUIRED_REGIONS = {"left", "center", "right", "top", "bottom"}
MIN_LOCKED_POINTS = 30
MIN_LOCKED_GROUPS = 15
MIN_LOCKED_CROSS_CAMERA_PAIRS = 10
MIN_VALIDATION_POINTS = 15
MIN_VALIDATION_GROUPS = 10
CHI2_2D_95 = 5.991464547107979

# These are ceilings, not user-tunable defaults.  A manifest may tighten them but
# cannot make them easier.  Pixel values scale linearly with source-frame width.
MAX_GATES = {
    "pixel_rmse_px": 3.0,
    "pixel_median_px": 2.0,
    "pixel_p95_px": 6.0,
    "pixel_max_px": 12.0,
    "region_p95_px": 8.0,
    "world_near_p95_m": 0.5,
    "world_mid_p95_m": 1.0,
    "world_far_p95_m": 2.0,
    "cross_camera_world_max_m": 1.0,
    "covariance_95_coverage_min": 0.90,
    "covariance_semi_major_95_max_m": 2.0,
    "pixel_uncertainty_95_coverage_min": 0.90,
    "baseline_improvement_confidence_min": 0.95,
}
MODEL_GATES = {
    "normalized_jacobian_condition_max": 1.0e8,
    "max_abs_parameter_correlation": 0.95,
    "minimum_information_eigenvalue": 1.0e-8,
    "prior_sensitivity_max_sigma": 2.0,
    "observations_per_parameter_min": 2.0,
}


class EvidenceError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must contain a JSON object")
    return value, _sha256_bytes(raw)


def _image_dimensions(raw: bytes, label: str) -> tuple[int, int]:
    """Read PNG/JPEG dimensions from the exact bytes that were hash-checked."""
    with io.BytesIO(raw) as stream:
        prefix = stream.read(24)
        if prefix.startswith(b"\x89PNG\r\n\x1a\n") and prefix[12:16] == b"IHDR":
            width, height = struct.unpack(">II", prefix[16:24])
            if width and height:
                return width, height
        if prefix[:2] != b"\xff\xd8":
            raise EvidenceError(f"unsupported or invalid image format: {label}")
        stream.seek(2)
        while True:
            byte = stream.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            while byte == b"\xff":
                byte = stream.read(1)
            marker = byte[0]
            if marker in {0xD8, 0xD9}:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                body = stream.read(length - 2)
                if len(body) >= 5:
                    height, width = struct.unpack(">HH", body[1:5])
                    if width and height:
                        return width, height
                break
            stream.seek(length - 2, 1)
    raise EvidenceError(f"could not decode image dimensions: {label}")


def _parse_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError(f"{label} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{label} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise EvidenceError(f"{label} must be UTC")
    return value


def _load_baseline(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    descriptor = manifest.get("baseline")
    if not isinstance(descriptor, dict) or set(descriptor) != {"path", "sha256"}:
        raise EvidenceError("manifest baseline must contain only path and sha256")
    path_value, expected_hash = descriptor["path"], descriptor["sha256"]
    if not isinstance(path_value, str) or not isinstance(expected_hash, str):
        raise EvidenceError("manifest baseline path and sha256 must be strings")
    baseline_path = Path(path_value)
    if not baseline_path.is_absolute():
        baseline_path = manifest_path.parent / baseline_path
    baseline, actual_hash = _load_json(baseline_path)
    if actual_hash != expected_hash:
        raise EvidenceError("baseline SHA-256 mismatch")
    if baseline.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(f"baseline schema_version must be {SCHEMA_VERSION}")
    results = baseline.get("observations")
    if not isinstance(results, dict):
        raise EvidenceError("baseline observations must be an object")
    return results


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{label} must be a finite number")
    return result


def _vector(value: Any, size: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != size:
        raise EvidenceError(f"{label} must contain exactly {size} numbers")
    return [_finite_number(item, label) for item in value]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise EvidenceError("cannot calculate a percentile of no values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _region(pixel: list[float], width: int, height: int) -> set[str]:
    u, v = pixel
    horizontal = "left" if u < width / 3 else "right" if u >= 2 * width / 3 else "center"
    regions = {horizontal}
    if v < height / 3:
        regions.add("top")
    if v >= 2 * height / 3:
        regions.add("bottom")
    return regions


def _matrix2(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise EvidenceError(f"{label} must be a 2x2 matrix")
    row0 = _vector(value[0], 2, label)
    row1 = _vector(value[1], 2, label)
    if abs(row0[1] - row1[0]) > 1e-9:
        raise EvidenceError(f"{label} must be symmetric")
    a, b, d = row0[0], row0[1], row1[1]
    determinant = a * d - b * b
    if a <= 0 or d <= 0 or determinant <= 0:
        raise EvidenceError(f"{label} must be positive definite")
    return a, b, d


def _covariance_stats(error_xy: list[float], covariance: Any, label: str) -> tuple[float, float]:
    a, b, d = _matrix2(covariance, label)
    determinant = a * d - b * b
    inv00, inv01, inv11 = d / determinant, -b / determinant, a / determinant
    x, y = error_xy
    nees = x * (inv00 * x + inv01 * y) + y * (inv01 * x + inv11 * y)
    trace = a + d
    largest_eigenvalue = (trace + math.sqrt(max(0.0, (a - d) ** 2 + 4 * b * b))) / 2
    semi_major_95 = math.sqrt(CHI2_2D_95 * largest_eigenvalue)
    return nees, semi_major_95


def _bootstrap_improvement_confidence(rows: list[dict[str, Any]], *, samples: int = 5000) -> float:
    """Cluster bootstrap by atomic evidence group, never by correlated rows."""
    by_group: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_group[row["evidence_group_id"]].append(
            row["baseline_error"] - row["pixel_error"]
        )
    if not by_group:
        raise EvidenceError("candidate and baseline errors must be paired")
    group_means = [statistics.mean(values) for values in by_group.values()]
    rng = random.Random(0x563258)
    wins = 0
    for _ in range(samples):
        mean = sum(rng.choice(group_means) for _ in group_means) / len(group_means)
        wins += mean > 0
    return wins / samples


def _chi_square_sum_bounds(sample_count: int) -> tuple[float, float]:
    """Wilson-Hilferty 95% bounds for a sum of 2D NEES samples."""
    degrees = 2 * sample_count
    normal = NormalDist()

    def quantile(probability: float) -> float:
        z = normal.inv_cdf(probability)
        return degrees * (1 - 2 / (9 * degrees) + z * math.sqrt(2 / (9 * degrees))) ** 3

    return quantile(0.025), quantile(0.975)


def _validated_gates(manifest: dict[str, Any]) -> dict[str, float]:
    supplied = manifest.get("gates", {})
    if not isinstance(supplied, dict):
        raise EvidenceError("manifest gates must be an object")
    unknown = set(supplied) - set(MAX_GATES)
    if unknown:
        raise EvidenceError(f"unknown gates: {sorted(unknown)}")
    gates = dict(MAX_GATES)
    for key, value in supplied.items():
        candidate = _finite_number(value, f"gate {key}")
        ceiling = MAX_GATES[key]
        if key.endswith("_min"):
            if candidate < ceiling:
                raise EvidenceError(f"gate {key} weakens fixed minimum {ceiling}")
        elif candidate > ceiling:
            raise EvidenceError(f"gate {key} weakens fixed maximum {ceiling}")
        gates[key] = candidate
    return gates


def _validate_frames(manifest_path: Path, frames: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(frames, list) or not frames:
        raise EvidenceError("manifest frames must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise EvidenceError(f"frame {index} must be an object")
        frame_id = frame.get("frame_id")
        camera_id = frame.get("camera_id")
        if not isinstance(frame_id, str) or not frame_id or frame_id in result:
            raise EvidenceError(f"frame {index} has an invalid or duplicate frame_id")
        if not isinstance(camera_id, str) or not camera_id:
            raise EvidenceError(f"frame {frame_id} has no camera_id")
        width, height = frame.get("width"), frame.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise EvidenceError(f"frame {frame_id} has invalid dimensions")
        source = frame.get("source")
        if source not in {"archived_real", "ue5_render"}:
            raise EvidenceError(f"frame {frame_id} has unsupported source {source!r}")
        _parse_timestamp(frame.get("media_timestamp_utc"), f"frame {frame_id} media_timestamp_utc")
        path_value, expected_hash = frame.get("path"), frame.get("sha256")
        if not isinstance(path_value, str) or not isinstance(expected_hash, str):
            raise EvidenceError(f"frame {frame_id} lacks path or sha256")
        frame_path = Path(path_value)
        if not frame_path.is_absolute():
            frame_path = manifest_path.parent / frame_path
        if not frame_path.is_file():
            raise EvidenceError(f"frame {frame_id} file does not exist: {frame_path}")
        raw = frame_path.read_bytes()
        actual_hash = _sha256_bytes(raw)
        if actual_hash != expected_hash:
            raise EvidenceError(f"frame {frame_id} SHA-256 mismatch")
        actual_width, actual_height = _image_dimensions(raw, str(frame_path))
        if (width, height) != (actual_width, actual_height):
            raise EvidenceError(
                f"frame {frame_id} dimensions mismatch: declared {width}x{height}, "
                f"actual {actual_width}x{actual_height}"
            )
        result[frame_id] = {**frame, "resolved_path": str(frame_path)}
    return result


def _validate_models(
    candidate: dict[str, Any], camera_ids: set[str]
) -> tuple[dict[str, Any], bool]:
    models = candidate.get("models")
    if not isinstance(models, dict) or set(models) != camera_ids:
        raise EvidenceError("candidate models must exactly cover manifest cameras")
    reports: dict[str, Any] = {}
    all_ok = True
    for camera_id in sorted(camera_ids):
        model = models[camera_id]
        if not isinstance(model, dict):
            raise EvidenceError(f"model {camera_id} must be an object")
        model_id = model.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            raise EvidenceError(f"model {camera_id} lacks model_id")
        parameter_count = model.get("parameter_count")
        observation_count = model.get("training_observation_count")
        if not isinstance(parameter_count, int) or parameter_count <= 0:
            raise EvidenceError(f"model {camera_id} has invalid parameter_count")
        if not isinstance(observation_count, int) or observation_count <= 0:
            raise EvidenceError(f"model {camera_id} has invalid training_observation_count")
        condition = _finite_number(
            model.get("normalized_jacobian_condition_number"),
            f"model {camera_id} normalized_jacobian_condition_number",
        )
        correlation = _finite_number(
            model.get("max_abs_parameter_correlation"),
            f"model {camera_id} max_abs_parameter_correlation",
        )
        eigenvalue = _finite_number(
            model.get("minimum_information_eigenvalue"),
            f"model {camera_id} minimum_information_eigenvalue",
        )
        sensitivity = _finite_number(
            model.get("prior_sensitivity_max_sigma"),
            f"model {camera_id} prior_sensitivity_max_sigma",
        )
        bound_hits = model.get("bound_hits")
        if not isinstance(bound_hits, list) or not all(
            isinstance(value, str) and value for value in bound_hits
        ):
            raise EvidenceError(f"model {camera_id} bound_hits must be a string list")
        if model.get("selected_using_split") != "validation":
            raise EvidenceError(f"model {camera_id} was not selected on validation only")
        if model.get("locked_test_used_for_selection") is not False:
            raise EvidenceError(f"model {camera_id} used locked test for model selection")
        failures: list[str] = []
        if condition > MODEL_GATES["normalized_jacobian_condition_max"]:
            failures.append("normalized Jacobian condition exceeds gate")
        if correlation > MODEL_GATES["max_abs_parameter_correlation"]:
            failures.append("parameter correlation exceeds gate")
        if eigenvalue < MODEL_GATES["minimum_information_eigenvalue"]:
            failures.append("minimum information eigenvalue is below gate")
        if sensitivity > MODEL_GATES["prior_sensitivity_max_sigma"]:
            failures.append("prior sensitivity exceeds gate")
        ratio = observation_count / parameter_count
        if ratio < MODEL_GATES["observations_per_parameter_min"]:
            failures.append("insufficient training observations per parameter")
        if bound_hits:
            failures.append("one or more fitted parameters hit a bound")
        reports[camera_id] = {
            "ok": not failures,
            "model_id": model_id,
            "parameter_count": parameter_count,
            "training_observation_count": observation_count,
            "observations_per_parameter": ratio,
            "normalized_jacobian_condition_number": condition,
            "max_abs_parameter_correlation": correlation,
            "minimum_information_eigenvalue": eigenvalue,
            "prior_sensitivity_max_sigma": sensitivity,
            "bound_hits": bound_hits,
            "failures": failures,
        }
        all_ok &= not failures
    return reports, all_ok


def evaluate(
    manifest: dict[str, Any],
    candidate: dict[str, Any],
    *,
    manifest_path: Path,
    manifest_sha256: str,
    candidate_sha256: str,
    reveal_locked_test: bool,
    operator: str | None = None,
    ticket: str | None = None,
) -> dict[str, Any]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(f"manifest schema_version must be {SCHEMA_VERSION}")
    if candidate.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(f"candidate schema_version must be {SCHEMA_VERSION}")
    if candidate.get("manifest_sha256") != manifest_sha256:
        raise EvidenceError("candidate is not bound to the exact manifest bytes")
    coordinate_frame = manifest.get("coordinate_frame")
    if not isinstance(coordinate_frame, str) or not coordinate_frame:
        raise EvidenceError("manifest must name a global coordinate_frame")

    gates = _validated_gates(manifest)
    frames = _validate_frames(manifest_path, manifest.get("frames"))
    camera_ids = {frame["camera_id"] for frame in frames.values()}
    model_reports, models_ok = _validate_models(
        candidate, camera_ids
    )
    baseline_results = _load_baseline(manifest_path, manifest)
    observations = manifest.get("observations")
    results = candidate.get("observations")
    if not isinstance(observations, list) or not observations:
        raise EvidenceError("manifest observations must be a non-empty list")
    if not isinstance(results, dict):
        raise EvidenceError("candidate observations must be an object")

    feature_splits: dict[str, str] = {}
    group_splits: dict[str, str] = {}
    frame_splits: dict[str, str] = {}
    frame_content_splits: dict[str, str] = {}
    ids: set[str] = set()
    eligible_ids: set[str] = set()
    locked_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            raise EvidenceError(f"observation {index} must be an object")
        observation_id = observation.get("observation_id")
        feature_id = observation.get("feature_id")
        group_id = observation.get("evidence_group_id")
        split = observation.get("split")
        frame_id = observation.get("frame_id")
        if not isinstance(observation_id, str) or not observation_id or observation_id in ids:
            raise EvidenceError(f"observation {index} has invalid or duplicate id")
        ids.add(observation_id)
        if not all(isinstance(value, str) and value for value in (feature_id, group_id)):
            raise EvidenceError(f"observation {observation_id} lacks feature/group identity")
        if split not in ALLOWED_SPLITS:
            raise EvidenceError(f"observation {observation_id} has invalid split {split!r}")
        for mapping, key, label in (
            (feature_splits, feature_id, "feature"),
            (group_splits, group_id, "evidence group"),
        ):
            previous = mapping.setdefault(key, split)
            if previous != split:
                raise EvidenceError(f"{label} {key} leaks across {previous} and {split}")
        if frame_id not in frames:
            raise EvidenceError(f"observation {observation_id} references unknown frame")
        frame = frames[frame_id]
        for mapping, key, label in (
            (frame_splits, frame_id, "frame"),
            (frame_content_splits, frame["sha256"], "frame content"),
        ):
            previous = mapping.setdefault(key, split)
            if previous != split:
                raise EvidenceError(f"{label} {key} leaks across {previous} and {split}")
        pixel = _vector(observation.get("pixel"), 2, f"{observation_id}.pixel")
        if not (0 <= pixel[0] < frame["width"] and 0 <= pixel[1] < frame["height"]):
            raise EvidenceError(f"observation {observation_id} pixel is outside its frame")
        world_truth = _vector(
            observation.get("world_xyz_m"), 3, f"{observation_id}.world_xyz_m"
        )
        uncertainty = _finite_number(
            observation.get("pixel_uncertainty_px"), f"{observation_id}.pixel_uncertainty_px"
        )
        if uncertainty <= 0:
            raise EvidenceError(f"observation {observation_id} uncertainty must be positive")
        category = observation.get("category")
        range_band = observation.get("range_band")
        if category not in REQUIRED_CATEGORIES:
            raise EvidenceError(f"observation {observation_id} has unsupported category")
        if range_band not in ALLOWED_RANGES:
            raise EvidenceError(f"observation {observation_id} has unsupported range_band")
        if split == LOCKED_SPLIT:
            locked_ids.add(observation_id)
            if frame["source"] != "archived_real":
                raise EvidenceError(
                    f"locked observation {observation_id} must use archived_real evidence"
                )
            if not reveal_locked_test:
                continue
        eligible_ids.add(observation_id)

        result = results.get(observation_id)
        if not isinstance(result, dict):
            raise EvidenceError(f"candidate lacks result for {observation_id}")
        projected = _vector(result.get("projected_pixel"), 2, f"{observation_id}.projected_pixel")
        if "baseline_projected_pixel" in result or "world_error_xy_m" in result:
            raise EvidenceError(
                f"candidate {observation_id} must not self-report baseline or world error"
            )
        baseline_result = baseline_results.get(observation_id)
        if not isinstance(baseline_result, dict):
            raise EvidenceError(f"pinned baseline lacks result for {observation_id}")
        baseline = _vector(
            baseline_result.get("projected_pixel"), 2, f"baseline {observation_id}"
        )
        error = math.dist(pixel, projected)
        baseline_error = math.dist(pixel, baseline)
        world_estimate = _vector(
            result.get("world_estimate_xy_m"), 2, f"{observation_id}.world_estimate_xy_m"
        )
        world_error_xy = [
            world_estimate[0] - world_truth[0],
            world_estimate[1] - world_truth[1],
        ]
        nees, semi_major = _covariance_stats(
            world_error_xy,
            result.get("world_covariance_xy_m2"),
            f"{observation_id}.world_covariance_xy_m2",
        )
        scale = frame["width"] / REFERENCE_WIDTH
        rows.append(
            {
                "observation_id": observation_id,
                "feature_id": feature_id,
                "evidence_group_id": group_id,
                "camera_id": frame["camera_id"],
                "frame_id": frame_id,
                "split": split,
                "category": category,
                "range_band": range_band,
                "regions": _region(pixel, frame["width"], frame["height"]),
                "pixel_error": error / scale,
                "baseline_error": baseline_error / scale,
                "pixel_uncertainty_covered": error <= math.sqrt(CHI2_2D_95) * uncertainty,
                "world_error": math.hypot(*world_error_xy),
                "nees": nees,
                "semi_major_95": semi_major,
                "world_estimate": world_estimate,
            }
        )

    extra = set(results) - ids
    if extra:
        raise EvidenceError(f"candidate contains unknown observations: {sorted(extra)[:5]}")
    if not reveal_locked_test and set(results) & locked_ids:
        raise EvidenceError("candidate includes locked-test results before explicit reveal")
    missing_or_extra = set(results) ^ eligible_ids
    if missing_or_extra:
        raise EvidenceError(
            f"candidate observations do not exactly cover eligible evidence: "
            f"{sorted(missing_or_extra)[:5]}"
        )
    if set(baseline_results) != ids:
        raise EvidenceError("pinned baseline must exactly cover manifest observations")
    if reveal_locked_test and (not operator or not ticket):
        raise EvidenceError("locked test reveal requires operator and ticket")

    evaluated_splits = ["train", "validation"] + ([LOCKED_SPLIT] if reveal_locked_test else [])
    cameras = sorted(camera_ids)
    if not rows:
        raise EvidenceError("no observations are eligible for evaluation")
    camera_reports: dict[str, Any] = {}
    overall_ok = models_ok
    for camera_id in cameras:
        camera_rows = [row for row in rows if row["camera_id"] == camera_id]
        split_reports: dict[str, Any] = {}
        for split in evaluated_splits:
            selected = [row for row in camera_rows if row["split"] == split]
            if not selected:
                failures = [f"camera has no {split.replace('_', '-')} observations"]
                split_reports[split] = {
                    "ok": False,
                    "metrics": {"count": 0},
                    "coverage": {"categories": [], "ranges": [], "regions": [], "groups": 0},
                    "failures": failures,
                }
                overall_ok = False
                continue
            errors = [row["pixel_error"] for row in selected]
            nees_sum = sum(row["nees"] for row in selected)
            nees_lower, nees_upper = _chi_square_sum_bounds(len(selected))
            metrics = {
                "count": len(selected),
                "pixel_metric_reference_width": int(REFERENCE_WIDTH),
                "pixel_rmse_px": math.sqrt(sum(value * value for value in errors) / len(errors)),
                "pixel_median_px": statistics.median(errors),
                "pixel_p95_px": _percentile(errors, 0.95),
                "pixel_max_px": max(errors),
                "baseline_improvement_confidence": _bootstrap_improvement_confidence(selected),
                "covariance_95_coverage": sum(row["nees"] <= CHI2_2D_95 for row in selected) / len(selected),
                "covariance_semi_major_95_max_m": max(row["semi_major_95"] for row in selected),
                "covariance_nees_sum": nees_sum,
                "covariance_nees_sum_95_bounds": [nees_lower, nees_upper],
                "pixel_uncertainty_95_coverage": sum(
                    row["pixel_uncertainty_covered"] for row in selected
                ) / len(selected),
            }
            coverage = {
                "categories": sorted({row["category"] for row in selected}),
                "ranges": sorted({row["range_band"] for row in selected}),
                "regions": sorted(set().union(*(row["regions"] for row in selected))),
                "groups": len({row["evidence_group_id"] for row in selected}),
            }
            failures: list[str] = []
            for key in ("pixel_rmse_px", "pixel_median_px", "pixel_p95_px", "pixel_max_px"):
                if metrics[key] > gates[key]:
                    failures.append(f"{key}={metrics[key]:.4f} exceeds {gates[key]:.4f}")
            for region in REQUIRED_REGIONS:
                region_errors = [row["pixel_error"] for row in selected if region in row["regions"]]
                if region_errors and _percentile(region_errors, 0.95) > gates["region_p95_px"]:
                    failures.append(f"region {region} p95 exceeds gate")
            for band in ALLOWED_RANGES:
                world_errors = [row["world_error"] for row in selected if row["range_band"] == band]
                if world_errors and _percentile(world_errors, 0.95) > gates[f"world_{band}_p95_m"]:
                    failures.append(f"world {band} p95 exceeds gate")
            if metrics["baseline_improvement_confidence"] < gates["baseline_improvement_confidence_min"]:
                failures.append("baseline improvement confidence below gate")
            if metrics["covariance_95_coverage"] < gates["covariance_95_coverage_min"]:
                failures.append("reported covariance is overconfident")
            if metrics["covariance_semi_major_95_max_m"] > gates["covariance_semi_major_95_max_m"]:
                failures.append("reported covariance is too broad")
            if not nees_lower <= nees_sum <= nees_upper:
                failures.append("reported covariance fails two-sided NEES consistency")
            if metrics["pixel_uncertainty_95_coverage"] < gates["pixel_uncertainty_95_coverage_min"]:
                failures.append("pixel residuals are inconsistent with annotation uncertainty")
            if split == "train":
                expected_training = model_reports[camera_id]["training_observation_count"]
                if len(selected) != expected_training:
                    failures.append(
                        "training evidence count does not match model diagnostics"
                    )
            if split == "validation":
                if len(selected) < MIN_VALIDATION_POINTS:
                    failures.append(
                        f"validation requires at least {MIN_VALIDATION_POINTS} observations"
                    )
                if coverage["groups"] < MIN_VALIDATION_GROUPS:
                    failures.append(
                        f"validation requires at least {MIN_VALIDATION_GROUPS} distinct groups"
                    )
            if split == LOCKED_SPLIT:
                if len(selected) < MIN_LOCKED_POINTS:
                    failures.append(f"locked test requires at least {MIN_LOCKED_POINTS} observations")
                if not REQUIRED_CATEGORIES <= set(coverage["categories"]):
                    failures.append("locked test lacks required feature categories")
                if not ALLOWED_RANGES <= set(coverage["ranges"]):
                    failures.append("locked test lacks required range bands")
                if not REQUIRED_REGIONS <= set(coverage["regions"]):
                    failures.append("locked test lacks required image regions")
                if coverage["groups"] < MIN_LOCKED_GROUPS:
                    failures.append(
                        f"locked test requires at least {MIN_LOCKED_GROUPS} distinct evidence groups"
                    )
            split_reports[split] = {"ok": not failures, "metrics": metrics, "coverage": coverage, "failures": failures}
            overall_ok &= not failures
        camera_reports[camera_id] = {"splits": split_reports}

    cross_failures: list[str] = []
    by_feature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_feature[row["feature_id"]].append(row)
    maximum_cross_error = 0.0
    cross_pairs = 0
    cross_pairs_by_split: Counter[str] = Counter()
    for feature_id, feature_rows in by_feature.items():
        for left, right in itertools.combinations(feature_rows, 2):
            if left["camera_id"] == right["camera_id"] or left["split"] != right["split"]:
                continue
            distance = math.dist(left["world_estimate"], right["world_estimate"])
            maximum_cross_error = max(maximum_cross_error, distance)
            cross_pairs += 1
            cross_pairs_by_split[left["split"]] += 1
            if distance > gates["cross_camera_world_max_m"]:
                cross_failures.append(f"feature {feature_id} cross-camera error {distance:.4f} m")
    if reveal_locked_test and cross_pairs_by_split[LOCKED_SPLIT] < MIN_LOCKED_CROSS_CAMERA_PAIRS:
        cross_failures.append(
            f"locked test requires at least {MIN_LOCKED_CROSS_CAMERA_PAIRS} "
            "cross-camera feature pairs"
        )
    overall_ok &= not cross_failures

    report = {
        "schema_version": SCHEMA_VERSION,
        "ok": overall_ok,
        "mode": "locked_test_reveal" if reveal_locked_test else "development_splits_only",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_sha256": manifest_sha256,
        "candidate_sha256": candidate_sha256,
        "coordinate_frame": coordinate_frame,
        "gates": gates,
        "model_gates": MODEL_GATES,
        "models": model_reports,
        "cameras": camera_reports,
        "cross_camera": {
            "ok": not cross_failures,
            "pair_count": cross_pairs,
            "pair_count_by_split": dict(sorted(cross_pairs_by_split.items())),
            "maximum_world_disagreement_m": maximum_cross_error,
            "failures": cross_failures,
        },
        "locked_test": {
            "available_observations": len(locked_ids),
            "revealed": reveal_locked_test,
            "burned": reveal_locked_test,
            "burn_id": (
                _sha256_bytes(
                    _canonical_bytes(
                        {
                            "manifest_sha256": manifest_sha256,
                            "candidate_sha256": candidate_sha256,
                            "operator": operator,
                            "ticket": ticket,
                        }
                    )
                )
                if reveal_locked_test
                else None
            ),
            "operator": operator if reveal_locked_test else None,
            "ticket": ticket if reveal_locked_test else None,
            "policy": "Any fit or threshold change after reveal requires a new independently surveyed locked set.",
        },
    }
    return report


def _reserve_burn(
    ledger_path: Path,
    *,
    manifest_sha256: str,
    candidate_sha256: str,
    operator: str,
    ticket: str,
) -> None:
    if not ledger_path.parent.is_dir():
        raise EvidenceError(f"burn ledger parent does not exist: {ledger_path.parent}")
    entry = {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "candidate_sha256": candidate_sha256,
        "operator": operator,
        "ticket": ticket,
        "revealed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with ledger_path.open("a+", encoding="utf-8") as ledger:
        fcntl.flock(ledger.fileno(), fcntl.LOCK_EX)
        ledger.seek(0)
        for line_number, line in enumerate(ledger, 1):
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(
                    f"burn ledger is corrupt at line {line_number}"
                ) from exc
            if existing.get("manifest_sha256") == manifest_sha256:
                raise EvidenceError(
                    "locked manifest was already revealed; survey and hash a new locked set"
                )
        ledger.seek(0, os.SEEK_END)
        ledger.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        ledger.flush()
        os.fsync(ledger.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--reveal-locked-test", action="store_true")
    parser.add_argument("--burn-ledger", type=Path)
    parser.add_argument("--operator")
    parser.add_argument("--ticket")
    parser.add_argument("--output", type=Path, help="optional report path; stdout is always emitted")
    args = parser.parse_args(argv)
    output = None
    try:
        manifest, manifest_sha = _load_json(args.manifest)
        candidate, candidate_sha = _load_json(args.candidate)
        if args.output:
            # Preflight exclusivity before an irreversible locked-set burn.
            output = args.output.open("x", encoding="utf-8")
        if args.reveal_locked_test:
            if not args.burn_ledger or not args.operator or not args.ticket:
                raise EvidenceError(
                    "locked reveal requires --burn-ledger, --operator, and --ticket"
                )
            if candidate.get("manifest_sha256") != manifest_sha:
                raise EvidenceError("candidate is not bound to the exact manifest bytes")
            _reserve_burn(
                args.burn_ledger,
                manifest_sha256=manifest_sha,
                candidate_sha256=candidate_sha,
                operator=args.operator,
                ticket=args.ticket,
            )
        report = evaluate(
            manifest,
            candidate,
            manifest_path=args.manifest,
            manifest_sha256=manifest_sha,
            candidate_sha256=candidate_sha,
            reveal_locked_test=args.reveal_locked_test,
            operator=args.operator,
            ticket=args.ticket,
        )
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        # Emit first so a later filesystem failure cannot erase all report evidence.
        print(rendered, end="")
        if output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        status = 0 if report["ok"] else 1
    except Exception as exc:  # Operational errors are distinct from evaluated gate failures.
        rendered = json.dumps({"ok": False, "error": str(exc)}, indent=2) + "\n"
        print(rendered, end="", file=sys.stderr)
        if output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        status = 2
    finally:
        if output:
            output.close()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
