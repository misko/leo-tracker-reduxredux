from math import remainder
from os import O_RDONLY, O_RDWR, major, minor
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import empty_lane_directed_replay as replay
from reports.ALGO08.v3 import empty_lane_directed_watch as watch


def test_epoch_converts_large_hardware_counter_before_float_reduction():
    counter = 9_000_000_000_000_001
    relative = 12_345.75
    factor = dict(integer_epoch_sample=12_346, fractional_epoch_offset_samples=-.25)
    phase = replay.arrival_phase(counter, factor)
    assert replay.phase_epoch(counter, phase) == pytest.approx(relative, abs=2e-12)
    base = (3 * counter % 40_000) / 3
    native = replay.phase_epoch(counter, (base + 13_333.2) % replay.PERIOD)
    assert native == pytest.approx(.2, abs=2e-12)
    assert remainder(native - 13_333.2, replay.PERIOD) == pytest.approx(1/3)
    with pytest.raises(ValueError):
        replay.phase_epoch(counter, float('nan'))


def test_raw_key_requires_exact_full_aperture_and_original_tuned_rf():
    window = SimpleNamespace(sequence=12, sample_rate_hz=10_000_000,
                             samples=np.empty((200_000, 2, 2), dtype='<i2'),
                             target=dict(lnb_lo_hz=1000, rf_center_hz=2002, edge='lower', channel=3),
                             acquisition=dict(global_visit=12, sample_start=987, actual_if_center_hz=1003))
    assert replay.signed_visit(window, [987, 'lower', 3, 2003]) == -1
    with pytest.raises(ValueError):
        replay.signed_visit(window, [987, 'lower', 3, 2002])
    window.samples = window.samples[:80_000]
    with pytest.raises(ValueError):
        replay.signed_visit(window, [987, 'lower', 3, 2003])


def test_projection_uses_empty_short_antenna_and_hardware_order():
    def lane(radio):
        return dict(short=True, factor=None, counter=7000, radio=radio,
                    row=dict(visit_index=4, payload_start_sample=800_000, probe_start_ms=0, probe_index=0,
                             receiver_id=radio, edge='lower',
                             channel=3, actual_rf_hz=100))
    lanes = {'b': lane(1), 'a': lane(0)}
    queries = {key: dict(centers_hz=[-90], phase=dict.fromkeys(replay.arrival.PHASES, 7200.5)) for key in lanes}
    _, rows = replay.project(lanes, queries)
    assert [r['id'] for r in rows] == ['a', 'b']
    assert rows[0]['epochs']['interpolated'] == 200.5
    lanes['b']['factor'] = True
    with pytest.raises(ValueError):
        replay.project(lanes, queries)


def test_one_seed_phase_controls_share_signed_center_and_native_budget():
    row = dict(radio=1, hz=-92, epochs=dict(zip(replay.arrival.PHASES, (1., 5., 3500.))))
    expected = []
    stages = SimpleNamespace(gates=1, cancellations=0, refine_ns=0, _fields_=[('gates', int)])

    def timed(samples, radio, center, seed, mode):
        expected.append((samples, radio, center, seed, mode))
        return (), 5, 8, stages

    args = None, 31, row, SimpleNamespace(timed=timed), lambda epoch, hz: (epoch, hz)
    result = replay.report_pulse(*args)
    assert list(result) == list(replay.arrival.PHASES)
    assert expected == [(None, 1, 31, [(epoch, -92)], 'decode') for epoch in (1., 5., 3500.)]
    stages.cancellations = 1
    with pytest.raises(ValueError):
        replay.report_pulse(*args)


def test_original_match_no_carrier_alias_and_stage_is_readonly():
    reference = {replay.arrival.HERTZ: -1000, 'integer_epoch_sample': 13_332,
                 'fractional_epoch_offset_samples': 1.2}
    assert replay.matches(123, [0, 0, 0.3, -1010, 2., .1], reference)
    assert not replay.matches(123, [0, 0, 0.3, 226272, 2., .1], reference)
    path = str(replay.prefix.STAGE / 'iq-000000.ci16.zst')
    replay.forbid_source('open', (path, 'rb', O_RDONLY), allowed={path})
    for name, flags, allowed in ((path, O_RDWR, {path}), (path, O_RDONLY, ()),
                                 ('/srv/bulk/other', O_RDONLY, ()), ('/tmp/installed/answer', O_RDONLY, ())):
        with pytest.raises(ValueError):
            replay.forbid_source('open', (name, 'rb', flags), allowed=allowed)


def test_passive_admission_requires_fresh_sleep_quiet_and_free_lock(tmp_path):
    quiet = {'original': dict(full_avg10=4., in_flight=0), 'output': dict(full_avg10=4., in_flight=2)}
    assert watch.eligible(dict(age_s=0.5), True, quiet, False) is None
    assert watch.eligible(dict(age_s=4.), True, quiet, False) == 'no-fresh-field-sleep'
    assert watch.eligible(dict(age_s=0.5), False, quiet, False) == 'no-fresh-field-sleep'
    assert watch.eligible(dict(age_s=0.5), True, quiet, True) == 'shared-lease-present'
    quiet['output']['in_flight'] += 1
    assert watch.eligible(dict(age_s=0.5), True, quiet, False) == 'storage-pressure'
    lease = tmp_path / 'lease'
    lease.touch()
    stat = lease.stat()
    key = f'{major(stat.st_dev):x}:{minor(stat.st_dev):x}:{stat.st_ino}'
    assert watch.lock_present(lease, f'17: FLOCK ADVISORY WRITE 1290 {key} 0 EOF\n')
    assert not watch.lock_present(lease, f'18: POSIX ADVISORY WRITE 1291 00:00:{stat.st_ino} 0 EOF\n')
