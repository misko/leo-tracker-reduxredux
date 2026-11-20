import json
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import iq_joint_resources as resource
from tools.pipeline_eval.qualification import iq_joint_results as results
from tools.pipeline_eval.qualification import iq_joint_trial as trial


def case_fixture():
    return dict(
        id="roof",
        catalog=dict(path="catalog", sha256="catalog-digest"),
        native=dict(path="native-original", sha256="capture-era"),
        track_config=dict(path="graph", sha256="graph-digest"),
        cutoff_utc_ns=40,
        catalog_timestamp_ns=38,
        recording=dict(window_count=12),
        regions=[dict(id="original", center=[40.0, 15.0])],
    )


def test_native_query_mounts_and_hashes_the_just_written_factors(tmp_path):
    case = case_fixture()
    path = tmp_path / "fresh-native.json"
    path.write_bytes(b"fresh detector factors")
    sha = sha256(path.read_bytes()).hexdigest()
    query, mounts = trial.bind_fresh(case, path, sha)
    assert mounts["native"] == path
    assert query["native"] == dict(path="/input/native", sha256=sha)
    assert query["probe_limit"] == 24
    assert query["track_config"]["sha256"] == "graph-digest"
    assert query["catalogue"]["sha256"] == "catalog-digest"
    assert query["cutoff"] == 40 and query["catalog_timestamp"] == 38
    assert case["native"]["sha256"] == "capture-era"
    with pytest.raises(ValueError, match="differs from the fresh native"):
        trial.bind_fresh(case, path, "capture-era")


def test_missing_tile_changes_only_the_offer(tmp_path):
    case = case_fixture()
    path = tmp_path / "fresh-native.json"
    path.write_bytes(b"the same detector evidence")
    sha = sha256(path.read_bytes()).hexdigest()
    wrong = dict(id="omitted", center=[44.0, 23.0])
    primary, mounts = trial.bind_fresh(case, path, sha)
    alternative, second_mounts = trial.bind_fresh(case, path, sha, wrong)
    assert alternative == dict(primary, offer=wrong) and mounts == second_mounts


def test_lanes_combine_only_near_time_samples_and_keep_sum_of_peaks_separate(tmp_path):
    paths = [tmp_path / f"lane-{i}.log" for i in range(2)]
    values = [((0, 80), (700_000_000, 90)), ((10, 120), (1_400_000_000, 130))]
    for lane, (path, samples) in enumerate(zip(paths, values, strict=True)):
        terminal = dict(VmHWM=100 + 50 * lane, VmPeak=300, address_space_limit_mib=768)
        path.write_text(
            "".join(resource.SAMPLE_PREFIX + f"{t} {rss}\n" for t, rss in samples)
            + resource.MEMORY_PREFIX
            + json.dumps(terminal)
            + "\n"
        )
    summary = resource.raw_memory(paths)
    assert summary["largest_individual_rss_kib"] == 150
    assert summary["sum_of_individual_peaks_kib"] == 250
    assert summary["largest_near_simultaneous_sampled_sum_rss_kib"] == 200
    assert summary["paired_memory_samples"] == 1


def test_cpu_accounting_uses_independent_sandbox_self_counter():
    row = {"worker": {"cpu_s": 2.5}}
    receipt = results.account_cpu(row, 50)
    assert receipt == dict(
        host_supervisor_and_waited_cpu_s=50, isolated_fitter_self_cpu_s=2.5, total_cpu_s=52.5
    )
    assert row["worker_cpu_s"] == 52.5
    assert results.account_cpu({}, 50)["total_cpu_s"] is None
