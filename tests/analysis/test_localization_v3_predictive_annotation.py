from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import predictive_annotation as annotation


def test_insufficient_distinct_geometry_stops_before_any_frequency_fit(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Insufficient timestamp support must skip RF fits')
    monkeypatch.setattr(annotation, 'fit_training', forbidden)
    target = dict(track_id='target', track_index=0, current_large=True)
    track = dict(key='short', times=np.arange(4.), values=np.arange(4.))
    p = SimpleNamespace(members=[], flat_times=np.arange(300.))
    d = dict(scan=SimpleNamespace(tracks=[track]), problems={'c0':(p,np.zeros(2))})
    result = annotation.annotate(d, dict(tracks=[target]), 'target')
    assert result['result']['geometry_only_early_exit']
    assert result['result']['annotation']['status'] == 'insufficient_partitions'
    assert result['result']['no_accepted_associations']
    assert not result['nominations'] and not result['attempts']
