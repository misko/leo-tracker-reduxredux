"""Nominal support-aware sensitivity using the frozen scan-0 pilot measurements."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'norad65512_position'
spec = importlib.util.spec_from_file_location('support_position_prior', PREVIOUS/'run.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
prior.HERE = HERE
fast, _, _ = prior.dependencies()
OriginalStationary = fast.Stationary
original_patch = prior.patch_documents


class SupportStationary(OriginalStationary):
    def prediction(self, track, x):
        shifts = track.get('nominal_support_shift_s')
        if shifts is None or not np.any(shifts):
            return super().prediction(track, x)
        times = x[2] + shifts
        if np.any(times < self.taus[0]) or np.any(times > self.taus[-1]):
            raise ValueError('measurement time outside frozen orbit bank')
        hi = np.clip(np.searchsorted(self.taus, times, side='right'), 1, len(self.taus)-1)
        lo = hi-1
        weight = ((times-self.taus[lo])/(self.taus[hi]-self.taus[lo]))[None, :, None]
        observations = np.arange(len(times))
        def interpolate(array):
            return array[:, lo, observations]*(1-weight) + array[:, hi, observations]*weight
        pos = interpolate(track['candidate_position_km'])
        vel = interpolate(track['candidate_velocity_km_s'])
        rec, up = fast.baseline.site(*self.coordinates(x))
        unit = pos-rec
        unit /= np.linalg.norm(unit, axis=-1)[..., None]
        prediction = -fast.baseline.REFERENCE_RF_HZ/fast.baseline.LIGHT_KM_S*np.sum(unit*vel, axis=-1)
        return prediction, np.any((unit @ up)[:, track['mask']] >= 0, axis=1)


def patch_documents(documents, corrections):
    patched = original_patch(documents, corrections)
    tracks = {t['track_id']: t for d in patched for t in d['tracks']}
    for track in tracks.values():
        track['nominal_support_shift_s'] = np.zeros(len(track['y']))
    for row in corrections:
        shift = row['nominal_support_shift_s']
        assert np.isfinite(shift) and -.005 < shift < 0
        tracks[row['track_id']]['nominal_support_shift_s'][row['observation_index']] = shift
    for track in tracks.values():
        assert not np.any(track['nominal_support_shift_s'][~track['mask']])
    return patched


fast.Stationary = SupportStationary
prior.patch_documents = patch_documents
# A 5-ms guard avoids extrapolating the unchanged +/-5-second orbit bank.
# Existing control and all original pilot endpoints are strictly inside it.
prior.BOUNDS = [(-12., 12.), (-12., 12.), (-4.995, 4.995)]


def prepare():
    plan = prior.read(PREVIOUS/'plan.json')
    prior.context(plan)
    support_path = PREVIOUS/'support_audit.json'
    support = prior.read(support_path)
    for path, expected in support['sources'].items():
        assert prior.digest(path) == expected, path
    rows = {(r['track_id'], r['observation_index']): r for r in support['rows']}
    assert len(rows) == len(support['rows']) == 111
    for arm, corrections in plan['corrections'].items():
        assert {(r['track_id'], r['observation_index']) for r in corrections} == set(rows)
        for row in corrections:
            row['nominal_support_shift_s'] = rows[row['track_id'], row['observation_index']]['arms'][arm]['pilot_minus_glrt_center_s']
    paths = [PREVIOUS/'plan.json', support_path, Path(__file__), HERE/'test_run.py', HERE/'PROTOCOL.md']
    plan['sources'].update(support['sources'])
    plan['sources'].update({str(p): prior.digest(p) for p in paths})
    plan.update(schema='ds11-nominal-support-position/v1',
                effective_estimator_weighting_measured=False, bounds=prior.BOUNDS,
                measurement_time_policy='Geometric mean of eight-frame FFT support per pilot arm; target training rows only')
    documents, _, timing, harness = prior.context(plan)
    model = timing.TimingModel(documents, plan['config'], 'original')
    replay = prior.audited_endpoint(model, plan['control']['x'], True, harness)
    assert replay['qualified'] and abs(replay['score']-plan['control']['score']) < 1e-8
    for arm in prior.ARMS:
        patch_documents(documents, plan['corrections'][arm])
    prior.write(HERE/'plan.json', plan)
    print('Frozen 111 rows per arm, eight starts; original control replay passed.', flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'fit':
        prior.fit(int(sys.argv[2]))
    else:
        {'prepare': prepare, 'batch': prior.batch, 'assess': prior.assess}[sys.argv[1]]()
