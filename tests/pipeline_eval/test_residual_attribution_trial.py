import json
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


@pytest.fixture(scope="module")
def trial():
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    source = reports / "residual_attribution_trial.py"
    spec = spec_from_file_location(source.stem, source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native(ranks):
    raw, detector = "sha256:raw", "native"
    rows = [dict(visit_index=i, receiver_id=i % 2, valid_start_counter=1000*i,
                 candidates=[] if r is None else [dict(candidate_rank=r, cfo=1200*r)])
            for i, r in enumerate(ranks)]
    digest = canonical_digest(["cancellation", raw, detector, rows])
    return dict(source=dict(raw_recording_authority_digest=raw, probes=rows,
                            analysis_manifest_sha256=digest, session_id="session"),
                provenance=dict(detector_sha256="sha256:" + detector, run_id="before"),
                clock_anchor={"counter": 0})


def test_saved_solver_retains_regional_geometry_and_drops_raw_reader_dependencies(trial):
    spec = dict(ingress="paired-sha256", paired_sha256={"library": "pinned"}, member_lookahead=True,
                fractional_score_selection=True, curved_design=True, longitude_chart=True,
                detector_sha256="original", sources={"solver": "pinned"}, regional_veto=True)
    before = deepcopy(spec)
    replay = trial.saved_solver_options(spec)
    assert replay["ingress"] == "stock"
    assert not {"member_lookahead", "paired_sha256", "fractional_score_selection"} & replay.keys()
    for key in ("curved_design", "longitude_chart", "detector_sha256", "sources", "regional_veto"):
        assert replay[key] == spec[key]
    assert spec == before


def test_partition_depends_only_on_either_native_rank_and_preserves_order(trial):
    before = native([0, None, 1, None, 0, 1, 1, 0])
    after = native([None, 0, None, 1, 1, 0, 1, 0])
    snapshots = deepcopy(before), deepcopy(after)
    inputs, partition = trial.hybrids(before, after)
    trace = {
        item["visit"]: item["group"] for item in partition["changed"]
    }
    assert trace == {
        0: "restore-primary", 1: "restore-primary", 2: "restore-residual",
        3: "restore-residual", 4: "restore-residual", 5: "restore-residual",
    }
    assert [trial.rank(r) for r in inputs["restore-primary"]["source"]["probes"]] == (
        [0, None, None, 1, 1, 0, 1, 0]
    )
    assert [trial.rank(r) for r in inputs["restore-residual"]["source"]["probes"]] == (
        [None, 0, 1, None, 0, 1, 1, 0]
    )
    assert inputs["unchanged"] == after
    assert inputs["restore-all"]["source"]["probes"] == before["source"]["probes"]
    for mode, document in inputs.items():
        assert document["clock_anchor"] == after["clock_anchor"]
        if mode != "unchanged":
            assert document["source"]["analysis_manifest_sha256"] != (
                after["source"]["analysis_manifest_sha256"]
            )
    assert (before, after) == snapshots


def test_probe_metadata_must_match_even_when_only_one_factor_differs(trial):
    before, after = native([None, 1]), native([None, None])
    before["source"]["probes"][1]["receiver_id"] = 0
    with pytest.raises(ValueError, match="opportunity metadata"):
        trial.hybrids(before, after)


def test_controls_require_both_endpoints_and_completed_publication(trial):
    arms = {"c0": {"latlon": [1.1, 10.]}, "fitted_c": {"latlon": [1.2, 10.]}}
    solved = dict(status="ok", arms=deepcopy(arms))
    published = dict(arms=arms, receipt={"decision": "complete"})
    assert trial.controls_match(solved, published)
    solved["arms"]["fitted_c"]["latlon"] = [1.2, 10.1]
    assert not trial.controls_match(solved, published)


def test_reference_remains_unread_until_all_solves_are_sealed(trial, tmp_path):
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"plan": {"case": trial.CASE}, "results": {"unchanged": {}}}))
    with pytest.raises(ValueError, match="all four completed solves"):
        trial.score(partial, tmp_path / "reference-must-not-exist.json")
