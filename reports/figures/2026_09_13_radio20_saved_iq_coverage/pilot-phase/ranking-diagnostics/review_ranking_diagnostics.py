"""Review ranking selections, source provenance and frozen C worker outputs."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
reviewer = BASE / 'review_missed_candidate_replay.py'
ns = {'__file__': str(reviewer)}
exec(compile(reviewer.read_text().split('\nmanifest=json.loads', 1)[0], str(reviewer), 'exec'), ns)
proposals = json.loads((BASE / 'expanded-proposal-ranking-v1.json').read_text())['cases']
refs = np.fromfile(BASE / 'direct-references.ci16', dtype='<i2').reshape(4, 3300, 4).astype(float)
ref = refs[0, :, 0] + 1j * refs[0, :, 1]
energy = np.vdot(ref, ref).real
results = []
mutations = 0
rank_checks = 0
for mode in ('timing-aware', 'repeat-phase'):
    root = BASE / f'{mode}-ranking-v1'
    manifest = json.loads((root / 'result.json').read_text())
    for case, proposal_case in zip(manifest['cases'], proposals, strict=True):
        label = f"{case['label']}-{case['number']}"
        assert (case['label'], case['number']) == (proposal_case['label'], proposal_case['number'])
        if mode == 'repeat-phase':
            ns['ROOT'] = root
            path = root / label / 'iq.ci16'
            source = BASE / 'paced-original-seed-input-v1' / f"{case['label']}.ci16"
            assert digest(source) == case['source_sha256']
            assert digest(path) == case['selected_iq_sha256']
            raw = np.fromfile(source, dtype='<i2').reshape(-1, 2)
            start = case['number'] * 447851
            assert case['source_offset'] == start
            assert case['repeat_shift'] == (0, 3333, 6667)[case['repeat']]
            offset = start + case['repeat_shift']
            np.testing.assert_array_equal(np.fromfile(path, dtype='<i2').reshape(-1, 2), raw[offset:offset + 447851])
            local = raw[start:start + 20000].astype(float)
            powers = np.asarray(case['powers'])
            winner, repeat = np.unravel_index(powers.argmax(), powers.shape)
            assert (winner + 1, repeat) == (case['winner'], case['repeat'])
            choices = [dict(case, ranking_shift=case['repeat_shift'])]
        else:
            ns['ROOT'] = BASE / 'combined-pilot-controls-v1'
            path = ns['ROOT'] / label / 'iq.ci16'
            assert digest(path) == case['input_sha256']
            local = np.fromfile(path, dtype='<i2').reshape(-1, 2).astype(float)
            powers = np.asarray(case['scores'])
            choices = case['comparisons']
        iq = local[:, 0] + 1j * local[:, 1]
        seen = set()
        for choice in choices:
            if mode == 'timing-aware':
                radius = choice['radius']
                block = powers[:choice['budget'], 8-radius:9+radius]
                winner, column = np.unravel_index(block.argmax(), block.shape)
                assert (winner + 1, column-radius) == (choice['winner'], choice['ranking_shift'])
            peak = proposal_case['scores'][choice['winner'] - 1]
            start = peak['epoch'] + 22 + choice['ranking_shift']
            z = iq[start:start + 3300]
            spectrum = np.fft.fft(z * ref.conj(), 4096)
            frequency = abs(spectrum).argmax()
            direct = abs(np.vdot(ref, z * np.exp(-2j*np.pi*frequency*np.arange(3300)/4096)))**2 / max(float(energy*np.vdot(z,z).real), 1)
            np.testing.assert_allclose(choice['power'], direct, rtol=2e-10, atol=2e-14)
            rank_checks += 1
            if choice['winner'] in seen:
                continue
            seen.add(choice['winner'])
            journal = root / (f"{label}-candidate{choice['winner']}.jsonl" if mode == 'timing-aware' else f'{label}/worker.jsonl')
            assert digest(journal) == choice['journal_sha256']
            rows = [json.loads(line) for line in journal.read_text().splitlines()]
            assert rows[-1] == choice['terminal']
            description = dict(label=label, proposal=peak)
            checked = ns['check'](description, rows)
            assert checked['accepted'] == choice['accepted']
            results.append(dict(mode=mode, winner=choice['winner'], **checked))
            if label == 'positive-0':
                for field in ('coherence', 'cfo_hz'):
                    changed = copy.deepcopy(rows)
                    next(r for r in changed if r['kind'] == 3)[field] += .001
                    try:
                        ns['check'](description, changed)
                    except AssertionError:
                        mutations += 1
                    else:
                        raise AssertionError('corrupted measurement accepted')
result = dict(status='pass', ranking_winners_checked=rank_checks, worker_checks=len(results),
    resolver_hypotheses=sum(r['resolver_hypotheses'] for r in results),
    moment_dense_fits=sum(r['moment_dense_fits'] for r in results), mutations_rejected=mutations,
    reviewer_sha256=digest(Path(__file__)), reused_reviewer_sha256=digest(reviewer),
    new_rf_samples=0, arm_cost_measured=False, live_tracking_qualified=False, cases=results)
with (BASE / 'ranking-diagnostics-independent-review.json').open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k != 'cases'}))
