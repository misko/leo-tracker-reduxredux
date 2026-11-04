import pytest
from check_algo07v3_track_preparation import deny_legacy


@pytest.mark.parametrize(('event', 'args'), [
    ('subprocess.Popen', ('worker',)),
    ('import', ('algo03_shadow_worker',)),
    ('import', ('leo.storage.fast_graph_position_v5',)),
    ('open', ('/opt/leo-fast-graph/old/tools/worker.py',)),
])
def test_candidate_cannot_access_historical_engines(event, args):
    with pytest.raises(RuntimeError):
        deny_legacy(event, args)


@pytest.mark.parametrize(('event', 'args'), [
    ('import', ('leo.analysis.localization_v3.tracks',)),
    ('import', ('numpy',)),
    ('open', ('/private/native-input.json',)),
    ('open', (4,)),
])
def test_pure_components_and_native_files_are_allowed(event, args):
    deny_legacy(event, args)
