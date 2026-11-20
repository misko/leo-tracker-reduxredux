import csv
import gzip
import hashlib
import json

import pytest

from tools.pipeline_eval.qualification import cavity_pairs as cavity


@pytest.fixture
def journal(tmp_path, monkeypatch):
    cpus = (18, 19)
    directory = tmp_path / "journal"
    calls, controls = {cpu: [] for cpu in cpus}, {}
    monkeypatch.setattr(cavity.os, "sched_getaffinity", lambda _: set(cpus))
    monkeypatch.setattr(cavity, "references", lambda panel, selected: (panel, selected))
    monkeypatch.setattr(cavity, "public_cases", lambda _, refs, cache: [{"id": refs[0]}])

    def worker(method, document, out, bound, cpu):
        assert bound == 720
        assert out == directory
        case = document["id"]
        if calls[cpu]:
            previous = calls[cpu][-1]
            repeat = (len(calls[cpu]) - 1) // 2 + 1
            assert (directory / f"{case}-{repeat}-{previous}.json").is_file()
        calls[cpu].append(method)
        metrics = dict(
            tracks=12,
            observations=402,
            initial_branches=3,
            initial_arm_fits=3,
            cavity_offered=False,
            stage_s={"initial": 2.0},
        )
        if method == "orbit_projector":
            metrics.update(kernel_sha256="c" * 64, compact_projections=15)
        row = dict(
            id=case,
            input_sha256=hashlib.sha256(cavity.encoded(document)).hexdigest(),
            implementation_sha256=("a" if method == "v5_core" else "b") * 64,
            worker_wall_s=8 if method == "v5_core" else 5,
            result=dict(
                status="ok",
                boundary="native detections through cavity",
                arms={"c0": {"latlon": [37, -122]}, "fitted_c": {"latlon": [37.02, -122]}},
                metrics=metrics,
            ),
        )
        controls.setdefault((case, method), row)
        return row

    monkeypatch.setattr(cavity, "run_one", worker)
    cavity.benchmark(directory, cpus)
    return directory, cpus, calls, controls


def test_runs_alternating_pairs_and_packages_all_receipts(journal, tmp_path, monkeypatch):
    directory, cpus, calls, controls = journal
    primary, alternate = cavity.METHODS, cavity.METHODS[::-1]
    assert calls[cpus[0]] == list(primary + alternate + primary + alternate + primary)
    assert calls[cpus[1]] == list(alternate + primary + alternate + primary + alternate)

    def unexpected_rerun(*args):
        pytest.fail("a completed receipt was rerun")

    monkeypatch.setattr(cavity, "run_one", unexpected_rerun)
    cavity.benchmark(directory, cpus)
    out = tmp_path / "packaged"
    cavity.package(directory, out, cpus, controls)
    with gzip.open(out / "cavity-repeats.jsonl.gz", "rt") as stream:
        receipt_rows = list(map(json.loads, stream))
    assert len(receipt_rows) == 20
    assert receipt_rows[0]["method"] == "v5_core"
    assert receipt_rows[10]["method"] == "orbit_projector"
    with (out / "cavity-projection-timing.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 10
    assert {r["speedup"] for r in rows} == {"1.6"}
    assert {r["v5_core_observations"] for r in rows} == {"402"}
    assert {r["orbit_projector_observations"] for r in rows} == {"402"}
    assert {r["c0_coordinate_delta_km"] for r in rows} == {"0.0"}
    assert {r["fitted_c_coordinate_delta_km"] for r in rows} == {"0.0"}
    regenerated = tmp_path / "regenerated"
    cavity.package(out / "cavity-repeats.jsonl.gz", regenerated, cpus, controls)
    for artifact in out.iterdir():
        assert (regenerated / artifact.name).read_bytes() == artifact.read_bytes()


def test_retains_a_changed_experimental_coordinate_but_disqualifies_its_timing(journal):
    directory, cpus, _, controls = journal
    case = next(iter(cavity.CASES))
    path = directory / f"{case}-1-orbit_projector.json"
    record = json.loads(path.read_bytes())
    record["result"]["arms"]["c0"]["latlon"][0] += 0.01
    path.write_text(json.dumps(record))
    _, timings = cavity.read_journal(directory, cpus, controls)
    assert timings[0]["speedup"] is None
    assert timings[0]["c0_coordinate_delta_km"] > 1
    assert timings[0]["fitted_c_coordinate_delta_km"] == 0


def test_requires_the_earlier_native_input(journal):
    directory, cpus, _, controls = journal
    case = next(iter(cavity.CASES))
    path = directory / f"{case}-1-v5_core.json"
    record = json.loads(path.read_bytes())
    record["input_sha256"] = "0" * 64
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="wrong recording, input, CPU or order"):
        cavity.read_journal(directory, cpus, controls)
