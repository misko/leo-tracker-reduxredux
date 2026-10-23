"""Freeze RF-only restart selection before geographic reporting."""

from pathlib import Path

import numpy as np

from ds23_family_cavity import unused_student_gap
from probe_ds23_family_cavity_position import unused_count
from run_algo01_ds23_sample import read, write, sha
import run_dbg01_latest_worst as study


def phase_valid(pair):
    return all(r['final_phase_change_s'] <= .01 and max(abs(np.asarray(r['state']['phases']))) <= 15.+1e-8
               for r in pair.values())


def one(case):
    out = study.configure(case)
    d = study.data(case)
    bank = read(out/'hypothesis_bank.json')
    base = d['arms']['c0']
    p = study.engine.build(d['node'], d['keep'], 'c0', base['phase_reference'], d['entries'])
    base_loss = base['negative_twice_elbo']-unused_count(p, d['entries'])*unused_student_gap(d['model']['nu'])
    records = []
    for i in range(81):
        source = out/f'restart_{i:02d}.json'
        saved = read(source)
        node = bank['nodes'][saved['arms']['c0']['final_mode']]
        r = saved['arms']['c0']
        p = study.engine.build(node, d['keep'], 'c0', r['phase_reference'], d['entries'])
        value = r['negative_twice_elbo']-unused_count(p, d['entries'])*unused_student_gap(d['model']['nu'])
        records.append(dict(start_id=i, loss=value, compatible=bool(saved['paired_valid'] and phase_valid(saved['arms'])),
                            source_sha256=sha(source), final_mode=r['final_mode']))
    choices = [r for r in records if r['compatible']]
    best = min(choices, key=lambda r:(r['loss'], r['start_id'])) if choices else None
    gain = base_loss-best['loss'] if best is not None else None
    penalty = float(2*np.log(len(bank['nodes'])))
    result = dict(case=case, incumbent_loss=base_loss, best=best, gain=gain,
                  penalty=penalty, accepted=bool(best is not None and gain > penalty), records=records,
                  selection='minimum corrected normalized c0 score, both-arm gates and phase convergence, 2 log assignment-pool size preference',
                  matched_original_points_and_predictive_entries=True,
                  no_evaluation_reference_or_position_error_used=True,
                  source_sha256=sha(Path(__file__)))
    target = out/'RF_restart_selection.json'
    if target.exists():
        raise FileExistsError('preserve sealed restart selection')
    write(target, result)
    print(case, 'RF-selected restart', None if best is None else best['start_id'],
          'gain', gain, 'accepted', result['accepted'], flush=True)
    return result


def main():
    audit = read(study.PARENT/'independent_iteration_audit.json')
    if not audit['all_passed']:
        raise ValueError('finish independent audit before RF selection')
    results = [one(case) for case in read(study.PARENT/'protocol.json')['cases']]
    write(study.PARENT/'RF_restart_selection.json', dict(rows=results,
          selection_frozen_before_new_geographic_error_comparison=True))


if __name__ == '__main__':
    main()
