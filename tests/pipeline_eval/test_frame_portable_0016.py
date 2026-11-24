from pathlib import Path

import pytest

from reports.ALGO08.v3.frame_portable_0016 import candidate_command, eligible_pair


def test_combined_command_preserves_recording_and_detached_custody(tmp_path):
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
