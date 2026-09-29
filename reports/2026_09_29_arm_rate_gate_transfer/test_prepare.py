import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def test_sealed_transfer_panel_is_balanced_and_frontloaded():
    panel=json.loads((HERE/'selection.json').read_text())
    assert set(panel['panels'])=={'DS8','DS9'}
    for value in panel['panels'].values():
        selected=value['selected'];assert len(selected)==32
        assert all(row['rate_hz']==2500000 for row in selected[:8])
        assert {(row['rate_hz'],row['target']['edge']) for row in selected}=={
            (rate,edge) for rate in (2500000,5000000,7500000,10000000) for edge in ('lower','upper')}
        assert len({(row['session_id'],row['visit_index']) for row in selected})==32
