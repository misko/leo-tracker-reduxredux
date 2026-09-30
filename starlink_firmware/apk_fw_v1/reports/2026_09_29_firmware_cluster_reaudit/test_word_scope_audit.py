from word_scope_audit import state_counts


def test_conflicting_windows_do_not_become_a_consistent_frame_transition():
    rows = [dict(frame=f, known_phase=s) for f, s in [(1, 2), (1, 3), (3, 4), (3, 4)]]
    result = state_counts(rows)
    assert result["multiwindow_frames"] == 2
    assert result["multiwindow_single_state"] == 1
    assert result["two_frame_tracks"] == 0
