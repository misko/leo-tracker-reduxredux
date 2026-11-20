import csv
import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.pipeline_eval import whole_iq as iq
from tools.pipeline_eval.qualification import cavity_payload_trial
from tools.pipeline_eval.qualification import paired_epoch_full_trial as trial
from tools.pipeline_eval.qualification import whole_band_results as results
from tools.pipeline_eval.qualification import whole_pressure_trial as pressure


def test_release_receipt_changes_when_a_nested_library_or_numerical_source_changes(tmp_path):
    files = (
        "__main__.py",
        "tools/__init__.py",
        "native/manifest.json",
        "native/math.so",
        "projector.so",
        "leo/model.py",
    )
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(b"original")
    before = iq.receiver_identity(tmp_path)
    assert set(before) == set(files)
    for name in ("native/math.so", "leo/model.py"):
        (tmp_path / name).write_bytes(b"modified")
        assert iq.receiver_identity(tmp_path)[name] != before[name]


def test_native_build_must_travel_with_its_verified_sources(tmp_path):
    manifest = {}
    for field, name in (
        ("binary", "native/native_bound.so"),
        ("source", "leo/analysis/localization_v4/native_bound.c"),
        ("wrapper", "leo/analysis/localization_v4/native_bound.py"),
    ):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(field.encode())
        manifest[field] = str(path)
        manifest[field + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "native/manifest.json").write_text(json.dumps(manifest))
    projector = tmp_path / "tools/pipeline_eval/variants/orbit_projector.c"
    projector.parent.mkdir(parents=True)
    projector.write_bytes(b"projector")
    assert set(iq.native_sources(tmp_path)) == {
        "leo/analysis/localization_v4/native_bound.c",
        "tools/pipeline_eval/variants/orbit_projector.c",
    }
    source = Path(manifest["source"])
    source.unlink()
    with pytest.raises(FileNotFoundError):
        iq.native_sources(tmp_path)
    source.write_bytes(b"modified")
    with pytest.raises(ValueError, match="declared SHA-256"):
        iq.native_sources(tmp_path)
    manifest["source"] = str(tmp_path / "elsewhere.c")
    (tmp_path / "native/manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="this installation"):
        iq.native_sources(tmp_path)


def test_replay_rejects_bad_configuration_before_creating_an_attempt(tmp_path):
    cores = sorted(os.sched_getaffinity(0))
    cpu = cores[0]
    detector = tmp_path / "detector.so"
    detector.write_bytes(b"dummy")
    out = tmp_path / "attempt"
    args = ("sample", detector, "wrong-digest", tmp_path)
    with pytest.raises(ValueError, match="two distinct"):
        iq.evaluate(*args, out, [cpu, cpu], 60)
    with pytest.raises(ValueError, match="read-only"):
        iq.evaluate(*args, Path("/mnt/qnap01/replay"), [cpu, cpu], 60)
    assert not out.exists()
    with pytest.raises(ValueError, match="SHA-256"):
        iq.checked(detector, "wrong-digest")


def test_different_samples_or_exclusions_cannot_be_scored_as_matched_search_spans():
    support = {name: name + "-measured" for name in results.COMMON}
    results.pair_geometry(support, dict(support, candidate_count=81))
    for field in results.COMMON:
        with pytest.raises(ValueError, match="waveform or probe support"):
            results.pair_geometry(support, dict(support, **{field: "changed"}))


def test_unfinished_runs_are_never_counted_as_withholds_or_removed_from_the_roster(tmp_path):
    pin = dict(
        cases={
            "sample": dict(
                tile={"id": "original"},
                ordinary_sha256="a",
                catalog_sha256="b",
                request_sha256="c",
                cohort="reserve",
            )
        }
    )
    with pytest.raises(ValueError, match="no terminal attempt receipt"):
        results.attempt(tmp_path, "sample", "wide", pin)
    folder = tmp_path / "sample"
    folder.mkdir()
    (folder / "wide-failure.json").write_text(json.dumps({"error": "decoder exited early"}))
    row, resource, native = results.attempt(tmp_path, "sample", "wide", pin)
    assert native is None and resource["failure"] == "decoder exited early"
    assert row["result"]["status"] == "failed" and row["id"] == "sample"
    assert all(a["latlon"] is None for a in row["result"]["arms"].values())


def test_position_oom_keeps_authenticated_raw_evidence_on_the_complete_roster():
    report = results.REPORT
    receipts = iq.read(report / "resources.json")
    lock = iq.read(report / "prediction-lock.json")
    iq.checked(report / "resources.json", lock["files"]["resources.json"])
    case = "DS29-0247"
    assert len(receipts) == 6 and set(receipts) == set(lock["cases"])
    narrow, wide = (receipts[case][key] for key in ("narrow", "wide"))
    results.pair_geometry(narrow, wide)
    assert narrow["failure"].startswith("oom-kill:")
    assert narrow["charged_peak_to_failure_bytes"] == iq.MEMORY
    assert narrow["cpu_to_failure_s"] > 0 and narrow["wall_to_failure_s"] > narrow["raw_s"]
    assert "position_s" not in narrow and "wall_s" not in narrow
    assert narrow["dual_calls"] == wide["dual_calls"] == narrow["counts"]["processed_windows"]
    assert narrow["stages"][-1]["memory.swap.max"] == 0
    snapshot = gzip.decompress((report / "measured-whole-iq.py.gz").read_bytes())
    source = iq.read(report / "source-lock.json")["sources"]["tools/pipeline_eval/whole_iq.py"]
    assert hashlib.sha256(snapshot).hexdigest() == source


def test_shared_epochs_use_the_wide_control_on_identical_reserve_recordings():
    lock = iq.read(trial.REPORT / "prediction-lock.json")
    assert set(lock["cases"]) == set(trial.CASES)
    iq.checked(results.REPORT / "prediction-lock.json", lock["parent_sha256"])
    resources = iq.read(trial.REPORT / "resources.json")
    with gzip.open(trial.REPORT / "positions.jsonl.gz", "rt") as stream:
        rows = [json.loads(line) for line in stream]
    with (trial.REPORT / "scores.csv").open() as stream:
        scores = list(csv.DictReader(stream))
    for case in trial.CASES:
        results.pair_geometry(resources[case]["union"], resources[case]["wide"])
        methods = {r["method"] for r in rows if r["id"] == case}
        assert methods == {trial.UNION, results.METHOD["wide"]}
    assert len(scores) == 2 * 2 * len(trial.CASES)
    assert {r["arm"] for r in scores} == {"c0", "fitted_c"}


def test_public_install_repeated_the_repaired_positions_and_complete_narrow_native_archive():
    repeat = iq.read(pressure.REPORT / "installed-profile.json")
    iq.checked(pressure.REPORT / "prediction-lock.json", repeat["primary_prediction_sha256"])
    records = pressure.rows_from(pressure.REPORT / "positions.jsonl.gz")
    primary = next(row for row in records if row["method"] == pressure.BRANCHES["repair"])
    assert repeat["case"] == primary["id"] and repeat["native_sha256"] == primary["native_sha256"]
    assert repeat["distinct_recording"] is False
    assert cavity_payload_trial.scientific_result(repeat["result"]) == (
        cavity_payload_trial.scientific_result(primary["result"])
    )
    assert repeat["resources"]["dual_calls"] == 6767
    assert repeat["resources"]["max_bytes"] == iq.MEMORY
    assert repeat["resources"]["swap_bytes"] == 0
