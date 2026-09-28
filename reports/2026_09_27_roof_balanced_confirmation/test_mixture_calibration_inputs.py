from dataclasses import replace
from types import SimpleNamespace

import numpy as np

import mixture_calibration_inputs as inputs
import mixture_reception_core as core


def fixture():
    rows = (
        inputs.JoinedRow("s", "t", "a", "rx0", "1:lower", "1", 1., True, .2,
                         np.array([-.5, .5])),
        inputs.JoinedRow("s", "t", "b", "rx1", "1:lower", "1", 2., False, 0.,
                         np.array([100., 200.])),
    )
    return (inputs.JoinedTrack("s", "t", (10, 20),
                               np.log(np.array([.25, .75])), rows),)


def test_schema_ratio_scalers_use_matched_rows_only():
    schema = inputs.fit_schema(fixture())
    assert schema.ratio_east_mean == .25
    assert schema.ratio_east_scale == 1.
    assert schema.detection_east_mean != schema.ratio_east_mean


def test_arm_tensors_share_nuisance_and_mean_is_candidate_invariant():
    tracks = fixture(); schema = inputs.fit_schema(tracks)
    m0, _, _ = inputs.build_arm(tracks, schema, "M0", core)
    mean, _, _ = inputs.build_arm(tracks, schema, "mean", core)
    mixture, _, _ = inputs.build_arm(tracks, schema, "mixture", core)
    assert np.array_equal(m0[0].detection_design[0], m0[0].detection_design[1])
    assert np.array_equal(mean[0].detection_design[0], mean[0].detection_design[1])
    assert not np.array_equal(mixture[0].detection_design[0],
                              mixture[0].detection_design[1])
    assert np.array_equal(mean[0].detection_design[..., :-1],
                          mixture[0].detection_design[..., :-1])


def test_outcome_perturbation_does_not_change_structural_signature():
    tracks = fixture()
    changed_row = replace(tracks[0].rows[0], matched=False, log_ratio=999.)
    changed = (replace(tracks[0], rows=(changed_row, tracks[0].rows[1])),)
    assert inputs.structural_signature(tracks) == inputs.structural_signature(changed)


def test_real_join_has_frozen_dimensions_candidates_and_weights():
    tracks, receipt = inputs.load_joined()
    assert len(tracks) == receipt["tracks"] == 344
    assert sum(len(track.rows) for track in tracks) == receipt["rows"] == 6378
    assert len(receipt["excluded_track_keys"]) == 10
    assert all(len(track.candidate_ids) == 3 for track in tracks)
    assert max(abs(inputs._logsumexp(track.log_weights)) for track in tracks) < 1e-10
