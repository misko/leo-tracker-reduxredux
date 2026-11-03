"""Apply the historical T1-AT v1 association engine to new frozen scan inputs.

Reuse each scan's existing orbit-blind refinement and converged calibration.
Regenerate timing candidates with one absolute shift per satellite, then run
the exact historical top-only greedy/replacement implementation in both RF arms.
No position search, recalibration, new IQ acquisition, or alternate-candidate use.
"""
import argparse
import json
import math
import signal
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE.parent / '2026_10_04_ds13_18_scan_benchmark'
LEGACY = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
sys.path.insert(0, str(BENCHMARK))
from discovery import FoldCalibration
from numeric_data import view
from cohort import digest


def absolute_parameters(parameters, indices, timing):
    if not np.isfinite(timing) or abs(timing) > 20:
        raise ValueError('Absolute timing must be within +/-20 seconds')
    trial = np.asarray(parameters).copy()
    trial[6 + np.asarray(indices, dtype=int)] = timing
    return trial


class TopAbsoluteCalibration(FoldCalibration):
    def __init__(self, directory):
        super().__init__(directory, permit_warning=False)
        mask = self.data.top_mask.copy()
        self.data = view(self.data, mask)
        self.data.top_mask = np.ones(len(self.data.times), dtype=bool)
        self.inverse = self.inverse[mask]
        self.d = self.data  # Historical discovery adapter port.
        self.baseline = {arm: [] for arm in ('fitted-c', 'zero-c')}
        assert len(set(self.d.group)) == len(self.d.times)
        for path in (Path(__file__), BENCHMARK/'discovery.py', LEGACY/'greedy_pool_two_scans.py',
                     LEGACY/'greedy_restart_scan.py', LEGACY/'penalty_replace_search.py',
                     HERE.parent/'2026_10_03_ds13_coverage_goal/adaptive_discovery.py'):
            self.sources[str(path)] = digest(path.read_bytes())

    def predict(self, arm, ids, timing):
        shape = (self.group_count, len(ids))
        pred, visible, rate = np.empty(shape), np.empty(shape, bool), np.empty(shape)
        for destination, part, models in self.parts:
            parameters, unused_fold_reference, correction = models[arm]
            trial = absolute_parameters(parameters, ids, timing)
            rows = np.repeat(np.arange(len(part.times)), len(ids))
            satellites = np.tile(ids, len(part.times))
            p, v, j = self.predictor(part, trial, rows, satellites)
            pred[destination] = p.reshape(len(part.times), -1) + correction[:, None]
            visible[destination] = v.reshape(len(part.times), -1)
            rate[destination] = j.tau.reshape(len(part.times), -1)
        return pred[self.inverse], visible[self.inverse], rate[self.inverse]


def run(directory, label, output):
    sys.path.insert(0, str(LEGACY))
    import greedy_pool_two_scans as historical
    sys.path.insert(0, str(historical.OLD))
    from greedy_restart_scan import compile_mode
    from penalty_replace_search import Search
    cal = TopAbsoluteCalibration(directory)
    d = cal.data
    signature = dict(baseline='t1_at_v1', scan=label, session_id=d.session_id,
                     scope=__doc__, observations='highest refined margin per receiver/channel/probe',
                     timing='one absolute shift per satellite; no fold timing reference',
                     calibration='scan-specific saved five-fold receiver/RF calibration; not the original A/B numerical fits',
                     tle=json.loads((directory/'orbit-bank/receipt.json').read_text())['signature']['tle'],
                     sources=cal.sources, penalty=10, tolerance_hz=600, maximum_replacement_passes=3)
    output.mkdir(parents=True, exist_ok=False)
    (output/'input-receipt.json').write_text(json.dumps(signature, indent=2))
    historical.FrozenCalibration = lambda: cal
    historical.OUT = output
    historical.SCAN = label
    historical.SESSIONS[label] = d.session_id
    historical.discover()
    pool_path = output/'candidate-pool.json'
    pool = json.loads(pool_path.read_text())
    # Correct the historical module's generic common-relative description;
    # the injected predictor above evaluates absolute timing, as for old B.
    pool.update(scope=__doc__, timing_convention=signature['timing'], baseline='t1_at_v1')
    pool_path.write_text(json.dumps(pool))
    assert pool['original_rows'] == d.original_rows.tolist()
    assert [(m['catalog_number'], m['offset_s']) for m in pool['arms']['fitted-c']] == [
        (m['catalog_number'], m['offset_s']) for m in pool['arms']['zero-c']]
    summaries = []
    for arm in ('fitted-c', 'zero-c'):
        modes = [compile_mode(m, d.receiver, d.channel) for m in pool['arms'][arm]]
        result = Search(modes, d.group, d.times).run(3)
        # Independently recompute every selected mode's residuals from orbits.
        for selected in result['final']['selected']:
            m = pool['arms'][arm][selected['mode_index']]
            assigned = [a for a in result['final']['assignments'] if a['catalog_number'] == m['catalog_number']]
            ix = np.array([a['row_index'] for a in assigned], dtype=int)
            errors, visible, _ = cal.residual(arm, m['satellite_index'], m['offset_s'])
            assert np.all(visible[ix]) and np.all(abs(errors[ix]) <= 600)
            assert np.allclose(errors[ix], [a['residual_hz'] for a in assigned], atol=1e-6, rtol=0)
        for stage in ('initial', 'final'):
            r = result[stage]
            assert len({int(d.group[a['row_index']]) for a in r['assignments']}) == r['assigned']
            for a in r['assignments']:
                a['row_index'] = int(d.original_rows[a['row_index']])
            r.update(denominator=len(d.times), coverage=r['assigned']/len(d.times),
                     unassigned=len(d.times)-r['assigned'])
        final = result['final']
        summary = dict(scan=label, arm=arm, **{k:final[k] for k in ('assigned','denominator','coverage','unassigned','satellites','objective')},
                       greedy_assigned=result['initial']['assigned'],
                       rms_hz=math.sqrt(sum(a['residual_hz']**2 for a in final['assignments'])/final['assigned']) if final['assigned'] else None,
                       accepted_replacements=sum(p['accepted'] for p in result['passes']),
                       residual_reconstruction_verified=True, elapsed_s=result['elapsed_s'])
        result.update(input_receipt=signature, source_sha256=digest(pool_path.read_bytes()), summary=summary)
        (output/f'{arm}.json').write_text(json.dumps(result, indent=2))
        summaries.append(summary)
        print('RESULT', json.dumps(summary), flush=True)
    (output/'summary.json').write_text(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--label', required=True, choices=['N01', 'N02'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *_: sys.exit('Bounded 15-minute run limit reached; partial artifacts retained'))
    signal.alarm(900)
    run(args.directory, args.label, args.output)
