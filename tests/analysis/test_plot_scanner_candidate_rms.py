from tools.plot_scanner_candidate_rms import plot_rows


def test_plot_caps_candidates_without_resorting_on_heldout():
    candidates = [{"catalog_number": i, "heldout_rms_hz": 20 - i} for i in range(14)]
    track = {"fields": {"0": {"top_training": candidates}}}
    assert plot_rows(track) == candidates[:10]
    assert len(candidates) == 14


def test_short_archive_is_not_padded():
    candidates = [{"catalog_number": i} for i in range(5)]
    assert plot_rows({"fields": {"0": {"top_training": candidates}}}) == candidates
    assert plot_rows({"fields": {"0": {}}}) == []
