from copy import deepcopy
import gzip
import json
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import short_shared_phase_0016 as experiment


def test_admission_preflights_the_controller_meter_in_its_own_process():
    keys = ["cpu_s", "input_blocks"]
    experiment.check_controller(SimpleNamespace(controller_preflight=lambda: keys), {"controller_counters": keys})
    with pytest.raises(ValueError, match="meter counters"):
        experiment.check_controller(SimpleNamespace(controller_preflight=lambda: []), {"controller_counters": keys})


def test_new_detector_identity_is_derived_at_both_recipe_boundaries(monkeypatch):
    digest = lambda value: experiment.callback.digest(experiment.canonical(value))
    base = dict(shortened_sha256=experiment.callback.ORIGINAL, aperture_samples=[200_000, 80_000])
    held = dict(base, held_native_8ms={"route": "unfiltered"})
    monkeypatch.setattr(experiment, "OLD_BASE_RECIPE", digest(base))
    monkeypatch.setattr(experiment, "OLD_HELD_RECIPE", digest(held))
    short = "1" * 64
    assert experiment.pins(short, held) == (digest(dict(base, shortened_sha256=short)),
                                            digest(dict(held, shortened_sha256=short)))
    with pytest.raises(ValueError, match="held policy"):
        experiment.pins(short, dict(held, held_native_8ms={"route": "history"}))


def test_scoring_allows_guarded_short_scores_and_checks_exact_anchor_and_sign():
    factor = dict.fromkeys(experiment.SCORE_FIELDS, .15)
    factor.update(candidate_rank=0, fractional_tracking_cfo_hz=-0., passed_fractional_margin_gate=True)
    altered = dict(factor, fractional_exact_score=.1500000001)
    assert experiment.compare_factors([factor], [altered], False)["fractional_exact_score"] == pytest.approx(1e-10)
    with pytest.raises(ValueError, match="signed short"):
        experiment.compare_factors([factor], [dict(altered, fractional_tracking_cfo_hz=0.)], False)
    with pytest.raises(ValueError, match="signed short"):
        experiment.compare_factors([factor], [altered], True)
    with pytest.raises(ValueError, match="Ordered candidates"):
        experiment.compare_factors([factor], [], False)
    with pytest.raises(ValueError, match="drift"):
        experiment.compare_factors([factor], [dict(factor, fractional_margin=.1501)], False)


def test_product_match_requires_roles_ordered_grid_and_pixel_identity():
    scope = dict.fromkeys(("chunk_index", "first_sequence", "encoded", "decoded", "windows", "member_sha256",
                          "raw_sha256", "index_sha256", "manifest_sha256"), 1)
    baseline = dict(verified_member_scopes=[scope]*13, ordered_owners={"c0": [["a", 1234, "conditional"]]},
                    outcome="complete", raw_identity="verified", detector_route="normal",
                    grid={"binding": "original", "elapsed_seconds": 0., "points": [[0., 1.]]},
                    path={"binding": "original", "stages": [1]}, publication_arms={}, evidence={"arms": {}},
                    figures=[dict(name="position", size=[50, 50], sha256="first", rgba_sha256="same")])
    candidate = deepcopy(baseline)
    candidate["grid"].update(binding="new run", elapsed_seconds=10.)
    candidate["figures"][0]["sha256"] = "different bytes"
    assert experiment.science(baseline, candidate)["media"][0]["identical_pixels"]
    candidate["figures"][0]["rgba_sha256"] = "different pixels"
    with pytest.raises(ValueError, match="decoded pixels"):
        experiment.science(baseline, candidate)
    candidate["ordered_owners"]["c0"][0][-1] = "held_out"
    with pytest.raises(ValueError, match="ordered_owners"):
        experiment.science(baseline, candidate)


def test_sealed_normal_publication_and_short_score_deltas():
    receipt = experiment.PROTOCOL.parent / "measurements" / "short-shared-phase-0016.json.gz"
    value = json.loads(gzip.decompress(receipt.read_bytes()))
    control, candidate = (value["result"][role] for role in ("historical_control", "candidate"))
    assert value["prelaunch"]["numeric_children"] == 0
    assert value["trial"]["watch.json"]["attempts"] == 1
    assert candidate["numeric_process"]["exit_code"] == 0
    assert experiment.science(control, candidate) == value["result"]["science"]
    assert value["result"]["packet"]["lanes"] == {"anchor": 186, "short": 1240}
    assert len(value["changed_short_rows"]) == value["result"]["packet"]["changed_factor_rows"]["short"] == 407
    for index, name in enumerate(value["short_score_columns"]):
        drift = max(abs(row["baseline"][index] - row["trial"][index]) for row in value["changed_short_rows"])
        assert drift == value["result"]["packet"]["score_drift"][name]
