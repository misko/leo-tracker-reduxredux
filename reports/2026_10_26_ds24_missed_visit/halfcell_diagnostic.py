"""Prespecified half-cell coverage check; no scorer or forecast changes."""
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'timing'))
import study
import timing_search


def main():
    study.bound()
    destination = ROOT / 'halfcell_diagnostic'
    destination.mkdir(exist_ok=True)
    protocol = dict(
        schema='unchanged-r01-halfcell-control/v1', seed=2026102607,
        offsets_samples=[-252, -100, 4, 100, 252], strengths_db=[-12],
        edges=['lower', 'upper'], rates_hz_s=[-2000., 2000.],
        donor_errors_hz=[-200., 200.],
        lanes=['zero_rate_fallback', 'rate_propagated'],
        expected_independent_targets=80, maximum_seconds=580,
        scorer_protocol_sha256=study.sha(ROOT / 'timing/protocol.json'),
        source_sha256=study.sha(__file__), outcomes_before_freeze=0,
        purpose='Test between-grid timing errors without changing R01 scoring or gates.',
        root_approved=True,
    )
    study.write(destination / 'protocol.json', protocol)
    rng = np.random.default_rng(protocol['seed'])
    began = time.monotonic()
    rows = []
    combinations = itertools.product(protocol['edges'], protocol['offsets_samples'],
        protocol['rates_hz_s'], protocol['donor_errors_hz'], protocol['lanes'])
    for trial, (edge, offset, rate, error, lane) in enumerate(combinations):
        owner = f'halfcell/{trial}/{edge}'
        packet = study.synth_packet(owner, edge, error, offset, rate, lane)
        noise = (rng.normal(size=200000) + 1j*rng.normal(size=200000))/np.sqrt(2)
        wave = study.wave(200000, 10_000_000, edge, 4321.25,
                          213456.75 + rate*.354, rate, 100*np.sign(rate))
        amplitude = np.sqrt(np.mean(abs(noise)**2)*10**(-12/10)/np.mean(abs(wave)**2))
        values = (noise + amplitude*wave).astype(np.complex64)
        def seal(receipt, trial=trial):
            study.write(destination / 'selections' / f'{trial}.json', receipt)
        result = timing_search.score_target(values, 10_000_000, edge, packet, seal)
        evaluation = study.evaluate(result, 213456.75+rate*(.354+.01),
                                    4321.25+np.sign(rate), 10_000_000)
        rows.append(dict(trial=trial, edge=edge, offset_samples=offset,
            true_rate_hz_s=rate, donor_error_hz=error, lane=lane,
            target_sha256=hashlib.sha256(values.astype('<c8').tobytes()).hexdigest(),
            result=result, evaluation=evaluation))
    summary = {}
    for method in ['point', 'search']:
        evaluated = [r['evaluation'][method] for r in rows]
        summary[method] = dict(
            targets=len(evaluated),
            admitted=sum(bool(v.get('admitted')) for v in evaluated),
            admitted_within500=sum(bool(v.get('admitted')) and v.get('accurate500', False) for v in evaluated),
            admitted_over1000=sum(bool(v.get('admitted')) and abs(v.get('cfo_error_hz', 0)) > 1000 for v in evaluated),
        )
    study.write(destination / 'outcomes.json.gz', dict(protocol=protocol, rows=rows,
        seconds=time.monotonic()-began, summary=summary))
    study.write(destination / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
