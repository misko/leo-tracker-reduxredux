"""Scheduling probes must leave arithmetic and unrelated source untouched."""

from pathlib import Path

import pytest
from build_native_schedule_probe import transform

SOURCE = Path(__file__).resolve().parents[2] / 'src/leo/analysis/starlink/_native_acquisition.c'


def test_only_target_tuning_changes():
    original = SOURCE.read_text()
    changed = transform(original)
    assert changed.replace('tune=arrowlake', 'tune=haswell') == original
    assert changed.count('target("avx2,fma,tune=arrowlake")') == 2


@pytest.mark.parametrize('source', ['', SOURCE.read_text().replace('tune=haswell', 'tune=native'),
                                    SOURCE.read_text() * 2])
def test_unknown_layout_rejected(source):
    with pytest.raises(ValueError, match='Unknown native target layout'):
        transform(source)
