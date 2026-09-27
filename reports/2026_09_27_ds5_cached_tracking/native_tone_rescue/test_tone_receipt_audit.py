from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_receipts import associates


def pair(receiver=0, epoch=317., cfo=1000.):
    return {'receiver': receiver, 'first': {'dwell_epoch_sample': epoch, 'tracking_cfo_hz': cfo},
            'second': {'dwell_epoch_sample': epoch+50000, 'tracking_cfo_hz': cfo}}


def test_audit_association_requires_both_members_and_receiver():
    reference = pair()
    assert associates(pair(epoch=322., cfo=9000.), reference, 2500000)
    assert not associates(pair(epoch=322.01), reference, 2500000)
    assert not associates(pair(cfo=9000.01), reference, 2500000)
    assert not associates(pair(receiver=1), reference, 2500000)
    altered = pair()
    altered['second']['tracking_cfo_hz'] = 9000.01
    assert not associates(altered, reference, 2500000)
    assert not associates(None, reference, 2500000)


def test_audit_association_uses_physical_frame_period():
    assert associates(pair(epoch=317.+2500000/750), pair(), 2500000)
