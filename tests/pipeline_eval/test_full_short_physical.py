from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module


def test_recipe_is_the_measured_full_coverage_identity(research):
    raw = research("full_short_raw")
    assert canonical_digest(raw.recipe()) == "sha256:" + raw.RECIPE_SHA
    assert raw.recipe()["rule"] == ["full"] + ["short_primary"] * 7


def test_only_bilateral_unique_early_withhold_passes_gate(research):
    trial = research("full_short_physical")
    result = dict(status="withheld", reason="both_receivers_support_far_exterior", attempts=[], ranks=[], science={})
    proof = dict(complete=True, would_withhold=True, receivers={"1": {"unique_exterior": True}, "2": {"unique_exterior": True}})
    handoff = dict(catalogue_handoff=1)
    assert trial.verify_gate(result, [dict(result=proof)], handoff)
    assert not trial.verify_gate(dict(result, attempts=[{}]), [dict(result=proof)], handoff)
    assert not trial.verify_gate(result, [dict(result=dict(proof, receivers={"1": {"unique_exterior": True}}))], handoff)


def test_recipe_pin_binds_raw_acquire_then_restores_asset_pin(research):
    raw = research("full_short_raw")
    audit = {}
    scan = SimpleNamespace(PINS={"cancellation-factors.so": raw.mixed.INSTALLED_SHA})

    class Source:
        def windows(self):
            yield SimpleNamespace(iq_sha256="iq-digest")

    def acquire(_session, inventory_sha, inventory, _assets):
        hashes = [w.iq_sha256 for w in scan.FastSegmentSource().windows()]
        authority = canonical_digest([inventory_sha, hashes])
        probes = [dict(candidates=["verified"]), dict(candidates=[])]
        assert scan.PINS["cancellation-factors.so"] == raw.RECIPE_SHA
        analysis = canonical_digest(["cancellation", authority, raw.RECIPE_SHA, probes])
        return dict(source=dict(raw_recording_authority_digest=authority, analysis_manifest_sha256=analysis, probes=probes),
                    provenance=dict(detector_sha256="sha256:" + raw.RECIPE_SHA))

    scan.acquire, scan.FastSegmentSource = acquire, Source
    runner = SimpleNamespace(receipt=lambda: dict(native_calls={"full": 2}))
    with raw.observe_acquisition(scan, runner, raw.RECIPE_SHA, audit):
        scan.acquire("session", "inventory", {"window_count": 1}, None)
        assert scan.PINS["cancellation-factors.so"] == raw.RECIPE_SHA
    assert scan.PINS["cancellation-factors.so"] == raw.mixed.INSTALLED_SHA
    assert (audit["issued"], audit["selected"], audit["native"]["native_calls"]) == (1, 1, {"full": 2})


def test_publication_reconstructs_all_eighth_anchors_from_stereo_probes(research):
    trial = research("full_short_physical_score")
    probes = []
    for j in range(9):
        for lane in (0, 1):
            rank = 1 if j in (0, 8) else 0
            probes.append(dict(visit_index=j, valid_start_counter=j*200_000, edge="lower", channel=1,
                               actual_rf_hz=11e9, receiver_id=lane,
                               candidates=[dict(candidate_rank=rank, passed_fractional_margin_gate=True)]))
    report = trial.classified(probes)
    assert report == dict(visits={"full": 2, "short_primary": 7}, native_calls={"full": 4, "short_primary": 14},
                          factors={"full": 4, "short_primary": 14})
    probes[2]["candidates"][0]["candidate_rank"] = 1
    with pytest.raises(ValueError, match="emitted a residual"):
        trial.classified(probes)
