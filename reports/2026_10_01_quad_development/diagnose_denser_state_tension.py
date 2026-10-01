"""Compare each evidence model at both fitted states; no cross-model objective ranking."""
import fcntl
import json
from pathlib import Path
import sys
import numpy as np
from denser_window_inputs import prepare_denser_window
from regression_batch import verify_sources
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'denser-state-tension-v1.json'
    if output.exists():
        raise FileExistsError(output)
    inputs, rows = {}, []
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for dataset in ('DS9', 'DS10', 'DS11'):
            unit = dataset+'-B01-S1'
            receipts, states = {}, {}
            for limit in (8, 16):
                directory = HERE/'denser-pilot-v1'/unit/str(limit)
                path = directory/(unit+'.json')
                receipt = sealed(path)
                audit = sealed(directory/'evaluation.json')
                launch = sealed(directory/'audit-launch.json')
                assert launch['returncode'] == 0 and launch['within_budget'] and not launch['timed_out']
                assert audit['rows'][0]['accepted'] and audit['rows'][0]['receipt_sha256'] == digest(path)
                freeze = sealed(directory/'sources.json')
                verify_sources(freeze['source_sha256'])
                verify_sources(freeze['inputs'])
                inputs.update({str(p): digest(p) for p in (path, directory/'evaluation.json', directory/'audit-launch.json', directory/'sources.json')})
                receipts[limit] = receipt
                states[limit] = np.asarray(receipt['best']['mean'])
            precision = np.asarray(receipts[8]['precision'])
            prior_terms = {str(limit): dict(clock=float(.5*precision[2]*state[2]**2),
                drifts=float(.5*(precision[3:5]*state[3:5])@state[3:5]),
                epochs=float(.5*(precision[5:]*state[5:])@state[5:])) for limit, state in states.items()}
            models = {}
            for limit in (8, 16):
                prepared, _ = prepare_denser_window(unit, limit)
                ports = prepared[-1]
                values = {}
                labels = {}
                for state_limit, state in states.items():
                    scores = [p.score_all(state) for p in ports]
                    labels[state_limit] = [int(np.argmax(s)) for s in scores]
                    likelihood = -float(sum(np.max(s) for s in scores))
                    prior = float(.5*(precision*state)@state)
                    values[str(state_limit)] = dict(negative_log_likelihood=likelihood,
                                                   prior=prior, objective=likelihood+prior)
                assert abs(values[str(limit)]['objective']-receipts[limit]['best']['objectives'][-1]) < 1e-6
                models[str(limit)] = dict(at_states=values,
                    objective_change_8_to_16_state=values['16']['objective']-values['8']['objective'],
                    changed_argmax_labels_between_states=sum(a != b for a,b in zip(labels[8],labels[16])))
            rows.append(dict(unit=unit, models=models, prior_terms=prior_terms,
                fitted_endpoint_label_changes=sum(a != b for a,b in zip(receipts[8]['best']['associations'],receipts[16]['best']['associations'])),
                position_shift_m=float(1000*np.linalg.norm(states[16][:2]-states[8][:2]))))
    sources = {str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py'
        and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
    result = dict(rows=rows, inputs=inputs, sources=sources,
        qualification='Fixed three-pilot diagnostic, no fits or reference-based track selection. Compare state changes within each model only. Endpoint labels do not prove the optimization never changed labels internally. Not a causal diagnosis.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
