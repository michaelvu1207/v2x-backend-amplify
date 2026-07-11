import hashlib
import json
import struct

import pytest

from apps.perception.tools.evaluate_calibration_evidence import (
    EvidenceError,
    evaluate,
    main,
)


def _write_frame(tmp_path, name="frame.png", width=2560, height=1920):
    path = tmp_path / name
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + name.encode()
    )
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path, count=30):
    frames_by_split = {}
    frame_records = []
    for split in ("locked_test", "validation", "train"):
        for camera_id in ("ch1", "ch2"):
            frame, digest = _write_frame(tmp_path, f"{split}-{camera_id}.png")
            frames_by_split[(split, camera_id)] = frame
            frame_records.append(
                {
                    "frame_id": f"f-{split}-{camera_id}",
                    "camera_id": camera_id,
                    "path": str(frame),
                    "sha256": digest,
                    "width": 2560,
                    "height": 1920,
                    "source": "archived_real",
                    "media_timestamp_utc": "2026-07-11T00:00:00Z",
                }
            )
    manifest = {
        "schema_version": 1,
        "coordinate_frame": "EPSG:4978",
        "frames": frame_records,
        "observations": [],
    }
    categories = ["road_edge", "lane_marking", "stable_landmark"]
    ranges = ["near", "mid", "far"]
    pixels = [(100, 100), (1280, 100), (2450, 100), (100, 960), (2450, 1800), (1280, 1800)]
    candidate = {
        "schema_version": 1,
        "manifest_sha256": "pending",
        "observations": {},
        "models": {
            camera_id: {
                "model_id": "brown5_full",
                "parameter_count": 15,
                "training_observation_count": 30,
                "normalized_jacobian_condition_number": 1.0e5,
                "max_abs_parameter_correlation": 0.8,
                "minimum_information_eigenvalue": 1.0e-4,
                "prior_sensitivity_max_sigma": 0.5,
                "bound_hits": [],
                "selected_using_split": "validation",
                "locked_test_used_for_selection": False,
            }
            for camera_id in ("ch1", "ch2")
        },
    }
    baseline = {"schema_version": 1, "observations": {}}
    for split, split_count in (("locked_test", count), ("validation", 15), ("train", 30)):
        for camera_id in ("ch1", "ch2"):
            for index in range(split_count):
                observation_id = f"o-{split}-{camera_id}-{index}"
                pixel = list(pixels[index % len(pixels)])
                manifest["observations"].append(
                    {
                        "observation_id": observation_id,
                        "feature_id": f"{split}-feature-{index}",
                        "evidence_group_id": f"{split}-group-{index}",
                        "frame_id": f"f-{split}-{camera_id}",
                        "split": split,
                        "category": categories[index % len(categories)],
                        "range_band": ranges[index % len(ranges)],
                        "world_xyz_m": [float(index), 0.0, 1.0],
                        "pixel": pixel,
                        "pixel_uncertainty_px": 0.25,
                    }
                )
                candidate["observations"][observation_id] = {
                    "projected_pixel": [pixel[0] + 0.5, pixel[1]],
                    "world_covariance_xy_m2": [[0.00125, 0.0], [0.0, 0.00125]],
                    "world_estimate_xy_m": [float(index) + 0.05, 0.0],
                }
                baseline["observations"][observation_id] = {
                    "projected_pixel": [pixel[0] + 10.0, pixel[1]]
                }
    baseline_path = tmp_path / "baseline.json"
    baseline_bytes = json.dumps(baseline).encode()
    baseline_path.write_bytes(baseline_bytes)
    manifest["baseline"] = {
        "path": str(baseline_path),
        "sha256": hashlib.sha256(baseline_bytes).hexdigest(),
    }
    manifest_sha = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
    candidate["manifest_sha256"] = manifest_sha
    candidate_sha = hashlib.sha256(json.dumps(candidate).encode()).hexdigest()
    return (
        manifest,
        candidate,
        manifest_sha,
        candidate_sha,
        frames_by_split[("locked_test", "ch1")],
    )


def _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha, reveal=True):
    manifest_path = tmp_path / "manifest.json"
    return evaluate(
        manifest,
        candidate,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        candidate_sha256=candidate_sha,
        reveal_locked_test=reveal,
        operator="test-operator" if reveal else None,
        ticket="TEST-1" if reveal else None,
    )


def _write_cli_inputs(tmp_path, manifest, candidate):
    manifest_path = tmp_path / "manifest.json"
    manifest_bytes = json.dumps(manifest).encode()
    manifest_path.write_bytes(manifest_bytes)
    candidate["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate))
    return manifest_path, candidate_path


def test_locked_test_passes_strict_metrics_and_emits_burn_record(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    assert report["ok"] is True
    assert report["locked_test"]["burned"] is True
    assert len(report["locked_test"]["burn_id"]) == 64
    assert report["cameras"]["ch1"]["splits"]["locked_test"]["metrics"]["count"] == 30


def test_locked_test_is_not_evaluated_without_explicit_reveal(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    with pytest.raises(EvidenceError, match="includes locked-test results"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha, reveal=False)


def test_rejects_feature_split_leakage(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    manifest["observations"][1]["feature_id"] = manifest["observations"][0]["feature_id"]
    manifest["observations"][1]["split"] = "validation"
    with pytest.raises(EvidenceError, match="feature .* leaks"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_evidence_group_split_leakage(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    manifest["observations"][1]["evidence_group_id"] = manifest["observations"][0]["evidence_group_id"]
    manifest["observations"][1]["split"] = "validation"
    with pytest.raises(EvidenceError, match="evidence group .* leaks"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_frame_hash_mismatch(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, frame = _fixture(tmp_path)
    frame.write_bytes(b"changed")
    with pytest.raises(EvidenceError, match="SHA-256 mismatch"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_declared_image_dimension_mismatch(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    manifest["frames"][0]["width"] = 25600
    with pytest.raises(EvidenceError, match="dimensions mismatch"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_frame_level_split_leakage(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    manifest["observations"][1]["split"] = "validation"
    with pytest.raises(EvidenceError, match="frame .* leaks"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_identical_frame_content_hidden_behind_different_ids(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    locked = next(frame for frame in manifest["frames"] if frame["frame_id"] == "f-locked_test-ch1")
    validation = next(frame for frame in manifest["frames"] if frame["frame_id"] == "f-validation-ch1")
    validation["path"] = locked["path"]
    validation["sha256"] = locked["sha256"]
    with pytest.raises(EvidenceError, match="frame content .* leaks"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_synthetic_locked_frame(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    manifest["frames"][0]["source"] = "ue5_render"
    with pytest.raises(EvidenceError, match="must use archived_real"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_weakened_gate(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    manifest["gates"] = {"pixel_p95_px": 7.0}
    with pytest.raises(EvidenceError, match="weakens fixed maximum"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_fails_overconfident_covariance(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    for result in candidate["observations"].values():
        result["world_estimate_xy_m"][0] += 1.0
        result["world_covariance_xy_m2"] = [[0.0001, 0.0], [0.0, 0.0001]]
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    split = report["cameras"]["ch1"]["splits"]["locked_test"]
    assert report["ok"] is False
    assert "reported covariance is overconfident" in split["failures"]


def test_world_error_is_derived_from_surveyed_truth(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    for key, result in candidate["observations"].items():
        if "-ch1-" in key:
            result["world_estimate_xy_m"][0] += 3.0
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    failures = report["cameras"]["ch1"]["splits"]["locked_test"]["failures"]
    assert any("world" in failure and "p95" in failure for failure in failures)


def test_rejects_candidate_self_reported_world_error_or_baseline(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    candidate["observations"]["o-locked_test-ch1-0"]["world_error_xy_m"] = [0.0, 0.0]
    with pytest.raises(EvidenceError, match="must not self-report"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_rejects_tampered_baseline_artifact(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text("{}")
    with pytest.raises(EvidenceError, match="baseline SHA-256 mismatch"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_fails_camera_with_no_locked_observations(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    removed = {
        row["observation_id"]
        for row in manifest["observations"]
        if row["frame_id"] == "f-locked_test-ch2"
    }
    manifest["observations"] = [
        row for row in manifest["observations"] if row["observation_id"] not in removed
    ]
    for observation_id in removed:
        candidate["observations"].pop(observation_id)
    baseline_path = tmp_path / "baseline.json"
    baseline = json.loads(baseline_path.read_text())
    for observation_id in removed:
        baseline["observations"].pop(observation_id)
    baseline_bytes = json.dumps(baseline).encode()
    baseline_path.write_bytes(baseline_bytes)
    manifest["baseline"]["sha256"] = hashlib.sha256(baseline_bytes).hexdigest()
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    assert report["cameras"]["ch2"]["splits"]["locked_test"]["ok"] is False
    assert "no locked-test" in report["cameras"]["ch2"]["splits"]["locked_test"]["failures"][0]


def test_fails_cross_camera_world_disagreement(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    for key, result in candidate["observations"].items():
        if "-ch2-" in key:
            result["world_estimate_xy_m"][1] += 1.5
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    assert report["cross_camera"]["ok"] is False
    assert report["cross_camera"]["pair_count_by_split"]["locked_test"] == 30


def test_fails_locked_test_with_too_few_points(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path, count=12)
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    failures = report["cameras"]["ch1"]["splits"]["locked_test"]["failures"]
    assert any("at least 30" in failure for failure in failures)


def test_candidate_must_bind_exact_manifest_bytes(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    candidate["manifest_sha256"] = "0" * 64
    with pytest.raises(EvidenceError, match="exact manifest bytes"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("normalized_jacobian_condition_number", 1.0e9, "Jacobian condition"),
        ("max_abs_parameter_correlation", 0.99, "parameter correlation"),
        ("minimum_information_eigenvalue", 1.0e-10, "information eigenvalue"),
        ("prior_sensitivity_max_sigma", 3.0, "prior sensitivity"),
        ("training_observation_count", 20, "observations per parameter"),
        ("bound_hits", ["k3"], "hit a bound"),
    ],
)
def test_model_identifiability_failures_are_explicit(
    tmp_path, field, value, failure
):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    candidate["models"]["ch1"][field] = value
    report = _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)
    assert report["ok"] is False
    assert any(failure in item for item in report["models"]["ch1"]["failures"])


def test_rejects_locked_test_model_selection(tmp_path):
    manifest, candidate, manifest_sha, candidate_sha, _ = _fixture(tmp_path)
    candidate["models"]["ch1"]["locked_test_used_for_selection"] = True
    with pytest.raises(EvidenceError, match="used locked test"):
        _evaluate(tmp_path, manifest, candidate, manifest_sha, candidate_sha)


def test_cli_burn_ledger_is_append_only_and_prevents_repeat_reveal(tmp_path):
    manifest, candidate, _, _, _ = _fixture(tmp_path)
    manifest_path, candidate_path = _write_cli_inputs(tmp_path, manifest, candidate)
    ledger = tmp_path / "burn-ledger.jsonl"
    output = tmp_path / "report.json"
    args = [
        str(manifest_path),
        str(candidate_path),
        "--reveal-locked-test",
        "--burn-ledger",
        str(ledger),
        "--operator",
        "test-operator",
        "--ticket",
        "TEST-1",
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert len(ledger.read_text().strip().splitlines()) == 1
    assert output.is_file()
    assert main(args) == 2
    assert len(ledger.read_text().strip().splitlines()) == 1


def test_cli_distinguishes_gate_failure_from_operational_error(tmp_path):
    manifest, candidate, _, _, _ = _fixture(tmp_path)
    for result in candidate["observations"].values():
        result["projected_pixel"][0] += 100.0
    manifest_path, candidate_path = _write_cli_inputs(tmp_path, manifest, candidate)
    assert main(
        [
            str(manifest_path),
            str(candidate_path),
            "--reveal-locked-test",
            "--burn-ledger",
            str(tmp_path / "ledger.jsonl"),
            "--operator",
            "test-operator",
            "--ticket",
            "TEST-2",
        ]
    ) == 1
    candidate["manifest_sha256"] = "0" * 64
    candidate_path.write_text(json.dumps(candidate))
    assert main([str(manifest_path), str(candidate_path)]) == 2


def test_post_burn_error_is_persisted_to_exclusive_report(tmp_path):
    manifest, candidate, _, _, _ = _fixture(tmp_path)
    candidate["observations"]["o-locked_test-ch1-0"]["world_error_xy_m"] = [0.0, 0.0]
    manifest_path, candidate_path = _write_cli_inputs(tmp_path, manifest, candidate)
    ledger = tmp_path / "ledger.jsonl"
    output = tmp_path / "error-report.json"
    status = main(
        [
            str(manifest_path),
            str(candidate_path),
            "--reveal-locked-test",
            "--burn-ledger",
            str(ledger),
            "--operator",
            "test-operator",
            "--ticket",
            "TEST-3",
            "--output",
            str(output),
        ]
    )
    assert status == 2
    assert len(ledger.read_text().strip().splitlines()) == 1
    persisted = json.loads(output.read_text())
    assert persisted["ok"] is False
    assert "must not self-report" in persisted["error"]
