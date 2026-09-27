from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_local import LocalConfirmedEngine
from test_early_confirmed import Port, fixtures


class LocalPort(Port):
    def guided(self, raw, **kwargs):
        point = super().guided(raw, **kwargs)
        epoch = kwargs['predicted_local_epoch_sample']
        return replace(point, margin={316.: .04, 317.: .02, 318.: .9}[epoch],
                       status=2 if epoch == 318 else 0)


def test_search_recovers_adjacent_sample_but_rejects_wrong_frequency():
    port = LocalPort()
    engine = LocalConfirmedEngine(Port(), port)
    point = fixtures.Observation(0, 0, 0, 317.4, fitted=False)
    result = engine._confirm(None, point)
    assert result.local_epoch_sample == 316
    assert not result.fitted and engine.confirmation_calls == 3
    assert {c['scoring_cfo_hz'] for c in port.calls} == {point.acquired_cfo_hz}
    assert {c['expected_physical_cfo_hz'] for c in port.calls} == {point.tracking_cfo_hz}


def test_tie_prefers_center_without_teaching_guided_drift():
    engine = LocalConfirmedEngine(Port(), Port())
    point = fixtures.Observation(0, 0, 0, 317.4, fitted=False)
    assert engine._confirm(None, point).local_epoch_sample == 317
