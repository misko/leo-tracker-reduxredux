import numpy as np
import pytest
from compare_algo07v3_published import exact_persisted, mapped_predictive, read_export


def test_persisted_comparison_checks_every_scientific_value():
    old = dict(case="SCAN", phase=[1.0, 2.0], owners={"point": 69333}, score=1.0)
    new = dict(phase=np.array([1.0, 2.0]), owners={"point": 69333}, score=1.0)
    exact_persisted(old, new, {"case"})
    for changed in (
        dict(new, phase=np.array([1.0, 2.00000000001])),
        dict(new, owners={"point": 12345}),
        dict(new, score=1.000000000001),
    ):
        with pytest.raises(ValueError):
            exact_persisted(old, changed, {"case"})


def test_unknown_or_missing_bookkeeping_does_not_silently_disappear():
    with pytest.raises(ValueError, match="scope"):
        exact_persisted(dict(score=1, surprise=True), dict(score=1), set())
    with pytest.raises(ValueError, match="scope"):
        exact_persisted(dict(score=1), dict(score=1), {"case"})


def test_reference_export_hash_is_checked(tmp_path):
    import json

    stage = tmp_path / "ALGO02"
    stage.mkdir()
    (stage / "value.json").write_text('{"value": 1}')
    (stage / "descriptor.json").write_text(json.dumps(dict(files={"value.json": "wrong"})))
    with pytest.raises(ValueError, match="changed"):
        read_export(tmp_path, "ALGO02", "value.json")


def test_predictive_mapping_does_not_erase_unbound_retry_evidence(tmp_path):
    original = dict(
        selected=None,
        attempts=[
            dict(
                numerical_retry=dict(original_trial="/source/original", retry_trial="/source/retry")
            )
        ],
    )
    with pytest.raises(ValueError, match="no bound"):
        mapped_predictive(original, dict(source_worker_root="/source", files={}), tmp_path)


def test_failed_process_cannot_be_mapped_to_completed_science(tmp_path):
    original = dict(
        selected=None, attempts=[], stages=[dict(name="inventory", status="complete", returncode=1)]
    )
    with pytest.raises(ValueError, match="nonzero exit"):
        mapped_predictive(original, {}, tmp_path)


def test_trigger_checks_full_ranking_including_unselected_families():
    from compare_algo07v3_published import compare_trigger

    original = dict(ranking=[dict(norad=1, score=2.0), dict(norad=2, score=1.0)], selected=[1])
    candidate = dict(
        status="reassociation_targets_ranked",
        ranking=original["ranking"],
        targets=[1],
        recovery_complete=False,
    )
    compare_trigger(original, candidate)
    with pytest.raises(ValueError):
        compare_trigger(original, dict(candidate, ranking=[dict(norad=1, score=2.0)]))
    with pytest.raises(ValueError):
        compare_trigger(original, dict(candidate, targets=[2]))


@pytest.fixture
def final_fallback(tmp_path):
    import hashlib
    from copy import deepcopy

    descriptor = dict(source_worker_root="/source", files={})
    for name in ("catalogue.json", "input.json", "candidate/protocol.json"):
        path = tmp_path / "worker/recovery" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        descriptor["files"][str(path.relative_to(tmp_path))] = (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        )
    sha = hashlib.sha256(b"{}").hexdigest()
    original = dict(
        selected=None,
        records=[],
        review=[],
        execution_status="complete",
        final=dict(c0=dict(x=[1.0, 2.0]), fitted_c=dict(x=[2.0, 3.0])),
        catalogue_eligibility=dict(
            candidate_count=11,
            catalogue_path="/source/recovery/catalogue.json",
            catalogue_sha256=sha,
            input_path="/source/recovery/input.json",
            input_sha256=sha,
        ),
        case="SCAN",
        seconds=1.0,
        protocol_sha256=sha,
    )
    value = deepcopy(original)
    for key in ("case", "seconds", "protocol_sha256"):
        del value[key]
    for key in ("catalogue_path", "catalogue_sha256", "input_path", "input_sha256"):
        del value["catalogue_eligibility"][key]
    value.update(control_fits={}, candidate_fits={})
    candidate = dict(status="reassociation_evaluated", recovery_complete=True, recovery=value)
    return original, candidate, descriptor, tmp_path


def test_final_fallback_checks_all_results_and_bound_files(final_fallback):
    from compare_algo07v3_published import compare_final_fallback

    compare_final_fallback(*final_fallback)
    original, candidate, descriptor, folder = final_fallback
    candidate["recovery"]["final"]["c0"]["x"][0] += 1e-10
    with pytest.raises(ValueError):
        compare_final_fallback(*final_fallback)


@pytest.mark.parametrize("field", ["control_fits", "candidate_fits", "records", "review"])
def test_final_mapping_rejects_uncovered_fit_branches(final_fallback, field):
    from compare_algo07v3_published import compare_final_fallback

    final_fallback[1]["recovery"][field] = {"unmapped": 1}
    with pytest.raises(ValueError):
        compare_final_fallback(*final_fallback)


def test_final_mapping_rejects_changed_source_link(final_fallback):
    from compare_algo07v3_published import compare_final_fallback

    (final_fallback[3] / "worker/recovery/catalogue.json").write_text('{"changed": true}')
    with pytest.raises(ValueError, match="Source bytes changed"):
        compare_final_fallback(*final_fallback)


def test_no_admission_screen_checks_rejected_candidates_and_both_cavities(final_fallback):
    from copy import deepcopy

    from compare_algo07v3_published import compare_screen_no_admission

    original, final, descriptor, folder = final_fallback
    original.update(targets=[1], guards={}, propagation_failures=[])
    screens = {
        "1": dict(
            cavity={a: dict(seconds=1.0, objective=5.0) for a in ("c0", "fitted_c")},
            proposals=[dict(norad=2, passed=False, score=4.0)],
        )
    }
    candidate = dict(
        status="reassociation_candidates_screened",
        recovery_complete=False,
        admission=dict(
            status="screened",
            targets=[1],
            catalogue_eligibility=final["recovery"]["catalogue_eligibility"],
            propagation_failures=[],
            screens=deepcopy(screens),
            shared={},
            guards={},
            admitted=[],
        ),
    )
    for arm in candidate["admission"]["screens"]["1"]["cavity"].values():
        del arm["seconds"]
    compare_screen_no_admission(original, screens, candidate, descriptor, folder)
    changed = deepcopy(candidate)
    changed["admission"]["screens"]["1"]["proposals"][0]["score"] += 1e-10
    with pytest.raises(ValueError):
        compare_screen_no_admission(original, screens, changed, descriptor, folder)
    changed = deepcopy(candidate)
    del changed["admission"]["screens"]["1"]["cavity"]["c0"]
    with pytest.raises(ValueError):
        compare_screen_no_admission(original, screens, changed, descriptor, folder)
    with pytest.raises(ValueError, match="Missing or extra"):
        compare_screen_no_admission(original, {}, candidate, descriptor, folder)


@pytest.mark.parametrize("width", [0, 3, 12])
@pytest.mark.parametrize("order", ["C", "F"])
@pytest.mark.parametrize("experiment", ["scatter", "factor_reuse"])
def test_experimental_kernels_preserve_exact_results_across_sparse_shapes(width, order, experiment):
    import runpy
    from pathlib import Path

    from leo.analysis.localization_v3.hierarchical import hierarchical_bound

    relative = (
        "reports/2026_11_05_algo07v3_pair/probe_assembly.py"
        if experiment == "scatter"
        else "reports/2026_11_05_algo07v3_assembly/probe_factor_reuse.py"
    )
    path = Path(__file__).resolve().parents[2] / relative
    candidate, _, _ = runpy.run_path(str(path))["candidate_function"]()
    rng = np.random.default_rng(177)
    features = rng.normal(size=(21, width))
    features[rng.random(features.shape) < 0.6] = 0
    features = np.array(features, order=order)
    y, sigma, groups = rng.normal(size=21), rng.uniform(10, 50, 21), np.arange(21) % 4
    prior = np.arange(width) // 3 - 1
    kwargs = dict(prior_groups=prior, powers=0.75, iterations=10)
    original = hierarchical_bound(y, features, sigma, groups, **kwargs)
    actual = candidate(y, features, sigma, groups, **kwargs)
    assert original.keys() == actual.keys()
    for key in original:
        a, b = np.asarray(original[key]), np.asarray(actual[key])
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), key


def test_gap_prepare_only_mapping_verifies_native_support_and_process(tmp_path):
    import hashlib
    import json
    from copy import deepcopy

    from compare_algo07v3_published import compare_gap_no_split

    descriptor = dict(source_worker_root="/worker", files={})

    def write(relative, value):
        path = tmp_path / "worker" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        descriptor["files"]["worker/" + relative] = "sha256:" + sha
        return sha

    sha = write("inventory.json", {})
    write("validation/result.json", {})
    write(
        "target/source.json",
        dict(
            track_id="t",
            points=2,
            inventory="/worker/inventory.json",
            validation="/worker/validation",
        ),
    )
    write(
        "target/gap/protocol.json",
        dict(parent_observation_ids=["p", "q"], input_sha256={"/worker/inventory.json": sha}),
    )
    write("target/gap/branches.json", dict(branches=[dict(observation_ids=["p", "q"])]))
    stage = dict(
        command=[
            "python",
            "-B",
            "/old/algo05_gap_stage.py",
            "prepare",
            "/worker/target/source.json",
            "/worker/target/gap",
        ],
        returncode=0,
        seconds=1.0,
        timeout_s=180,
    )
    original = dict(
        selected=None,
        candidate=None,
        trials=[],
        excluded=[],
        stages=[stage],
        no_GPS_inference=True,
        causal_only=True,
    )
    candidate = dict(
        original,
        stages=[dict(name="gap-0-prepare", status="complete", seconds=0.5, timeout_s=180)],
        targets=[dict(track_id="t", points=2)],
        numerical_receipts={},
    )
    compare_gap_no_split(original, candidate, descriptor, tmp_path)
    for changed in (
        dict(candidate, targets=[dict(track_id="t", points=1)]),
        dict(candidate, numerical_receipts={"unmapped": 1}),
    ):
        with pytest.raises(ValueError):
            compare_gap_no_split(original, changed, descriptor, tmp_path)
    failed = deepcopy(original)
    failed["stages"][0]["returncode"] = 1
    with pytest.raises(ValueError, match="Completed"):
        compare_gap_no_split(failed, candidate, descriptor, tmp_path)
    write("target/gap/branches.json", dict(branches=[dict(observation_ids=["p"])]))
    with pytest.raises(ValueError, match="Actual split"):
        compare_gap_no_split(original, candidate, descriptor, tmp_path)
