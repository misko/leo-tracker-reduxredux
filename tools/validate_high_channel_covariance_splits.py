"""Sensitivity to eight fixed random block splits, with no model retuning."""

import argparse
from pathlib import Path

import debug_fast_graph_unassociated as report
from probe_graph_shared_high_channels import context
from probe_high_channel_correlated_noise import validation


def main(args):
    args.output.mkdir(parents=True,exist_ok=False)
    d=context(args)
    calibration=report.read(args.parent/'calibration.json')
    extras=report.read(args.parent/'target_entries.json')
    models=dict(white=calibration['null'],correlated=calibration['best_correlated'])
    results=[]
    for seed in range(8):
        checks={name:validation(d,extras,model,seed=seed) for name,model in models.items()}
        record=dict(seed=seed,checks=checks)
        results.append(record)
        print(seed,[(a,checks['white'][a]['held']['objective']-checks['correlated'][a]['held']['objective'],
            checks['correlated'][a]['held']['noise']['noise_screen_pass'],
            all(r['noise_screen_pass'] for r in checks['correlated'][a]['held']['per_track_noise'].values())) for a in ('c0','fitted_c')],flush=True)
    report.write(args.output/'results.json',dict(seeds=list(range(8)),no_retuning=True,
        independent_replicates=False,reason='Repeated splits reuse the same 113 observations',results=results))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','source-root','ch1','parent','output'):p.add_argument('--'+name,required=True,type=Path)
    main(p.parse_args())
