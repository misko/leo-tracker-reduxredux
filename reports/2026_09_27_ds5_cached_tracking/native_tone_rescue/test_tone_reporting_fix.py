from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_reporting_fix as adapter


def test_reporting_fix_only_omits_absent_comparator_and_preserves_rows(monkeypatch):
    rows = [{'raw_rescue_result': None, 'tone_rescue_result': {'value': 3}},
            {'raw_rescue_result': {'value': 2}, 'tone_rescue_result': {'value': 4}}]
    before = deepcopy(rows)
    captured = []
    monkeypatch.setattr(adapter, 'ORIGINAL_SUMMARIZE',
                        lambda stage, values: captured.append((stage, values)) or {})
    monkeypatch.setattr(adapter, 'digest', lambda _: 'pinned')
    result = adapter.summarize('diagnostic', rows)
    assert rows == before
    assert captured == [('diagnostic', [
        {'tone_rescue_result': {'value': 3}}, before[1]])]
    assert result['reporting_adapter']['lock_sha256'] == 'pinned'
