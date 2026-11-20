from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.native_geometry_trial import (
    _manifest,
    compare_ranked,
    ranked_candidate,
)


def _candidate():
    return dict(
        epoch=13332,
        acquired_cfo_hz=300_000.0,
        tracking_cfo_hz=300_123.0,
        exact_score=0.05,
        control_score=0.02,
        margin=0.03,
        fractional_epoch=dict(
            status="complete",
            offset_samples=-0.1,
            exact_score=0.075,
            control_score=0.05,
            margin=0.025,
            residual_cfo_hz=122.0,
            tracking_cfo_hz=300_122.0,
        ),
    )


def test_rank_tolerances_preserve_gates_status_and_count():
    reference = ranked_candidate(0, _candidate())
    close = dict(reference, tracking_cfo_hz=300_123.0000005)
    assert compare_ranked([reference], [close])["equal_within_tolerance"]
    assert not compare_ranked([reference], [])["equal_within_tolerance"]
    different = dict(close, fractional_margin=0.025 - 1e-12, epoch_sample=0)
    result = compare_ranked([reference], [different])
    assert result["mismatches"] == {
        "epoch_sample": [[0, 13332, 0]],
        "passed_fractional_margin_gate": [[0, True, False]],
    }
    different = dict(close, fractional_epoch_status="unbracketed", fractional_tracking_cfo_hz=None)
    fields = compare_ranked([reference], [different])["mismatches"]
    assert set(fields) == {"fractional_epoch_status", "fractional_tracking_cfo_hz"}


def test_manifest_rejects_a_changed_iq_digest(tmp_path):
    window = SimpleNamespace(samples=np.zeros((200_000, 2, 2), dtype="<i2"), iq_sha256="changed")
    template = np.ones(13_333, dtype="<c16")
    geometry = dict(receiver_centers_hz=(10, 20), residual_bounds_hz=(-800_000, 800_000))
    with pytest.raises(ValueError, match="authenticated CI16 bytes"):
        _manifest(tmp_path, [window], [geometry], template, template)
