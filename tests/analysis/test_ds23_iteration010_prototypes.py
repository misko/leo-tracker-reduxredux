import diagnose_ds23_iteration010_tracks as tracks
import probe_ds23_iteration010_paths as paths


def test_following_diagnostics_bind_the_current_batch_without_inference_changes():
    tracks.configure()
    assert tracks.diagnostic.runner is tracks.runner
    assert tracks.diagnostic.OUT==tracks.OUT
    assert tracks.OUT.parent==tracks.runner.RAW


def test_temporal_driver_uses_current_parent_and_existing_screen_rules():
    paths.configure()
    assert paths.paths.runner is paths.runner
    assert paths.paths.OUT==paths.OUT
    assert paths.paths.METHODS=={'independent':0.,'persistent5s':5.}


def test_whole_diagnostic_keeps_partial_source_out_of_nomination_only():
    ranking=[dict(points=12,original_points=30),dict(points=18,original_points=18),dict(points=7,original_points=7)]
    selected=tracks.diagnostic.choose_targets(ranking)
    assert selected==[ranking[1]]
    assert len(ranking)==3
