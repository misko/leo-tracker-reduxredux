from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('trained,requested', [('scalar', 'vector'), ('vector', 'scalar'), (None, 'vector')])
def test_reject_mismatched_vector_training(tmp_path, trained, requested):
    (tmp_path / 'score.gcda').write_bytes(b'profile-placeholder')
    (tmp_path / 'session-mode.txt').write_text('immutable\n')
    if trained is not None:
        (tmp_path / 'vector-mode.txt').write_text(trained + '\n')
    script = Path(__file__).with_name('build_arm_score_pgo.sh')
    result = subprocess.run(['bash', str(script), 'use', str(tmp_path),
                             str(tmp_path), 'immutable', requested], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'training vector mode differs' in result.stderr


def test_vector_requires_immutable_session(tmp_path):
    script = Path(__file__).with_name('build_arm_score_pgo.sh')
    result = subprocess.run(['bash', str(script), 'generate', str(tmp_path),
                             str(tmp_path), 'mutable', 'vector'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'vector mode requires immutable session' in result.stderr
    assert not (tmp_path / 'score.o').exists()


def test_reject_changed_cache_capacity(tmp_path):
    (tmp_path / 'score.gcda').write_bytes(b'profile-placeholder')
    (tmp_path / 'session-mode.txt').write_text('immutable\n')
    (tmp_path / 'vector-mode.txt').write_text('vector\n')
    (tmp_path / 'bank-mib.txt').write_text('64\n')
    result = subprocess.run(['bash', str(Path(__file__).with_name('build_arm_score_pgo.sh')),
                             'use', str(tmp_path), str(tmp_path), 'immutable', 'vector', '128'],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert 'training endpoint bank differs' in result.stderr
