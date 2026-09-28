"""Read saved 08:50 diagnostics; no RF replay or production mutations."""
import hashlib
import json
from pathlib import Path
import numpy as np
from polynomial_core import fit_residual

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'2026_09_26_ds5_0850_diagnosis/results.json'


def main():
    data = json.loads(SOURCE.read_text())
    rows = []
    for site, tracks in data['alternatives'].items():
        for tid, candidates in tracks.items():
            track = data['target_tracks'][tid]
            mask = np.asarray(track['training_mask'], bool)
            for candidate in candidates:
                residual = np.asarray(candidate['residual_hz_at_training_map'])
                original_rms = float(np.sqrt(np.mean(residual[~mask]**2)))
                assert abs(original_rms-candidate['eval_rms_at_training_map_hz']) < 1e-7
                fits = [fit_residual(track['times_s'], residual, mask, degree) for degree in range(4)]
                rows.append({'site': site, 'track_id': tid, 'channel': track['channel'],
                    'receiver': track['receiver'], 'span_s': track['span_s'],
                    'satellite_id': candidate['candidate_id'],
                    'fixed_independent_timing_s': candidate['timing']['map_s'],
                    'original_robust_offset_evaluation_rms_hz': original_rms, 'fits': fits})
    out = {'session_id': data['session_id'], 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'core_sha256': hashlib.sha256((HERE/'polynomial_core.py').read_bytes()).hexdigest(),
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'evidence_sha256': data['evidence_sha256'], 'snapshot_digest': data['snapshot_digest'],
        'protocol': 'All eight previously diagnosed tracks, all saved candidates, all three independent fixed sites. '
            'Timing frozen at each candidate independent training MAP from earlier diagnostic; NOT shared timing. '
            'OLS polynomial degrees 0..3 fitted on original training observations; original evaluation masks reused. '
            'Degree zero re-centers the earlier robust offset by OLS for a consistent polynomial comparison. '
            'No candidate/degree selection or classifier is fitted. Unregularized flexibility stress test; '
            'retrospective, correlated observations, no verified identities or fresh validation.', 'rows': rows}
    (HERE/'results.json').write_text(json.dumps(out, indent=2)+'\n')
    for row in rows:
        if row['site'] == 'reference' and row['track_id'].startswith(('sha256:0b8ea715', 'sha256:98dbb677')):
            print(row['track_id'][7:15], row['satellite_id'], row['fixed_independent_timing_s'],
                  [round(f['evaluation_rms_hz'], 1) for f in row['fits']], flush=True)
    print('candidate-track-site combinations:', len(rows))


if __name__ == '__main__':
    main()
