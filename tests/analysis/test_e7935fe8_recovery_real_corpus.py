from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.standard.analyzers import _pilot_detections
from leo.analysis.standard.runner import SingleReceiverIqReader
from leo.analysis.starlink.cfo_dealias import (
    default_cfo_dealias_config,
    default_replay_gate_v2,
    replay_observed_cfo_lifts_v2,
    select_final_trajectories_v2,
)
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.contracts.cfo_dealias import (
    CfoLiftReplayV1,
    DealiasedTrajectoryBankV2,
    LiftReplayTierV2,
)
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from leo.storage import PinnedLocalRoot, RecordingStore

_ROOT = Path("/srv/bulk/leo")
_SESSION = "cap-20260821T013440-8065b3e24a75"
_RUN = "capture-f82a8ff488fb4f77badd75f8de0ba664"
_SCOPE = "sha256:1bab4baa1e120ed113832058b298daede183438abb3970ae54414a5ef18b3b7d"
_BRANCH = "sha256:e7935fe88db67f1be3859c581ad0787175954bdc151c1c74ca6270d96583a37b"
_MANIFEST = "sha256:327228c6b4e04943692d97422ec97880c0e4dcb724148bbfe938d8fabb99545f"


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.mark.real_corpus
def test_e7935fe8_is_retained_as_one_display_candidate_but_never_as_correction() -> None:
    """Bounded exact-IQ regression for the reviewed 5d4d RX1 disappearance."""

    scientific = _ROOT / "analysis" / _SESSION / _RUN / "scientific" / "path-standard" / _SCOPE
    bank = DealiasedTrajectoryBankV2.model_validate(
        _read(scientific / "standard.dealiased-trajectory-bank.v2.json")
    )
    old = CfoLiftReplayV1.model_validate(_read(scientific / "standard.cfo-lift-replay.v1.json"))
    pilot = _read(scientific / "standard.pilot-scan.v3.json")
    branch = next(item for item in bank.branches if item.branch_id == _BRANCH)
    selected = next(item for item in branch.models if item.model_id == branch.selected_model_id)
    assert len(selected.observation_ids) == 82
    assert selected.polynomial_degree == 3
    assert selected.start_s == 8.0
    assert selected.end_s == 19.225
    assert selected.residual_rms_hz == pytest.approx(394.79640486141665)

    store = RecordingStore.open_pinned(PinnedLocalRoot(_ROOT))
    try:
        bundle = store.inspect(_SESSION)
        assert bundle.manifest_sha256 == _MANIFEST
        assert resolve_manifest_starlink_tuning(bundle.manifest)["stream-0"].edge.value == "lower"
        store.verify(bundle)
        source = store.reader(bundle, "stream-0", verify=True)
        replay = replay_observed_cfo_lifts_v2(
            SingleReceiverIqReader(source, 1),
            _pilot_detections(pilot),
            bank,
            replace(TrajectoryFeedbackConfig(), maximum_workers=12),
            edge=resolve_manifest_starlink_tuning(bundle.manifest)["stream-0"].edge,
            path_input_binding_digest=old.path_input_binding_digest,
            pilot_scan_digest=old.pilot_scan_digest,
            dealias_config=default_cfo_dealias_config(),
            gate_config=default_replay_gate_v2(),
        )
    finally:
        store.close()

    rows = {item.alias_index: item for item in replay.rows if item.branch_id == _BRANCH}
    assert rows[0].tier is LiftReplayTierV2.GEOMETRY_ONLY
    assert rows[0].evaluated_probe_count == 450
    assert rows[0].evaluated_block_count == 12
    assert rows[0].block_coverage_ratio == 1.0
    assert rows[0].harmful_block_count == 0
    assert rows[0].median_block_margin_delta == pytest.approx(-8.4995e-5, abs=5e-9)
    assert rows[0].median_block_corrected_margin == pytest.approx(0.003310, abs=5e-6)
    assert not rows[0].automatic_correction_eligible

    final = select_final_trajectories_v2(bank, replay, config=default_cfo_dealias_config())
    retained = [item for item in final.trajectories if item.branch_id == _BRANCH]
    assert len(retained) == 1
    assert retained[0].alias_index == 0
    assert retained[0].replay_tier is LiftReplayTierV2.GEOMETRY_ONLY
    assert not retained[0].automatic_correction_eligible
    assert retained[0].trajectory_id not in final.automatic_correction_trajectory_ids
