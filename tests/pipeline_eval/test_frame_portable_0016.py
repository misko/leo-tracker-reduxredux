from pathlib import Path

import pytest

@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'reports/ALGO08/v3'))
    import frame_portable_0016
    import frame_portable_0016_score

    return frame_portable_0016, frame_portable_0016_score


def test_combined_command_preserves_recording_and_detached_custody(tmp_path, trial):
    candidate_command = trial[0].candidate_command
    class Portable:
        def arguments(self):
            return ['--portable-orbit-index', '/staged/orbits']

    prior = ['/usr/bin/timeout', '--kill-after=2s', '75s', '/known/python', '-IB', '/old/exact_named_raw.py',
             '--recording', '/same/recording', '--output', '/old/frames', '--cairo-six-sheets',
             '--visit-frame-custody', '/same/custody', '--visit-frame-custody-sha256', 'sha256:keep', '--history-risk-route']
    combined = candidate_command(prior, tmp_path, Portable())
    assert '--cairo-six-sheets' in prior and '--cairo-six-sheets' not in combined
    assert '--cairo-residual-layout' in combined and '--history-risk-route' in combined
    assert combined[combined.index('--portable-orbit-index')+1] == '/staged/orbits'
    assert combined[combined.index('--recording')+1] == '/same/recording'
    assert combined[combined.index('--visit-frame-custody')+1] == '/same/custody'
    assert Path(combined[combined.index('--output')+1]) == tmp_path/'candidate'
    with pytest.raises(ValueError, match='qualified'):
        candidate_command(prior + ['--strict-packed-eight'], tmp_path, Portable())


def test_first_use_charges_prior_producer_and_discloses_custody_separately(trial):
    costs = trial[1].price(16, 12, 11, 9, 1, 2, 5)
    assert costs['prepared'] == 10
    assert costs['prepared_with_custody'] == 12
    assert costs['first_use_portable_prepared_capture'] == 15
    assert costs['speedups']['named_ready'] == pytest.approx(1.6)
    assert costs['gap_to_1_6'] == 0
    assert costs['gap_with_custody_to_1_6'] == 2
